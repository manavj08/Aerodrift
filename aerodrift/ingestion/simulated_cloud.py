"""A moto-backed AWS sandbox with a realistic 3-tier production estate.

``SimulatedCloud`` starts moto's in-memory AWS, seeds a secure baseline,
and exposes *drift scenarios* that reproduce the manual mistakes the
project targets (an engineer opening a database or SSH to the world).
Everything goes through real boto3 calls, so ingestion and remediation
code paths are identical to live AWS.

Baseline estate (region us-east-1, VPC 10.0.0.0/16 "prod-vpc"):

    Internet --443/80--> sg-web --> web-01, web-02     (public subnet)
    web tier --8080----> sg-app --> app-01             (private app subnet)
    app tier --5432----> sg-db  --> db-prod-01 (RDS)   (private data subnets)
    10.0.0.0/16 --22---> sg-app                        (SSH from inside VPC only)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import boto3

REGION = "us-east-1"


@dataclass
class DriftInjection:
    scenario: str
    description: str
    group_id: str
    rule: str
    injected_at: float = field(default_factory=time.monotonic)


class SimulatedCloud:
    """Context manager: ``with SimulatedCloud() as cloud: ...``."""

    SCENARIOS = ("open-db", "open-ssh", "open-all-app", "shadow-sg")

    def __init__(self, region: str = REGION, seed: bool = True):
        self.region = region
        self._seed = seed
        self._mock = None
        self.session = None
        self.ids: dict[str, str] = {}
        self.injections: list[DriftInjection] = []

    # -------------------------------------------------------- lifecycle
    def start(self) -> "SimulatedCloud":
        from moto import mock_aws  # imported lazily: only needed for simulation

        for var, val in (("AWS_ACCESS_KEY_ID", "testing"), ("AWS_SECRET_ACCESS_KEY", "testing"),
                         ("AWS_SESSION_TOKEN", "testing"), ("AWS_DEFAULT_REGION", self.region)):
            os.environ.setdefault(var, val)
        self._mock = mock_aws()
        self._mock.start()
        self.session = boto3.session.Session(region_name=self.region)
        self.ec2 = self.session.client("ec2", region_name=self.region)
        self.rds = self.session.client("rds", region_name=self.region)
        if self._seed:
            self.seed_baseline()
        return self

    def stop(self) -> None:
        if self._mock is not None:
            self._mock.stop()
            self._mock = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # ------------------------------------------------------------ seed
    @staticmethod
    def _name(resource_type, name):
        return [{"ResourceType": resource_type, "Tags": [{"Key": "Name", "Value": name}]}]

    def _sg(self, key, name, desc, vpc):
        gid = self.ec2.create_security_group(
            GroupName=name, Description=desc, VpcId=vpc,
            TagSpecifications=self._name("security-group", name),
        )["GroupId"]
        self.ids[key] = gid
        return gid

    def seed_baseline(self) -> dict:
        ec2 = self.ec2
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16",
                             TagSpecifications=self._name("vpc", "prod-vpc"))["Vpc"]["VpcId"]
        self.ids["vpc"] = vpc

        def subnet(key, cidr, az, name):
            sid = ec2.create_subnet(VpcId=vpc, CidrBlock=cidr, AvailabilityZone=az,
                                    TagSpecifications=self._name("subnet", name))["Subnet"]["SubnetId"]
            self.ids[key] = sid
            return sid

        pub = subnet("subnet_public", "10.0.1.0/24", f"{self.region}a", "public-a")
        app = subnet("subnet_app", "10.0.2.0/24", f"{self.region}a", "private-app-a")
        data_a = subnet("subnet_data_a", "10.0.3.0/24", f"{self.region}a", "private-data-a")
        data_b = subnet("subnet_data_b", "10.0.4.0/24", f"{self.region}b", "private-data-b")
        ec2.modify_subnet_attribute(SubnetId=pub, MapPublicIpOnLaunch={"Value": True})

        web_sg = self._sg("sg_web", "web-sg", "public web tier", vpc)
        app_sg = self._sg("sg_app", "app-sg", "private app tier", vpc)
        db_sg = self._sg("sg_db", "db-sg", "private database tier", vpc)

        def allow(gid, port, cidr=None, group=None):
            perm = {"IpProtocol": "tcp", "FromPort": port, "ToPort": port}
            if cidr:
                perm["IpRanges"] = [{"CidrIp": cidr}]
            if group:
                perm["UserIdGroupPairs"] = [{"GroupId": group}]
            ec2.authorize_security_group_ingress(GroupId=gid, IpPermissions=[perm])

        allow(web_sg, 443, cidr="0.0.0.0/0")
        allow(web_sg, 80, cidr="0.0.0.0/0")
        allow(app_sg, 8080, group=web_sg)
        allow(app_sg, 22, cidr="10.0.0.0/16")
        allow(db_sg, 5432, group=app_sg)

        def instance(key, name, sn, sg):
            iid = ec2.run_instances(
                ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t3.micro",
                SubnetId=sn, SecurityGroupIds=[sg], TagSpecifications=self._name("instance", name),
            )["Instances"][0]["InstanceId"]
            self.ids[key] = iid
            return iid

        instance("ec2_web_1", "web-01", pub, web_sg)
        instance("ec2_web_2", "web-02", pub, web_sg)
        instance("ec2_app_1", "app-01", app, app_sg)

        self.rds.create_db_subnet_group(DBSubnetGroupName="prod-data", DBSubnetGroupDescription="data",
                                        SubnetIds=[data_a, data_b])
        self.rds.create_db_instance(
            DBInstanceIdentifier="db-prod-01", DBInstanceClass="db.t3.micro", Engine="postgres",
            MasterUsername="aerodrift", MasterUserPassword="not-a-real-secret-1", AllocatedStorage=20,
            VpcSecurityGroupIds=[db_sg], DBSubnetGroupName="prod-data", PubliclyAccessible=False,
        )
        self.ids["rds_db"] = "db-prod-01"
        return dict(self.ids)

    # ---------------------------------------------------------- drift
    def _authorize(self, gid, proto, from_port, to_port, cidr="0.0.0.0/0"):
        perm = {"IpProtocol": proto, "IpRanges": [{"CidrIp": cidr}]}
        if proto != "-1":
            perm.update(FromPort=from_port, ToPort=to_port)
        self.ec2.authorize_security_group_ingress(GroupId=gid, IpPermissions=[perm])

    def inject_drift(self, scenario: str = "open-db") -> DriftInjection:
        """Simulate an engineer's manual console change."""
        if scenario == "open-db":
            gid, rule = self.ids["sg_db"], "0.0.0.0/0:5432/tcp"
            self._authorize(gid, "tcp", 5432, 5432)
            desc = "db-sg opened to 0.0.0.0/0 on 5432 (production database exposed)"
        elif scenario == "open-ssh":
            gid, rule = self.ids["sg_web"], "0.0.0.0/0:22/tcp"
            self._authorize(gid, "tcp", 22, 22)
            desc = "web-sg opened to 0.0.0.0/0 on 22 (SSH left open after debugging)"
        elif scenario == "open-all-app":
            gid, rule = self.ids["sg_app"], "0.0.0.0/0:all/all"
            self._authorize(gid, "-1", None, None)
            desc = "app-sg opened to 0.0.0.0/0 on all protocols (indirect path to the database)"
        elif scenario == "shadow-sg":
            gid = self._sg("sg_shadow", "temp-debug-sg", "temporary debugging", self.ids["vpc"])
            self._authorize(gid, "tcp", 5432, 5432)
            self.rds.modify_db_instance(DBInstanceIdentifier="db-prod-01",
                                        VpcSecurityGroupIds=[self.ids["sg_db"], gid],
                                        ApplyImmediately=True)
            rule = "0.0.0.0/0:5432/tcp"
            desc = "new temp-debug-sg (open 5432 to world) attached to db-prod-01"
        else:
            raise ValueError(f"unknown scenario {scenario!r}; choose from {self.SCENARIOS}")
        injection = DriftInjection(scenario, desc, gid, rule)
        self.injections.append(injection)
        return injection

    def ingress_rules(self, group_id: str) -> list[str]:
        from aerodrift.ingestion.rules import rules_from_ip_permissions
        grp = self.ec2.describe_security_groups(GroupIds=[group_id])["SecurityGroups"][0]
        return [str(r) for r in rules_from_ip_permissions(grp.get("IpPermissions", []))]
