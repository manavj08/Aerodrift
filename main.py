from aerodrift.graph.builder import build_graph
from sample_data import resources, connections


graph = build_graph(resources, connections)

print("Nodes:")
for node, data in graph.nodes(data=True):
    print(node, data)

print("\nEdges:")
for source, target, data in graph.edges(data=True):
    print(source, "->", target, data)