"""Tests for aerodrift.graph.topology placeholder — Week 2 Day 1.

NOTE: this module is Person B's responsibility. These tests only cover
Person C's placeholder mock data used to develop the dashboard before
B's real module lands. Delete this file once B's tests replace it.
"""

import networkx as nx

from aerodrift.graph.topology import build_empty_graph, build_mock_graph


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
