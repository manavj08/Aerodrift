import os
import sys
import unittest

# Ensure AeroDrift root is in Python module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aerodrift.graph.builder import build_graph


class TestGraphConstruction(unittest.TestCase):

    def setUp(self):
        self.resources = [
            {
                "id": "internet",
                "type": "internet",
                "name": "Internet",
                "exposure": "public",
                "cidr": "0.0.0.0/0"
            },
            {
                "id": "web-server",
                "type": "ec2",
                "name": "Web Server",
                "exposure": "public",
                "cidr": "10.0.1.0/24"
            },
            {
                "id": "database",
                "type": "rds",
                "name": "Private Database",
                "exposure": "private",
                "cidr": "10.0.2.0/24"
            }
        ]

        self.connections = [
            {
                "source": "internet",
                "target": "web-server",
                "port": 80,
                "protocol": "TCP",
                "direction": "inbound"
            },
            {
                "source": "web-server",
                "target": "database",
                "port": 5432,
                "protocol": "TCP",
                "direction": "outbound"
            }
        ]

        self.graph = build_graph(
            self.resources,
            self.connections
        )

    def test_nodes_are_created(self):
        self.assertEqual(len(self.graph.nodes), 3)

        self.assertIn("internet", self.graph.nodes)
        self.assertIn("web-server", self.graph.nodes)
        self.assertIn("database", self.graph.nodes)

    def test_node_attributes(self):
        database = self.graph.nodes["database"]

        self.assertEqual(database["resource_type"], "rds")
        self.assertEqual(database["name"], "Private Database")
        self.assertEqual(database["exposure"], "private")

    def test_edges_are_created(self):
        self.assertEqual(len(self.graph.edges), 2)

        self.assertTrue(
            self.graph.has_edge(
                "internet",
                "web-server"
            )
        )

        self.assertTrue(
            self.graph.has_edge(
                "web-server",
                "database"
            )
        )

    def test_edge_attributes(self):
        edge = self.graph["web-server"]["database"]

        self.assertEqual(edge["port"], 5432)
        self.assertEqual(edge["protocol"], "TCP")
        self.assertEqual(edge["direction"], "outbound")


if __name__ == "__main__":
    unittest.main()