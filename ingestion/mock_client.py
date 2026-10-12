import boto3
from moto import mock_aws
from ingestion.schema import Resource, Relationship


@mock_aws
def get_mock_ec2_state() -> tuple[list[Resource], list[Relationship]]:
    """Spins up fake EC2 infra via moto and returns it as Resource/Relationship objects."""
    ec2 = boto3.client("ec2", region_name="us-east-1")

    sg = ec2.create_security_group(GroupName="open-sg", Description="test sg")
    sg_id = sg["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        SecurityGroupIds=[sg_id],
    )

    resources = [
        Resource("sg-web", "SecurityGroup", {"ingress": "0.0.0.0/0:22"}),
        Resource("i-web", "EC2Instance", {"instance_type": "t2.micro"}),
    ]
    relationships = [
        Relationship("i-web", "sg-web", "ATTACHED_TO"),
    ]
    return resources, relationships


@mock_aws
def get_mock_ec2_state_fixed() -> tuple[list[Resource], list[Relationship]]:
    """Same as get_mock_ec2_state, but with the SG ingress rule removed (post-remediation)."""
    ec2 = boto3.client("ec2", region_name="us-east-1")

    sg = ec2.create_security_group(GroupName="closed-sg", Description="test sg (fixed)")
    sg_id = sg["GroupId"]
    # No open ingress rule added this time, which simulates the fix

    ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        SecurityGroupIds=[sg_id],
    )

    resources = [
        Resource("sg-web", "SecurityGroup", {"ingress": "none"}),
        Resource("i-web", "EC2Instance", {"instance_type": "t2.micro"}),
    ]
    relationships = [
        Relationship("i-web", "sg-web", "ATTACHED_TO"),
    ]
    return resources, relationships


if __name__ == "__main__":
    resources, relationships = get_mock_ec2_state()
    print("Resources:")
    for r in resources:
        print(" ", r)
    print("Relationships:")
    for rel in relationships:
        print(" ", rel)