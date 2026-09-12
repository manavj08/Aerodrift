"""Placeholder — owned by Person B.

Will model cloud state as a NetworkX directed graph and expose
drift detection queries. Not implemented by Person C.

The mock graph and drift-detection logic below are representative (per
CONTRACT.md and the project spec's "0.0.0.0/0 -> DB path-finding" use
case) so Person C's dashboard/CLI have real behavior to demo before B's
real module lands. Swap this file out entirely once B delivers — the
public function signatures (build_mock_graph, detect_drift) are the
contract seam.
"""

from datetime import datetime, timezone

import networkx as nx

INTERNET_NODE = "0.0.0.0/0"
SENSITIVE_RESOURCE_TYPES = {"database"}


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
    graph.add_node(INTERNET_NODE, resource_type="internet")
    graph.add_node("sg-0a1b2c3", resource_type="security_group")
    graph.add_node("ec2-app-01", resource_type="ec2")
    graph.add_node("db-prod-01", resource_type="database")

    graph.add_edge(INTERNET_NODE, "sg-0a1b2c3", rule="0.0.0.0/0:22/tcp")
    graph.add_edge("sg-0a1b2c3", "ec2-app-01", rule="internal")
    graph.add_edge("ec2-app-01", "db-prod-01", rule="internal")
    # Simulated drift: internet directly reaching the database.
    graph.add_edge(INTERNET_NODE, "db-prod-01", rule="0.0.0.0/0:5432/tcp")

    return graph


def detect_drift(graph: "nx.DiGraph") -> list:
    """Detect drift: any path from the internet node to a sensitive
    resource (currently: database nodes), per the project's core use case.

    This is Person C's placeholder implementation of Person B's real
    Week 2 task ("drift detection queries... 0.0.0.0/0 -> DB
    path-finding"). Replace with B's real module — the shape of the
    returned drift objects follows CONTRACT.md so downstream code
    (dashboard, codegen) does not need to change when B's version lands.
    """
    if INTERNET_NODE not in graph:
        return []

    drifts = []
    now = datetime.now(timezone.utc).isoformat()

    for node_id, attrs in graph.nodes(data=True):
        if node_id == INTERNET_NODE:
            continue
        if attrs.get("resource_type") not in SENSITIVE_RESOURCE_TYPES:
            continue
        if not nx.has_path(graph, INTERNET_NODE, node_id):
            continue

        # Prefer a direct edge (the classic misconfig) if one exists;
        # otherwise report the shortest path's first hop as the rule context.
        if graph.has_edge(INTERNET_NODE, node_id):
            rule = graph.edges[INTERNET_NODE, node_id].get("rule", "unknown")
            offending_edge = {"source": INTERNET_NODE, "target": node_id, "rule": rule}
            drift_type = "public_db_exposure" if attrs.get("resource_type") == "database" else "open_ingress"
        else:
            path = nx.shortest_path(graph, INTERNET_NODE, node_id)
            first_hop_target = path[1]
            rule = graph.edges[INTERNET_NODE, first_hop_target].get("rule", "unknown")
            offending_edge = {"source": INTERNET_NODE, "target": first_hop_target, "rule": rule}
            drift_type = "indirect_exposure"

        drifts.append(
            {
                "drift_id": f"drift-{node_id}",
                "type": drift_type,
                "affected_node": node_id,
                "offending_edge": offending_edge,
                "severity": "critical",
                "detected_at": now,
            }
        )

    return drifts
