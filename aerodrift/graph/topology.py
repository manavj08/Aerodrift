"""Placeholder — owned by Person B.

Will model cloud state as a NetworkX directed graph and expose
drift detection queries. Not implemented by Person C.

The mock graph below is representative (per CONTRACT.md) so Person C's
dashboard has real-shaped data to render before B's real module lands.
Swap this file out entirely once B delivers.
"""

import networkx as nx


def build_empty_graph() -> "nx.DiGraph":
    """Placeholder empty graph so Person C's dashboard can run standalone."""
    return nx.DiGraph()


def build_mock_graph() -> "nx.DiGraph":
    """A small representative cloud topology for dashboard development.

    Nodes carry `resource_type` (e.g. "internet", "security_group", "database")
    per the shape Person B is expected to use. Replace with B's real
    ingestion-backed graph once delivered.
    """
    graph = nx.DiGraph()
    graph.add_node("0.0.0.0/0", resource_type="internet")
    graph.add_node("sg-0a1b2c3", resource_type="security_group")
    graph.add_node("ec2-app-01", resource_type="ec2")
    graph.add_node("db-prod-01", resource_type="database")

    graph.add_edge("0.0.0.0/0", "sg-0a1b2c3", rule="0.0.0.0/0:22/tcp")
    graph.add_edge("sg-0a1b2c3", "ec2-app-01", rule="internal")
    graph.add_edge("ec2-app-01", "db-prod-01", rule="internal")
    # Simulated drift: internet directly reaching the database.
    graph.add_edge("0.0.0.0/0", "db-prod-01", rule="0.0.0.0/0:5432/tcp")

    return graph


def detect_drift(graph: "nx.DiGraph") -> list:
    """Placeholder — returns no drift until Person B implements this."""
    return []
