import networkx as nx


def detect_drift(graph):
    """
    Detect security drift in the cloud topology.

    Looks for paths from the Internet to private database resources.
    """

    drifts = []

    # Find internet nodes
    internet_nodes = [
        node
        for node, data in graph.nodes(data=True)
        if data.get("cidr") == "0.0.0.0/0"
        or data.get("resource_type") == "internet"
    ]

    # Find private database nodes
    database_nodes = [
        node
        for node, data in graph.nodes(data=True)
        if data.get("resource_type") in ("rds", "database")
        and data.get("exposure") == "private"
    ]

    # Check every Internet -> database path
    for internet in internet_nodes:
        for database in database_nodes:

            if nx.has_path(graph, internet, database):

                path = nx.shortest_path(
                    graph,
                    internet,
                    database
                )

                offending_edges = []

                for source, target in zip(path, path[1:]):
                    edge_data = graph[source][target]

                    offending_edges.append({
                        "source": source,
                        "target": target,
                        "port": edge_data.get("port"),
                        "protocol": edge_data.get("protocol"),
                        "direction": edge_data.get("direction")
                    })

                drift_type = classify_drift(
                    graph,
                    database
                )

                drifts.append({
                    "type": drift_type,
                    "affected_node": database,
                    "path": path,
                    "offending_edges": offending_edges,
                    "severity": "high"
                })

    return drifts


def classify_drift(graph, database_node):
    """
    Classify the detected security drift.
    """

    database_data = graph.nodes[database_node]

    if database_data.get("exposure") == "private":
        return "public-subnet-exposure"

    return "open-ingress"