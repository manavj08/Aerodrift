from aerodrift.graph.builder import build_graph
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

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


def test_adapter_fills_missing_fields_with_defaults():
    resources, relationships = get_mock_ec2_state()
    resource_dicts, _ = resources_to_graph_input(resources, relationships)

    # Person A's schema has no "exposure"/"cidr" concept — adapter must not
    # crash, and should fall back to documented defaults rather than KeyError.
    sg = next(r for r in resource_dicts if r["type"] == "SecurityGroup")
    assert sg["exposure"] == "unknown"
    assert sg["cidr"] is None
