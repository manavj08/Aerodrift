NODE_FIELDS = {
    "id": "Unique resource ID",
    "type": "Cloud resource type",
    "name": "Resource name",
    "exposure": "public or private",
    "cidr": "Network CIDR"
}


EDGE_FIELDS = {
    "source": "Source resource ID",
    "target": "Target resource ID",
    "port": "Network port",
    "protocol": "Network protocol",
    "direction": "Network direction"
}


DRIFT_FIELDS = {
    "type": "Drift type",
    "affected_node": "Resource affected by drift",
    "offending_edge": "Edge causing exposure",
    "severity": "Drift severity"
}