"""Tests for aerodrift.graph.topology placeholder — Week 2 Day 3.

NOTE: this module is Person B's responsibility. These tests only cover
Person C's placeholder mock data + drift-detection logic used to develop
the dashboard/CLI before B's real module lands. Delete this file once
B's tests replace it.
"""

import networkx as nx

from aerodrift.graph.topology import build_empty_graph, build_mock_graph, detect_drift


def test_build_empty_graph_returns_digraph():
    graph = build_empty_graph()
    assert isinstance(graph, nx.DiGraph)
    assert graph.number_of_nodes() == 0


def test_build_mock_graph_has_expected_nodes():
    graph = build_mock_graph()
    assert graph.number_of_nodes() == 4
    assert "db-prod-01" in graph.nodes
    assert "sg-0a1b2c3" in graph.nodes


def test_build_mock_graph_nodes_have_resource_type():
    graph = build_mock_graph()
    for _, attrs in graph.nodes(data=True):
        assert "resource_type" in attrs


def test_build_mock_graph_has_edges():
    graph = build_mock_graph()
    assert graph.number_of_edges() == 4
    assert graph.has_edge("0.0.0.0/0", "db-prod-01")  # simulated drift edge


def test_detect_drift_empty_graph_returns_no_drift():
    assert detect_drift(build_empty_graph()) == []


def test_detect_drift_graph_without_internet_node_returns_no_drift():
    graph = nx.DiGraph()
    graph.add_node("db-1", resource_type="database")
    assert detect_drift(graph) == []


def test_detect_drift_finds_direct_internet_to_db_path():
    graph = build_mock_graph()
    drifts = detect_drift(graph)
    assert len(drifts) == 1
    assert drifts[0]["affected_node"] == "db-prod-01"
    assert drifts[0]["type"] == "public_db_exposure"
    assert drifts[0]["severity"] == "critical"
    assert drifts[0]["offending_edge"]["rule"] == "0.0.0.0/0:5432/tcp"


def test_detect_drift_no_drift_when_no_path_to_sensitive_node():
    graph = nx.DiGraph()
    graph.add_node("0.0.0.0/0", resource_type="internet")
    graph.add_node("db-isolated", resource_type="database")
    # No edge at all — DB is unreachable from the internet.
    assert detect_drift(graph) == []


def test_detect_drift_ignores_non_sensitive_resources():
    graph = nx.DiGraph()
    graph.add_node("0.0.0.0/0", resource_type="internet")
    graph.add_node("ec2-1", resource_type="ec2")
    graph.add_edge("0.0.0.0/0", "ec2-1", rule="0.0.0.0/0:80/tcp")
    # EC2 is reachable but not in SENSITIVE_RESOURCE_TYPES.
    assert detect_drift(graph) == []


def test_detect_drift_indirect_path_reports_first_hop():
    graph = nx.DiGraph()
    graph.add_node("0.0.0.0/0", resource_type="internet")
    graph.add_node("sg-1", resource_type="security_group")
    graph.add_node("db-1", resource_type="database")
    graph.add_edge("0.0.0.0/0", "sg-1", rule="0.0.0.0/0:22/tcp")
    graph.add_edge("sg-1", "db-1", rule="internal")
    drifts = detect_drift(graph)
    assert len(drifts) == 1
    assert drifts[0]["type"] == "indirect_exposure"
    assert drifts[0]["offending_edge"]["target"] == "sg-1"


def test_detect_drift_runs_under_5_seconds_on_larger_graph():
    """Mid-project review checkpoint: drift detection under 5 seconds."""
    import time

    graph = nx.DiGraph()
    graph.add_node("0.0.0.0/0", resource_type="internet")
    # Build a 500-node chain plus one exposed database to simulate a
    # larger topology than the 4-node mock graph.
    prev = "0.0.0.0/0"
    for i in range(500):
        node = f"resource-{i}"
        graph.add_node(node, resource_type="ec2")
        graph.add_edge(prev, node, rule="internal")
        prev = node
    graph.add_node("db-far", resource_type="database")
    graph.add_edge(prev, "db-far", rule="internal")

    start = time.monotonic()
    drifts = detect_drift(graph)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0
    assert len(drifts) == 1
    assert drifts[0]["affected_node"] == "db-far"
