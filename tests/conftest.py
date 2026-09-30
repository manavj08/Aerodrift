import os

import pytest

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def cloud():
    from aerodrift.ingestion.simulated_cloud import SimulatedCloud
    with SimulatedCloud() as c:
        yield c


@pytest.fixture
def collector(cloud):
    from aerodrift.ingestion.collector import AWSCollector
    return AWSCollector(cloud.session, regions=[cloud.region])


@pytest.fixture
def mock_graph():
    from aerodrift.graph.topology import build_mock_graph
    return build_mock_graph()


@pytest.fixture
def healthy_graph():
    from aerodrift.graph.topology import build_mock_graph
    return build_mock_graph(drifted=False)
