from aerodrift.ingestion.mock_client import get_mock_ec2_state


def test_mock_state_shape():
    resources, relationships = get_mock_ec2_state()
    assert len(resources) == 2
    assert relationships[0].relation_type == "ATTACHED_TO"


def test_security_group_has_open_ingress():
    resources, _ = get_mock_ec2_state()
    sg = next(r for r in resources if r.resource_type == "SecurityGroup")
    assert "0.0.0.0/0" in sg.attributes["ingress"]