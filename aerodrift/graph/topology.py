"""Placeholder — owned by Person B.

Will model cloud state as a NetworkX directed graph and expose
drift detection queries. Not implemented by Person C.
"""

import networkx as nx


def build_empty_graph() -> "nx.DiGraph":
    """Placeholder empty graph so Person C's dashboard can run standalone."""
    return nx.DiGraph()


def detect_drift(graph: "nx.DiGraph") -> list:
    """Placeholder — returns no drift until Person B implements this."""
    return []
