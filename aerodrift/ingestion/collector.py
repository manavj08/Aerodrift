"""Asynchronous AWS state collector.

boto3 is synchronous, so every API call is pushed onto a worker thread
with ``asyncio.to_thread`` and all of them are awaited together with
``asyncio.gather``. A semaphore bounds how many calls are in flight at
once (per collector) so large multi-region scans don't trip API rate
limits. Results are normalised into ``Resource`` / ``Relationship``
records the topology engine understands.

The same collector works against real AWS (any boto3 session) and
against the moto-backed ``SimulatedCloud`` — nothing here is mock-aware.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import boto3

from aerodrift.config import (
    INTERNET_NODE,
    PUBLIC_CIDRS,
    TYPE_EC2,
    TYPE_INTERNET,
    TYPE_RDS,
    TYPE_SECURITY_GROUP,
    TYPE_SUBNET,
    TYPE_VPC,
)
from aerodrift.ingestion.rules import SOURCE_GROUP, rules_from_ip_permissions
from aerodrift.ingestion.schema import (
    REL_ALLOWS_INGRESS,
    REL_ATTACHED_TO,
    REL_CONTAINS,
    CloudState,
    Relationship,
    Resource,
)


def _tags(tag_list) -> dict:
    return {t["Key"]: t["Value"] for t in (tag_list or []) if "Key" in t}


class CollectionError(RuntimeError):
    """Raised when an AWS API call fails during collection."""


class AWSCollector:
    """Concurrently polls EC2 + RDS APIs and returns a ``CloudState``."""

    def __init__(self, session: "boto3.session.Session | None" = None,
                 regions: list[str] | None = None, max_concurrency: int = 8):
        self.session = session or boto3.session.Session()
        self.regions = regions or [self.session.region_name or "us-east-1"]
        self.max_concurrency = max_concurrency
        self._clients: dict[tuple[str, str], object] = {}

    # ----------------------------------------------------------- clients
    def client(self, service: str, region: str | None = None):
        region = region or self.regions[0]
        key = (service, region)
        if key not in self._clients:
            self._clients[key] = self.session.client(service, region_name=region)
        return self._clients[key]

    # ------------------------------------------------------- API helpers
    async def _call(self, sem, timings, label, fn):
        async with sem:
            start = time.perf_counter()
            try:
                result = await asyncio.to_thread(fn)
            except Exception as exc:  # botocore errors, network errors
                raise CollectionError(f"{label} failed: {exc}") from exc
            timings[label] = round((time.perf_counter() - start) * 1000, 2)
            return result

    @staticmethod
    def _paginate(client, operation, key, **kwargs):
        def run():
            out = []
            for page in client.get_paginator(operation).paginate(**kwargs):
                out.extend(page.get(key, []))
            return out
        return run

    async def _collect_region(self, region, sem, timings):
        ec2 = self.client("ec2", region)
        rds = self.client("rds", region)
        p = self._paginate
        results = await asyncio.gather(
            self._call(sem, timings, f"{region}:describe_vpcs", p(ec2, "describe_vpcs", "Vpcs")),
            self._call(sem, timings, f"{region}:describe_subnets", p(ec2, "describe_subnets", "Subnets")),
            self._call(sem, timings, f"{region}:describe_security_groups",
                       p(ec2, "describe_security_groups", "SecurityGroups")),
            self._call(sem, timings, f"{region}:describe_instances",
                       p(ec2, "describe_instances", "Reservations")),
            self._call(sem, timings, f"{region}:describe_db_instances",
                       p(rds, "describe_db_instances", "DBInstances")),
        )
        return region, results

    # ------------------------------------------------------------ public
    async def collect(self) -> CloudState:
        sem = asyncio.Semaphore(self.max_concurrency)
        timings: dict[str, float] = {}
        start = time.perf_counter()
        per_region = await asyncio.gather(
            *(self._collect_region(r, sem, timings) for r in self.regions)
        )
        resources: list[Resource] = [
            Resource(INTERNET_NODE, TYPE_INTERNET, {"name": "Internet", "cidr": "0.0.0.0/0"})
        ]
        relationships: list[Relationship] = []
        for region, (vpcs, subnets, groups, reservations, dbs) in per_region:
            r, rel = normalize(region, vpcs, subnets, groups, reservations, dbs)
            resources.extend(r)
            relationships.extend(rel)
        return CloudState(
            resources=resources,
            relationships=relationships,
            collected_at=datetime.now(timezone.utc).isoformat(),
            regions=list(self.regions),
            api_timings_ms=timings,
            total_ms=round((time.perf_counter() - start) * 1000, 2),
        )

    def collect_sync(self) -> CloudState:
        """Convenience wrapper for non-async callers."""
        return asyncio.run(self.collect())


def normalize(region, vpcs, subnets, groups, reservations, dbs):
    """Turn raw describe_* payloads into Resource/Relationship records."""
    resources: list[Resource] = []
    rels: list[Relationship] = []

    for v in vpcs:
        tags = _tags(v.get("Tags"))
        resources.append(Resource(v["VpcId"], TYPE_VPC, {
            "name": tags.get("Name", v["VpcId"]), "cidr": v.get("CidrBlock"),
            "region": region, "tags": tags, "is_default": v.get("IsDefault", False),
        }))

    for s in subnets:
        tags = _tags(s.get("Tags"))
        resources.append(Resource(s["SubnetId"], TYPE_SUBNET, {
            "name": tags.get("Name", s["SubnetId"]), "cidr": s.get("CidrBlock"),
            "vpc_id": s.get("VpcId"), "az": s.get("AvailabilityZone"),
            "public": bool(s.get("MapPublicIpOnLaunch")), "region": region, "tags": tags,
        }))
        if s.get("VpcId"):
            rels.append(Relationship(s["VpcId"], s["SubnetId"], REL_CONTAINS))

    for g in groups:
        tags = _tags(g.get("Tags"))
        rules = rules_from_ip_permissions(g.get("IpPermissions", []))
        resources.append(Resource(g["GroupId"], TYPE_SECURITY_GROUP, {
            "name": tags.get("Name", g.get("GroupName", g["GroupId"])),
            "group_name": g.get("GroupName"), "vpc_id": g.get("VpcId"),
            "region": region, "tags": tags,
            "ingress": [r.to_dict() for r in rules],
        }))
        for rule in rules:
            if rule.is_public:
                src = INTERNET_NODE
            elif rule.source_kind == SOURCE_GROUP:
                src = rule.source
            else:
                src = rule.source  # a private CIDR; the graph builder expands it
            rels.append(Relationship(src, g["GroupId"], REL_ALLOWS_INGRESS, rule.to_dict()))

    for res in reservations:
        for inst in res.get("Instances", []):
            state = (inst.get("State") or {}).get("Name", "unknown")
            if state in ("terminated", "shutting-down"):
                continue
            tags = _tags(inst.get("Tags"))
            iid = inst["InstanceId"]
            resources.append(Resource(iid, TYPE_EC2, {
                "name": tags.get("Name", iid), "instance_type": inst.get("InstanceType"),
                "subnet_id": inst.get("SubnetId"), "vpc_id": inst.get("VpcId"),
                "private_ip": inst.get("PrivateIpAddress"),
                "public_ip": inst.get("PublicIpAddress"), "state": state,
                "region": region, "tags": tags,
            }))
            if inst.get("SubnetId"):
                rels.append(Relationship(inst["SubnetId"], iid, REL_CONTAINS))
            for sg in inst.get("SecurityGroups", []):
                rels.append(Relationship(iid, sg["GroupId"], REL_ATTACHED_TO))

    for db in dbs:
        did = db["DBInstanceIdentifier"]
        tags = _tags(db.get("TagList"))
        subnet_ids = [s["SubnetIdentifier"] for s in (db.get("DBSubnetGroup") or {}).get("Subnets", [])]
        resources.append(Resource(did, TYPE_RDS, {
            "name": did, "engine": db.get("Engine"), "instance_class": db.get("DBInstanceClass"),
            "publicly_accessible": bool(db.get("PubliclyAccessible")),
            "vpc_id": (db.get("DBSubnetGroup") or {}).get("VpcId"),
            "subnet_ids": subnet_ids, "region": region, "tags": tags,
        }))
        if subnet_ids:
            rels.append(Relationship(sorted(subnet_ids)[0], did, REL_CONTAINS))
        for sg in db.get("VpcSecurityGroups", []):
            rels.append(Relationship(did, sg["VpcSecurityGroupId"], REL_ATTACHED_TO))

    return prune_empty_default_vpcs(resources, rels)


def prune_empty_default_vpcs(resources, rels):
    """Drop AWS default VPCs (and their subnets/SGs) that host no workloads.

    Every AWS region ships a default VPC with one subnet per AZ; showing
    them adds noise to the topology without adding risk. A default VPC
    that actually hosts EC2/RDS is kept.
    """
    default_vpcs = {r.resource_id for r in resources
                    if r.resource_type == TYPE_VPC and r.attributes.get("is_default")}
    if not default_vpcs:
        return resources, rels
    used = {r.attributes.get("vpc_id") for r in resources if r.resource_type in (TYPE_EC2, TYPE_RDS)}
    drop_vpcs = default_vpcs - used
    drop = {r.resource_id for r in resources
            if r.resource_id in drop_vpcs or r.attributes.get("vpc_id") in drop_vpcs}
    return ([r for r in resources if r.resource_id not in drop],
            [x for x in rels if x.source_id not in drop and x.target_id not in drop])
