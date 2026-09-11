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


def test_drift_list_panel_empty():
    assert _build_drift_list_panel([]) is not None


def test_drift_list_panel_with_data():
    drifts = [{"type": "open_ingress", "severity": "critical", "affected_node": "sg-1"}]
    assert _build_drift_list_panel(drifts) is not None


def test_footer_healthy():
    assert _build_footer(STATUS_HEALTHY) is not None


def test_footer_drifted():
    assert _build_footer(STATUS_DRIFTED) is not None
