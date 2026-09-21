import networkx as nx
from ingestion.schema import Resource, Relationship


def build_graph(resources: list[Resource], relationships: list[Relationship]) -> nx.DiGraph:
    """
    Converts ingested resources and relationships into a NetworkX directed graph.

    Node key = resource_id
    Node data = resource_type + attributes
    Edge = source_id -> target_id, with relation_type + attributes as edge data
    """
    graph = nx.DiGraph()

    for resource in resources:
        graph.add_node(
            resource.resource_id,
            resource_type=resource.resource_type,
            **resource.attributes,
        )

    for rel in relationships:
        graph.add_edge(
            rel.source_id,
            rel.target_id,
            relation_type=rel.relation_type,
            **rel.attributes,
        )

    return graph


if __name__ == "__main__":
    from ingestion.mock_client import get_mock_ec2_state

    resources, relationships = get_mock_ec2_state()
    graph = build_graph(resources, relationships)

    print(f"Nodes ({graph.number_of_nodes()}):")
    for node_id, data in graph.nodes(data=True):
        print(" ", node_id, data)

    print(f"Edges ({graph.number_of_edges()}):")
    for source, target, data in graph.edges(data=True):
        print(" ", f"{source} -> {target}", data)