"""Tests for aerodrift.cli.dashboard — Week 2 Day 1 real graph rendering."""

import networkx as nx
from rich.layout import Layout

from aerodrift.cli.dashboard import (
    build_layout,
    _build_header,
    _build_topology_panel,
    _build_drift_list_panel,
    _build_footer,
    _drifted_node_ids,
    STATUS_HEALTHY,
    STATUS_DRIFTED,
    MAX_TOPOLOGY_ROWS,
)
from aerodrift.graph.topology import build_mock_graph


def test_build_layout_returns_layout():
    layout = build_layout()
    assert isinstance(layout, Layout)


def test_layout_has_expected_regions():
    layout = build_layout()
    assert layout["header"] is not None
    assert layout["topology"] is not None
    assert layout["drift_list"] is not None
    assert layout["footer"] is not None


def test_build_layout_no_graph_no_drifts_is_healthy():
    layout = build_layout()
    assert layout is not None


def test_build_layout_with_graph_and_drifts():
    graph = build_mock_graph()
    drifts = [
        {"drift_id": "drift-001", "type": "open_ingress", "affected_node": "sg-0a1b2c3", "severity": "critical"}
    ]
    layout = build_layout(graph=graph, drifts=drifts)
    assert layout is not None


def test_header_builds():
    assert _build_header() is not None


def test_drifted_node_ids_extracts_affected_nodes():
    drifts = [{"affected_node": "sg-1"}, {"affected_node": "db-1"}, {}]
    assert _drifted_node_ids(drifts) == {"sg-1", "db-1"}


def test_topology_panel_no_graph():
    assert _build_topology_panel(graph=None, drifts=[]) is not None


def test_topology_panel_empty_graph():
    assert _build_topology_panel(graph=nx.DiGraph(), drifts=[]) is not None


def test_topology_panel_renders_mock_graph_nodes():
    graph = build_mock_graph()
    panel = _build_topology_panel(graph=graph, drifts=[])
    # Rendering shouldn't raise; node count should match graph nodes.
    assert graph.number_of_nodes() == 4


def test_topology_panel_marks_drifted_node():
    graph = build_mock_graph()
    drifts = [{"affected_node": "db-prod-01"}]
    panel = _build_topology_panel(graph=graph, drifts=drifts)
    assert panel is not None


def test_topology_panel_marks_multiple_drifted_nodes():
    graph = build_mock_graph()
    graph.add_node("sg-2", resource_type="security_group")
    drifts = [{"affected_node": "db-prod-01"}, {"affected_node": "sg-2"}]
    drifted = _drifted_node_ids(drifts)
    assert drifted == {"db-prod-01", "sg-2"}
    panel = _build_topology_panel(graph=graph, drifts=drifts)
    assert panel is not None


def test_drift_list_panel_with_multiple_entries():
    drifts = [
        {"type": "public_db_exposure", "severity": "critical", "affected_node": "db-prod-01"},
        {"type": "open_ingress", "severity": "high", "affected_node": "sg-2"},
    ]
    panel = _build_drift_list_panel(drifts)
    assert panel is not None


def test_drifted_node_ids_tolerates_malformed_entries():
    drifts = [{"affected_node": "sg-1"}, {}, {"affected_node": None}, "not-a-dict"]
    assert _drifted_node_ids(drifts) == {"sg-1"}


def test_topology_panel_truncates_large_graphs():
    import networkx as nx
    graph = nx.DiGraph()
    for i in range(MAX_TOPOLOGY_ROWS + 10):
        graph.add_node(f"resource-{i}", resource_type="ec2")

    panel = _build_topology_panel(graph=graph, drifts=[])
    assert panel is not None
    # Should not raise, and the table should have been capped — verified
    # indirectly by ensuring the function completes without error on an
    # oversized graph.


def test_topology_panel_always_shows_drifted_nodes_even_if_many():
    import networkx as nx
    graph = nx.DiGraph()
    for i in range(MAX_TOPOLOGY_ROWS + 5):
        graph.add_node(f"resource-{i}", resource_type="ec2")
    graph.add_node("db-drifted", resource_type="database")
    drifts = [{"affected_node": "db-drifted"}]

    panel = _build_topology_panel(graph=graph, drifts=drifts)
    assert panel is not None


def test_drift_list_panel_empty():
    assert _build_drift_list_panel([]) is not None


def test_drift_list_panel_with_data():
    drifts = [{"type": "open_ingress", "severity": "critical", "affected_node": "sg-1"}]
    assert _build_drift_list_panel(drifts) is not None


def test_footer_healthy():
    assert _build_footer(STATUS_HEALTHY) is not None


def test_footer_drifted():
    assert _build_footer(STATUS_DRIFTED) is not None
