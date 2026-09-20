"""Bridge between Person A's ingestion output and Person B's graph builder input.

TEMPORARY — this adapter exists because CONTRACT.md never actually pinned
down an ingestion -> graph shape. Person A's `get_mock_ec2_state()` returns
`Resource`/`Relationship` dataclasses (aerodrift.ingestion.schema); Person
B's `build_graph()` (aerodrift.graph.builder) expects plain dicts with a
different, non-overlapping set of keys (`id`/`type`/`name`/`exposure`/`cidr`
for resources, `source`/`target`/`port`/`protocol`/`direction` for
connections). Feeding one into the other directly raises immediately.

This module is a stopgap so the pipeline runs end-to-end today. It is not
a substitute for Person A and Person B agreeing on one real shape — see
CONTRACT.md's open items. Expect this file to be deleted once they do.

Fields Person B's schema expects that Person A's schema has no equivalent
for (`name`, `exposure`, `cidr`, `port`, `protocol`, `direction`) are
filled with best-effort defaults pulled from `Resource.attributes` /
`Relationship.attributes` where present, else a sentinel value — they are
NOT guaranteed accurate and should not be trusted for anything beyond
keeping the demo pipeline running.

SECOND WORKAROUND (added after the first pipeline landed): running the
adapter's output through `detect_drift()` found ZERO drift even though
Person A's mock security group has a genuinely open `0.0.0.0/0:22`
ingress rule. Cause: `detect_drift()` only searches from a literal graph
node named "0.0.0.0/0" (topology.INTERNET_NODE), and nothing in this
pipeline ever created that node — the open-ingress fact was sitting
unused in `Resource.attributes["ingress"]` as a string. `_synthesize_internet_exposure()`
below parses that string and adds the missing internet node/edge so the
known-drifted mock resource is actually detected. This is a workaround,
not a real ingestion feature: it only recognizes the exact
"{cidr}:{port}" string format Person A's mock_client.py currently
produces, and does nothing for any other ingress representation. Delete
this once Person A/B agree on a real way to represent public exposure
in the graph.
"""

from aerodrift.graph.topology import INTERNET_NODE
from aerodrift.ingestion.schema import Resource, Relationship

PUBLIC_CIDR = "0.0.0.0/0"


def _synthesize_internet_exposure(
    resources: list[Resource], resource_dicts: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Detect resources whose `ingress` attribute shows a public
    (0.0.0.0/0) rule, and synthesize the internet node + an edge to them
    so `detect_drift()` can actually find this exposure.

    Only understands the "{cidr}:{port}" ingress string format produced
    by `mock_client.get_mock_ec2_state()` today. Anything else is left
    alone (not an error — just not recognized as public exposure yet).
    """
    extra_resource_dicts = []
    extra_connection_dicts = []
    internet_node_needed = False

    for resource in resources:
        ingress = resource.attributes.get("ingress")
        if not ingress or ":" not in ingress:
            continue
        cidr, _, port = ingress.partition(":")
        if cidr != PUBLIC_CIDR:
            continue

        internet_node_needed = True
        extra_connection_dicts.append(
            {
                "source": INTERNET_NODE,
                "target": resource.resource_id,
                "port": port or 0,
                "protocol": "tcp",
                "direction": "inbound",
            }
        )

    if internet_node_needed:
        extra_resource_dicts.append(
            {
                "id": INTERNET_NODE,
                "type": "internet",
                "name": "Internet",
                "exposure": "public",
                "cidr": PUBLIC_CIDR,
            }
        )

    return resource_dicts + extra_resource_dicts, extra_connection_dicts


def resources_to_graph_input(
    resources: list[Resource], relationships: list[Relationship]
) -> tuple[list[dict], list[dict]]:
    """Convert Person A's dataclasses into the dict shape Person B's
    `build_graph(resources, connections)` expects.
    """
    resource_dicts = [
        {
            "id": r.resource_id,
            "type": r.resource_type,
            "name": r.attributes.get("name", r.resource_id),
            "exposure": r.attributes.get("exposure", "unknown"),
            "cidr": r.attributes.get("cidr"),
        }
        for r in resources
    ]

    connection_dicts = [
        {
            "source": rel.source_id,
            "target": rel.target_id,
            "port": rel.attributes.get("port", 0),
            "protocol": rel.attributes.get("protocol", "unknown"),
            "direction": rel.attributes.get("direction", "outbound"),
        }
        for rel in relationships
    ]

    resource_dicts, internet_connection_dicts = _synthesize_internet_exposure(
        resources, resource_dicts
    )
    connection_dicts = connection_dicts + internet_connection_dicts

    return resource_dicts, connection_dicts
