"""Topology engine: cloud state -> NetworkX DiGraph -> drift.

Graph model
-----------
Nodes are resources (``resource_type`` in config's canonical names).
Every edge carries a ``kind``:

* ``contains``  vpc -> subnet -> ec2/rds       (placement, NOT traffic)
* ``attached``  security group -> resource     (traffic entering the SG reaches the resource)
* ``ingress``   source -> security group       (a rule lets the source in; ``rules`` lists them)

Ingress sources are expanded to concrete nodes: the internet node for
0.0.0.0/0 and ::/0, every member of a referenced security group, and
every instance whose private IP falls inside a referenced private CIDR.

Only ``ingress`` + ``attached`` edges carry traffic, so all path-finding
runs on :func:`reachability_view`. "Is there a path from the Internet to
Database X?" is then literally ``nx.has_path(view, INTERNET_NODE, X)``.

Modelling note: an SG rule open to 0.0.0.0/0 is treated as internet
exposure without also checking route tables / public IPs. That matches
how auditors and AWS Config treat such rules (the rule is the risk), and
is what the project's use case describes.
"""

from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone

import networkx as nx

from aerodrift.config import (
    ADMIN_PORTS,
    DRIFT_INDIRECT,
    DRIFT_OPEN_INGRESS,
    DRIFT_PUBLIC_DB,
    INTERNET_NODE,
    SENSITIVE_RESOURCE_TYPES,
    SENSITIVE_TAG_KEY,
    SENSITIVE_TIER_VALUES,
    SEVERITY_ORDER,
    TYPE_EC2,
    TYPE_INTERNET,
    TYPE_RDS,
    TYPE_SECURITY_GROUP,
    TYPE_SUBNET,
    TYPE_VPC,
    normalize_type,
)
from aerodrift.ingestion.rules import SOURCE_GROUP, IngressRule
from aerodrift.ingestion.schema import (
    REL_ALLOWS_INGRESS,
    REL_ATTACHED_TO,
    REL_CONTAINS,
    CloudState,
    Relationship,
    Resource,
)

KIND_CONTAINS = "contains"
KIND_ATTACHED = "attached"
KIND_INGRESS = "ingress"
TRAFFIC_KINDS = frozenset({KIND_INGRESS, KIND_ATTACHED})

# Kept for backwards compatibility with earlier imports.
__all__ = [
    "INTERNET_NODE", "SENSITIVE_RESOURCE_TYPES", "build_topology", "build_mock_graph",
    "build_empty_graph", "reachability_view", "detect_drift", "diff_topologies",
    "TopologyDiff", "graph_to_dict", "graph_from_dict", "is_sensitive", "exposure_paths",
]


# --------------------------------------------------------------------------- build
def is_sensitive(attrs: dict) -> bool:
    if normalize_type(attrs.get("resource_type")) in SENSITIVE_RESOURCE_TYPES:
        return True
    tags = attrs.get("tags") or {}
    if str(tags.get(SENSITIVE_TAG_KEY, "")).lower() in ("1", "true", "yes"):
        return True
    return str(tags.get("Tier", "")).lower() in SENSITIVE_TIER_VALUES


_NODE_ATTR_KEYS = ("name", "cidr", "vpc_id", "subnet_id", "region", "engine", "instance_type",
                   "private_ip", "public_ip", "group_name", "tags", "publicly_accessible", "az")


def _add_rule(graph, source, target, rule: dict, via: str | None = None):
    rule = dict(rule)
    if via:
        rule["via_group"] = via
    if graph.has_edge(source, target):
        data = graph.edges[source, target]
        if all(r.get("rule") != rule.get("rule") for r in data["rules"]):
            data["rules"].append(rule)
    else:
        graph.add_edge(source, target, kind=KIND_INGRESS, rules=[rule], rule=rule.get("rule"))


def build_topology(state: "CloudState | tuple[list[Resource], list[Relationship]]") -> nx.DiGraph:
    """Build the directed topology graph from ingestion output."""
    if isinstance(state, CloudState):
        resources, relationships = state.resources, state.relationships
        meta = {"collected_at": state.collected_at, "regions": state.regions, "source": state.source}
    else:
        resources, relationships = state
        meta = {}

    graph = nx.DiGraph(**meta)
    for r in resources:
        attrs = {k: r.attributes[k] for k in _NODE_ATTR_KEYS if k in r.attributes}
        attrs["resource_type"] = normalize_type(r.resource_type)
        attrs.setdefault("name", r.resource_id)
        attrs["sensitive"] = is_sensitive(attrs)
        graph.add_node(r.resource_id, **attrs)

    members: dict[str, list[str]] = {}
    for rel in relationships:
        if rel.relation_type == REL_ATTACHED_TO:
            members.setdefault(rel.target_id, []).append(rel.source_id)

    compute_ips = []
    for node, attrs in graph.nodes(data=True):
        if attrs["resource_type"] in (TYPE_EC2, TYPE_RDS) and attrs.get("private_ip"):
            try:
                compute_ips.append((node, ipaddress.ip_address(attrs["private_ip"])))
            except ValueError:
                pass

    for rel in relationships:
        src, dst = rel.source_id, rel.target_id
        if rel.relation_type == REL_CONTAINS:
            if src in graph and dst in graph:
                graph.add_edge(src, dst, kind=KIND_CONTAINS)
        elif rel.relation_type == REL_ATTACHED_TO:
            if src in graph and dst in graph:
                graph.add_edge(dst, src, kind=KIND_ATTACHED)
        elif rel.relation_type == REL_ALLOWS_INGRESS:
            if dst not in graph:
                continue
            rule = rel.attributes or {"rule": f"{src}:unknown"}
            if src == INTERNET_NODE:
                if INTERNET_NODE not in graph:
                    graph.add_node(INTERNET_NODE, resource_type=TYPE_INTERNET, name="Internet",
                                   sensitive=False)
                _add_rule(graph, INTERNET_NODE, dst, rule)
            elif rule.get("source_kind") == SOURCE_GROUP or src.startswith("sg-"):
                for member in members.get(src, []):
                    if member != dst:
                        _add_rule(graph, member, dst, rule, via=src)
            else:
                try:
                    net = ipaddress.ip_network(src, strict=False)
                except ValueError:
                    continue
                for node, ip in compute_ips:
                    if ip.version == net.version and ip in net:
                        _add_rule(graph, node, dst, rule, via=src)
    return graph


def build_empty_graph() -> nx.DiGraph:
    return nx.DiGraph()


def reachability_view(graph: nx.DiGraph):
    """Read-only view with only traffic-carrying edges (ingress + attached)."""
    return nx.subgraph_view(graph, filter_edge=lambda u, v: graph.edges[u, v].get("kind") in TRAFFIC_KINDS)


# ---------------------------------------------------------------------- mock data
def mock_cloud_state(drifted: bool = True) -> CloudState:
    """A fixed, offline copy of the SimulatedCloud estate (stable ids, no moto).

    Used for fast previews (``aerodrift demo``) and unit tests.
    """
    R, Rel = Resource, Relationship
    res = [
        R(INTERNET_NODE, TYPE_INTERNET, {"name": "Internet", "cidr": "0.0.0.0/0"}),
        R("vpc-prod", TYPE_VPC, {"name": "prod-vpc", "cidr": "10.0.0.0/16"}),
        R("subnet-public-a", TYPE_SUBNET, {"name": "public-a", "cidr": "10.0.1.0/24", "vpc_id": "vpc-prod"}),
        R("subnet-app-a", TYPE_SUBNET, {"name": "private-app-a", "cidr": "10.0.2.0/24", "vpc_id": "vpc-prod"}),
        R("subnet-data-a", TYPE_SUBNET, {"name": "private-data-a", "cidr": "10.0.3.0/24", "vpc_id": "vpc-prod"}),
        R("sg-web", TYPE_SECURITY_GROUP, {"name": "web-sg", "vpc_id": "vpc-prod"}),
        R("sg-app", TYPE_SECURITY_GROUP, {"name": "app-sg", "vpc_id": "vpc-prod"}),
        R("sg-db", TYPE_SECURITY_GROUP, {"name": "db-sg", "vpc_id": "vpc-prod"}),
        R("i-web-01", TYPE_EC2, {"name": "web-01", "subnet_id": "subnet-public-a", "vpc_id": "vpc-prod", "private_ip": "10.0.1.10"}),
        R("i-web-02", TYPE_EC2, {"name": "web-02", "subnet_id": "subnet-public-a", "vpc_id": "vpc-prod", "private_ip": "10.0.1.11"}),
        R("i-app-01", TYPE_EC2, {"name": "app-01", "subnet_id": "subnet-app-a", "vpc_id": "vpc-prod", "private_ip": "10.0.2.10"}),
        R("db-prod-01", TYPE_RDS, {"name": "db-prod-01", "engine": "postgres", "vpc_id": "vpc-prod"}),
    ]

    def ingress(src, sg, text):
        return Rel(src, sg, REL_ALLOWS_INGRESS, IngressRule.parse(text).to_dict())

    rels = [
        Rel("vpc-prod", "subnet-public-a", REL_CONTAINS),
        Rel("vpc-prod", "subnet-app-a", REL_CONTAINS),
        Rel("vpc-prod", "subnet-data-a", REL_CONTAINS),
        Rel("subnet-public-a", "i-web-01", REL_CONTAINS),
        Rel("subnet-public-a", "i-web-02", REL_CONTAINS),
        Rel("subnet-app-a", "i-app-01", REL_CONTAINS),
        Rel("subnet-data-a", "db-prod-01", REL_CONTAINS),
        Rel("i-web-01", "sg-web", REL_ATTACHED_TO),
        Rel("i-web-02", "sg-web", REL_ATTACHED_TO),
        Rel("i-app-01", "sg-app", REL_ATTACHED_TO),
        Rel("db-prod-01", "sg-db", REL_ATTACHED_TO),
        ingress(INTERNET_NODE, "sg-web", "0.0.0.0/0:443/tcp"),
        ingress(INTERNET_NODE, "sg-web", "0.0.0.0/0:80/tcp"),
        ingress("sg-web", "sg-app", "sg-web:8080/tcp"),
        ingress("10.0.0.0/16", "sg-app", "10.0.0.0/16:22/tcp"),
        ingress("sg-app", "sg-db", "sg-app:5432/tcp"),
    ]
    if drifted:
        rels.append(ingress(INTERNET_NODE, "sg-db", "0.0.0.0/0:5432/tcp"))
        rels.append(ingress(INTERNET_NODE, "sg-web", "0.0.0.0/0:22/tcp"))
    return CloudState(res, rels, collected_at="2026-01-01T00:00:00+00:00", regions=["mock"], source="mock")


def build_mock_graph(drifted: bool = True) -> nx.DiGraph:
    return build_topology(mock_cloud_state(drifted=drifted))


# ------------------------------------------------------------------------- drift
def _rule_obj(rule: dict) -> IngressRule | None:
    try:
        if "source" in rule and "protocol" in rule:
            return IngressRule.from_dict(rule)
        return IngressRule.parse(rule.get("rule", ""))
    except (ValueError, KeyError):
        return None


def _drift_id(kind, sg, rule, target) -> str:
    digest = hashlib.sha1(f"{kind}|{sg}|{rule}|{target}".encode()).hexdigest()[:10]
    return f"drift-{digest}"


def _name(graph, node):
    return graph.nodes[node].get("name", node) if node in graph else node


def _make_drift(graph, kind, severity, sg, rule, target, path, description, now):
    rule_str = rule.get("rule") or str(_rule_obj(rule))
    return {
        "drift_id": _drift_id(kind, sg, rule_str, target),
        "type": kind,
        "severity": severity,
        "affected_node": sg,
        "affected_name": _name(graph, sg),
        "target_resource": target,
        "target_name": _name(graph, target),
        "offending_edge": {"source": path[path.index(sg) - 1] if sg in path and path.index(sg) else INTERNET_NODE,
                           "target": sg, "rule": rule_str},
        "rule_detail": {k: rule[k] for k in ("source", "protocol", "from_port", "to_port", "source_kind") if k in rule},
        "path": list(path),
        "path_names": [_name(graph, n) for n in path],
        "description": description,
        "detected_at": now,
        "remediation": {"action": "revoke_security_group_ingress", "group_id": sg, "rule": rule_str},
    }


def _ingress_rule_keys(graph) -> set:
    keys = set()
    for u, v, d in graph.edges(data=True):
        if d.get("kind") == KIND_INGRESS:
            for r in d.get("rules", []):
                keys.add((u, v, r.get("rule")))
    return keys


def detect_drift(graph: nx.DiGraph, baseline: nx.DiGraph | None = None,
                 now: str | None = None) -> list[dict]:
    """Detect security drift in a topology graph.

    Always-on policy checks (no baseline needed):
      * ``public_db_exposure`` (critical): a public ingress rule on a
        security group that is attached to a sensitive resource.
      * ``open_ingress``: a public rule on any other SG that opens an
        admin port (high) or every port (critical).

    Baseline-aware check (when ``baseline`` is given):
      * ``indirect_exposure``: a rule that is *new since the baseline*
        and sits on some internet -> sensitive-resource path (e.g. an app
        tier opened to the world, which then reaches the database).

    ``affected_node`` is always the security group to fix, so every drift
    maps to exactly one ``revoke_security_group_ingress`` call.
    """
    if INTERNET_NODE not in graph:
        return []
    now = now or datetime.now(timezone.utc).isoformat()
    view = reachability_view(graph)
    drifts: dict[tuple, dict] = {}

    def attached(sg):
        return [n for n in graph.successors(sg) if graph.edges[sg, n].get("kind") == KIND_ATTACHED]

    # 1 + 2: public rules
    for sg in list(graph.successors(INTERNET_NODE)):
        edge = graph.edges[INTERNET_NODE, sg]
        if edge.get("kind") != KIND_INGRESS:
            continue
        protected = attached(sg)
        sensitive = [n for n in protected if graph.nodes[n].get("sensitive")]
        for rule in edge.get("rules", []):
            ro = _rule_obj(rule)
            rule_str = rule.get("rule") or str(ro)
            if sensitive:
                for target in sensitive:
                    drifts[(sg, rule_str, target)] = _make_drift(
                        graph, DRIFT_PUBLIC_DB, "critical", sg, rule, target,
                        [INTERNET_NODE, sg, target],
                        f"{_name(graph, target)} is reachable from the internet via "
                        f"{_name(graph, sg)} ({rule_str})", now)
                continue
            if ro is None:
                continue
            admin = sorted(p for p in ADMIN_PORTS if ro.covers_port(p))
            if ro.all_ports or admin:
                target = protected[0] if protected else sg
                severity = "critical" if ro.all_ports else "high"
                what = "every port" if ro.all_ports else f"admin port(s) {', '.join(map(str, admin))}"
                drifts[(sg, rule_str, None)] = _make_drift(
                    graph, DRIFT_OPEN_INGRESS, severity, sg, rule, target,
                    [INTERNET_NODE, sg] + ([target] if target != sg else []),
                    f"{_name(graph, sg)} exposes {what} to the internet", now)

    # 3: baseline-aware indirect exposure.
    # Only rules that are new since the baseline can create *new* exposure,
    # so we BFS forward from those few edges instead of walking back from
    # every sensitive node (which is quadratic on large estates).
    if baseline is not None:
        base_keys = _ingress_rule_keys(baseline)
        from_internet = nx.descendants(view, INTERNET_NODE) | {INTERNET_NODE}
        new_edges = [(u, v, rule) for u, v, d in graph.edges(data=True)
                     if d.get("kind") == KIND_INGRESS and u in from_internet
                     for rule in d.get("rules", []) if (u, v, rule.get("rule")) not in base_keys]
        reach_cache: dict[str, list[str]] = {}
        for u, v, rule in new_edges:
            if v not in reach_cache:
                downstream = nx.descendants(view, v) | {v}
                reach_cache[v] = sorted(n for n in downstream if graph.nodes[n].get("sensitive"))
            rule_str = rule.get("rule")
            for target in reach_cache[v]:
                if (v, rule_str, target) in drifts:
                    continue  # already a direct public_db_exposure
                path = nx.shortest_path(view, INTERNET_NODE, u) + nx.shortest_path(view, v, target)
                ro = _rule_obj(rule)
                severity = "critical" if (u == INTERNET_NODE and ro and ro.all_ports) else "high"
                drifts.pop((v, rule_str, None), None)  # supersedes a plain open_ingress
                drifts[(v, rule_str, target)] = _make_drift(
                    graph, DRIFT_INDIRECT, severity, v, rule, target, path,
                    f"new rule {rule_str} on {_name(graph, v)} opens an internet path to "
                    f"{_name(graph, target)} ({len(path) - 1} hops)", now)

    return sorted(drifts.values(), key=lambda d: (SEVERITY_ORDER.get(d["severity"], 9), d["drift_id"]))


def exposure_paths(graph: nx.DiGraph) -> dict[str, list[str]]:
    """Shortest internet path to every sensitive resource that has one."""
    if INTERNET_NODE not in graph:
        return {}
    paths = nx.single_source_shortest_path(reachability_view(graph), INTERNET_NODE)
    return {n: p for n, p in paths.items() if graph.nodes[n].get("sensitive")}


# -------------------------------------------------------------------------- diff
@dataclass
class TopologyDiff:
    added_nodes: list[dict] = field(default_factory=list)
    removed_nodes: list[dict] = field(default_factory=list)
    added_rules: list[dict] = field(default_factory=list)
    removed_rules: list[dict] = field(default_factory=list)
    added_links: list[dict] = field(default_factory=list)
    removed_links: list[dict] = field(default_factory=list)
    newly_exposed: list[str] = field(default_factory=list)
    no_longer_exposed: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(getattr(self, f) for f in self.__dataclass_fields__)

    def summary(self) -> str:
        if self.is_empty:
            return "no topology changes"
        parts = []
        for label, items in (("+nodes", self.added_nodes), ("-nodes", self.removed_nodes),
                             ("+rules", self.added_rules), ("-rules", self.removed_rules),
                             ("+links", self.added_links), ("-links", self.removed_links),
                             ("newly exposed", self.newly_exposed),
                             ("no longer exposed", self.no_longer_exposed)):
            if items:
                parts.append(f"{label}: {len(items)}")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


def diff_topologies(old: nx.DiGraph, new: nx.DiGraph) -> TopologyDiff:
    """Structural + rule-level diff between two topology graphs."""
    diff = TopologyDiff()

    def node_info(g, n):
        a = g.nodes[n]
        return {"id": n, "name": a.get("name", n), "resource_type": a.get("resource_type")}

    diff.added_nodes = [node_info(new, n) for n in new.nodes if n not in old]
    diff.removed_nodes = [node_info(old, n) for n in old.nodes if n not in new]

    def rule_rows(g):
        rows = {}
        for u, v, d in g.edges(data=True):
            if d.get("kind") == KIND_INGRESS:
                for r in d.get("rules", []):
                    rows[(u, v, r.get("rule"))] = {
                        "source": u, "source_name": g.nodes[u].get("name", u),
                        "target": v, "target_name": g.nodes[v].get("name", v), "rule": r.get("rule"),
                    }
        return rows

    old_r, new_r = rule_rows(old), rule_rows(new)
    diff.added_rules = [new_r[k] for k in new_r if k not in old_r]
    diff.removed_rules = [old_r[k] for k in old_r if k not in new_r]

    def links(g):
        return {(u, v): {"source": u, "target": v, "kind": d.get("kind"),
                         "source_name": g.nodes[u].get("name", u), "target_name": g.nodes[v].get("name", v)}
                for u, v, d in g.edges(data=True) if d.get("kind") != KIND_INGRESS}

    old_l, new_l = links(old), links(new)
    diff.added_links = [new_l[k] for k in new_l if k not in old_l]
    diff.removed_links = [old_l[k] for k in old_l if k not in new_l]

    def direct_exposed(g):
        return {d["target_resource"] for d in detect_drift(g) if d["type"] == DRIFT_PUBLIC_DB}

    old_e, new_e = direct_exposed(old), direct_exposed(new)
    diff.newly_exposed = sorted(new_e - old_e)
    diff.no_longer_exposed = sorted(old_e - new_e)
    return diff


# ------------------------------------------------------------------- serialisation
def graph_to_dict(graph: nx.DiGraph) -> dict:
    return {
        "graph": dict(graph.graph),
        "nodes": [{"id": n, **a} for n, a in graph.nodes(data=True)],
        "edges": [{"source": u, "target": v, **d} for u, v, d in graph.edges(data=True)],
    }


def graph_from_dict(data: dict) -> nx.DiGraph:
    graph = nx.DiGraph(**data.get("graph", {}))
    for node in data.get("nodes", []):
        node = dict(node)
        graph.add_node(node.pop("id"), **node)
    for edge in data.get("edges", []):
        edge = dict(edge)
        graph.add_edge(edge.pop("source"), edge.pop("target"), **edge)
    return graph
