import networkx as nx
from ingestion.mock_client import get_mock_ec2_state, get_mock_ec2_state_fixed
from ingestion.graph_builder import build_graph


def refresh_state(fixed: bool = False) -> nx.DiGraph:
    """
    Re-polls infrastructure state and rebuilds the graph.
    fixed=True simulates polling AFTER a remediation action.
    """
    if fixed:
        resources, relationships = get_mock_ec2_state_fixed()
    else:
        resources, relationships = get_mock_ec2_state()

    return build_graph(resources, relationships)


if __name__ == "__main__":
    before = refresh_state(fixed=False)
    after = refresh_state(fixed=True)
    print("Before:", dict(before.nodes(data=True)))
    print("After:", dict(after.nodes(data=True)))