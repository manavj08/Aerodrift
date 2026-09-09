"""Placeholder — owned by Person A.

Will provide async boto3 wrappers to pull mock AWS state
(EC2s, Subnets, Security Groups). Not implemented by Person C.
"""


def get_mock_aws_state() -> dict:
    """Placeholder mock state so Person C's code can run standalone."""
    return {"vpcs": [], "ec2s": [], "security_groups": []}
