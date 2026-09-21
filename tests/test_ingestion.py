from ingestion.mock_client import get_mock_ec2_state
from ingestion.graph_builder import build_graph


def test_mock_state_shape():
    resources, relationships = get_mock_ec2_state()
    assert len(resources) == 2
    assert relationships[0].relation_type == "ATTACHED_TO"


def test_security_group_has_open_ingress():
    resources, _ = get_mock_ec2_state()
    sg = next(r for r in resources if r.resource_type == "SecurityGroup")
    assert "0.0.0.0/0" in sg.attributes["ingress"]


def test_build_graph_shape():
    resources, relationships = get_mock_ec2_state()
    graph = build_graph(resources, relationships)

    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1

    sg_node = next(n for n, d in graph.nodes(data=True) if d["resource_type"] == "SecurityGroup")
    assert graph.nodes[sg_node]["ingress"] == "0.0.0.0/0:22"