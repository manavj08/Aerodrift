import boto3
from moto import mock_aws
from aerodrift.ingestion.schema import Resource, Relationship


@mock_aws
def get_mock_ec2_state() -> tuple[list[Resource], list[Relationship]]:
    """Spins up fake EC2 infra via moto and returns it as Resource/Relationship objects."""
    ec2 = boto3.client("ec2", region_name="us-east-1")

    # Create a security group with an open SSH rule (deliberately risky, for drift testing later)
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

    # Create an instance attached to that security group
    instance = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        SecurityGroupIds=[sg_id],
    )
    instance_id = instance["Instances"][0]["InstanceId"]

    resources = [
        Resource(sg_id, "SecurityGroup", {"ingress": "0.0.0.0/0:22"}),
        Resource(instance_id, "EC2Instance", {"instance_type": "t2.micro"}),
    ]
    relationships = [
        Relationship(instance_id, sg_id, "ATTACHED_TO"),
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