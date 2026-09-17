import networkx as nx


def build_graph(resources, connections):
    """
    Build a directed cloud topology graph.

    Nodes represent cloud resources.
    Edges represent network reachability paths.
    """

    graph = nx.DiGraph()

    # Add cloud resources as nodes
    for resource in resources:
        graph.add_node(
            resource["id"],
            resource_type=resource["type"],
            name=resource["name"],
            exposure=resource["exposure"],
            cidr=resource.get("cidr")
        )

    # Add network reachability edges
    for connection in connections:
        graph.add_edge(
            connection["source"],
            connection["target"],
            port=connection["port"],
            protocol=connection["protocol"],
            direction=connection.get("direction", "outbound")
        )

    return graph