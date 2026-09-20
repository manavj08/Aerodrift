from aerodrift.graph.builder import build_graph
from aerodrift.graph.topology import detect_drift, INTERNET_NODE
from aerodrift.ingestion.adapter import resources_to_graph_input
from aerodrift.ingestion.mock_client import get_mock_ec2_state


def test_adapter_converts_dataclasses_to_dicts():
    resources, relationships = get_mock_ec2_state()
    resource_dicts, connection_dicts = resources_to_graph_input(resources, relationships)

    assert all(isinstance(r, dict) for r in resource_dicts)
    assert all(isinstance(c, dict) for c in connection_dicts)
    assert {"id", "type", "name", "exposure", "cidr"} <= resource_dicts[0].keys()
    assert {"source", "target", "port", "protocol", "direction"} <= connection_dicts[0].keys()


def test_adapter_output_is_consumable_by_build_graph():
    resources, relationships = get_mock_ec2_state()
    resource_dicts, connection_dicts = resources_to_graph_input(resources, relationships)

    graph = build_graph(resource_dicts, connection_dicts)

    # 2 real resources (SG, EC2 instance) + 1 synthesized internet node
    # (added by this fix so detect_drift() has a path to search from).
    assert len(graph.nodes) == 3
    # 1 real relationship (EC2 -> SG) + 1 synthesized internet -> SG edge.
    assert len(graph.edges) == 2


def test_adapter_fills_missing_fields_with_defaults():
    resources, relationships = get_mock_ec2_state()
    resource_dicts, _ = resources_to_graph_input(resources, relationships)

    # Person A's schema has no "exposure"/"cidr" concept — adapter must not
    # crash, and should fall back to documented defaults rather than KeyError.
    sg = next(r for r in resource_dicts if r["type"] == "SecurityGroup")
    assert sg["exposure"] == "unknown"
    assert sg["cidr"] is None


def test_adapter_synthesizes_internet_node_for_public_ingress():
    """The workaround this fix adds: a resource with a 0.0.0.0/0 ingress
    rule (per Resource.attributes["ingress"]) should produce a synthetic
    internet node + inbound edge, since nothing else in the pipeline
    creates one and detect_drift() requires it to find anything.
    """
    resources, relationships = get_mock_ec2_state()
    resource_dicts, connection_dicts = resources_to_graph_input(resources, relationships)

    internet_nodes = [r for r in resource_dicts if r["id"] == INTERNET_NODE]
    assert len(internet_nodes) == 1
    assert internet_nodes[0]["type"] == "internet"

    internet_edges = [c for c in connection_dicts if c["source"] == INTERNET_NODE]
    assert len(internet_edges) == 1
    sg = next(r for r in resources if r.resource_type == "SecurityGroup")
    assert internet_edges[0]["target"] == sg.resource_id


def test_adapter_does_not_synthesize_internet_node_without_public_ingress():
    # A resource with no "ingress" attribute, or a non-public one, should
    # not trigger internet-node synthesis.
    from aerodrift.ingestion.schema import Resource

    private_resource = Resource("i-private", "EC2Instance", {})
    resource_dicts, connection_dicts = resources_to_graph_input([private_resource], [])
    assert not any(r["id"] == INTERNET_NODE for r in resource_dicts)
    assert connection_dicts == []


def test_full_pipeline_now_produces_a_graph_with_internet_reachability():
    """End-to-end: ingestion -> adapter -> build_graph should now include
    a path from the internet to the open security group (it did not,
    before this fix — see CONTRACT.md).
    """
    import networkx as nx

    resources, relationships = get_mock_ec2_state()
    resource_dicts, connection_dicts = resources_to_graph_input(resources, relationships)
    graph = build_graph(resource_dicts, connection_dicts)

    sg = next(r for r in resources if r.resource_type == "SecurityGroup")
    assert INTERNET_NODE in graph
    assert nx.has_path(graph, INTERNET_NODE, sg.resource_id)


def test_detect_drift_still_finds_nothing_on_real_data_pending_type_alignment():
    """KNOWN GAP, not fixed by this adapter change: detect_drift() only
    flags nodes whose resource_type is in SENSITIVE_RESOURCE_TYPES
    ({"database", "rds"}). Person A's real mock data never produces a
    database/rds node — the exposed resource is a "SecurityGroup" — and
    topology.py's OWN mock graph uses lowercase "security_group", while
    Person A's real data uses PascalCase "SecurityGroup". So even with
    the internet node now correctly synthesized (see the tests above),
    detect_drift() still reports zero drift on this real pipeline.

    This test documents the current (still incomplete) behavior rather
    than silently passing or silently hiding the gap. See CONTRACT.md
    open items: does an internet-facing SecurityGroup count as drift on
    its own, and what resource_type casing is authoritative? Once the
    team decides, this test should be replaced with one asserting real
    drift IS detected.
    """
    resources, relationships = get_mock_ec2_state()
    resource_dicts, connection_dicts = resources_to_graph_input(resources, relationships)
    graph = build_graph(resource_dicts, connection_dicts)

    assert detect_drift(graph) == []
