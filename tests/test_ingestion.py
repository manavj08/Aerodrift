from ingestion.mock_client import get_mock_ec2_state
from ingestion.graph_builder import build_graph
from ingestion.state_refresh import refresh_state
from ingestion.snapshots import save_snapshot, diff_snapshots


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


def test_refresh_state_before_fix():
    graph = refresh_state(fixed=False)
    sg_node = next(n for n, d in graph.nodes(data=True) if d["resource_type"] == "SecurityGroup")
    assert "0.0.0.0/0" in graph.nodes[sg_node]["ingress"]


def test_refresh_state_after_fix():
    graph = refresh_state(fixed=True)
    sg_node = next(n for n, d in graph.nodes(data=True) if d["resource_type"] == "SecurityGroup")
    assert graph.nodes[sg_node]["ingress"] == "none"


def test_snapshot_diff_detects_fix(tmp_path):
    db = str(tmp_path / "test.db")
    before_id = save_snapshot(refresh_state(fixed=False), db)
    after_id = save_snapshot(refresh_state(fixed=True), db)

    diff = diff_snapshots(before_id, after_id, db)

    assert diff["added"] == []
    assert diff["removed"] == []
    assert "sg-web" in diff["changed"]
    assert diff["changed"]["sg-web"]["new"]["ingress"] == "none"