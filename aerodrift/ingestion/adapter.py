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
"""

from aerodrift.ingestion.schema import Resource, Relationship


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

    return resource_dicts, connection_dicts
