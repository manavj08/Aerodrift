import unittest

from aerodrift.graph.builder import build_graph
from aerodrift.graph.detector import detect_drift


class TestDriftDetection(unittest.TestCase):

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

    def test_internet_to_database_drift(self):

        drifts = detect_drift(self.graph)

        self.assertEqual(len(drifts), 1)

    def test_affected_database(self):

        drifts = detect_drift(self.graph)

        self.assertEqual(
            drifts[0]["affected_node"],
            "database"
        )

    def test_drift_type(self):

        drifts = detect_drift(self.graph)

        self.assertEqual(
            drifts[0]["type"],
            "public-subnet-exposure"
        )

    def test_drift_severity(self):

        drifts = detect_drift(self.graph)

        self.assertEqual(
            drifts[0]["severity"],
            "high"
        )

    def test_detected_path(self):

        drifts = detect_drift(self.graph)

        self.assertEqual(
            drifts[0]["path"],
            [
                "internet",
                "web-server",
                "database"
            ]
        )

    def test_no_drift_when_path_removed(self):

        self.graph.remove_edge(
            "web-server",
            "database"
        )

        drifts = detect_drift(self.graph)

        self.assertEqual(
            len(drifts),
            0
        )


if __name__ == "__main__":
    unittest.main()