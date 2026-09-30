import json
import time

import networkx as nx
import pytest

from aerodrift.config import INTERNET_NODE
from aerodrift.graph.topology import (
    build_mock_graph,
    build_topology,
    detect_drift,
    diff_topologies,
    exposure_paths,
    graph_from_dict,
    graph_to_dict,
    mock_cloud_state,
    reachability_view,
)
from aerodrift.ingestion.rules import IngressRule
from aerodrift.ingestion.schema import REL_ALLOWS_INGRESS, REL_ATTACHED_TO, Relationship, Resource


# ------------------------------------------------------------------ build
def test_edge_kinds(healthy_graph):
    g = healthy_graph
    assert g.edges["vpc-prod", "subnet-public-a"]["kind"] == "contains"
    assert g.edges["sg-db", "db-prod-01"]["kind"] == "attached"
    assert g.edges[INTERNET_NODE, "sg-web"]["kind"] == "ingress"
    assert {r["rule"] for r in g.edges[INTERNET_NODE, "sg-web"]["rules"]} == {"0.0.0.0/0:443/tcp", "0.0.0.0/0:80/tcp"}


def test_security_group_reference_expands_to_member_instances(healthy_graph):
    assert healthy_graph.has_edge("i-web-01", "sg-app") and healthy_graph.has_edge("i-web-02", "sg-app")
    assert healthy_graph.edges["i-app-01", "sg-db"]["rules"][0]["via_group"] == "sg-app"


def test_private_cidr_rule_expands_to_instances_in_range(healthy_graph):
    rules = {r["rule"] for r in healthy_graph.edges["i-web-01", "sg-app"]["rules"]}
    assert "10.0.0.0/16:22/tcp" in rules


def test_nodes_are_typed_and_sensitivity_flagged(healthy_graph):
    assert healthy_graph.nodes["db-prod-01"]["resource_type"] == "rds"
    assert healthy_graph.nodes["db-prod-01"]["sensitive"] is True
    assert healthy_graph.nodes["i-web-01"]["sensitive"] is False


def test_type_aliases_are_normalised():
    g = build_topology(([Resource("sg-1", "SecurityGroup"), Resource("i-1", "EC2Instance"),
                         Resource("db", "database")], []))
    assert [g.nodes[n]["resource_type"] for n in ("sg-1", "i-1", "db")] == ["security_group", "ec2", "rds"]


def test_contains_edges_are_not_traffic(healthy_graph):
    view = reachability_view(healthy_graph)
    assert not view.has_edge("vpc-prod", "subnet-public-a")
    assert view.has_edge("sg-db", "db-prod-01")


def test_baseline_has_a_tiered_path_to_db_but_no_drift(healthy_graph):
    assert nx.has_path(reachability_view(healthy_graph), INTERNET_NODE, "db-prod-01")
    assert detect_drift(healthy_graph) == []
    assert detect_drift(healthy_graph, baseline=healthy_graph) == []


# ------------------------------------------------------------------ drift
def test_public_db_exposure_reports_the_security_group(mock_graph):
    d = next(x for x in detect_drift(mock_graph) if x["type"] == "public_db_exposure")
    assert d["affected_node"] == "sg-db"
    assert d["target_resource"] == "db-prod-01"
    assert d["severity"] == "critical"
    assert d["offending_edge"] == {"source": INTERNET_NODE, "target": "sg-db", "rule": "0.0.0.0/0:5432/tcp"}
    assert d["path"] == [INTERNET_NODE, "sg-db", "db-prod-01"]
    assert d["remediation"]["action"] == "revoke_security_group_ingress"


def test_open_admin_port_is_high(mock_graph):
    d = next(x for x in detect_drift(mock_graph) if x["type"] == "open_ingress")
    assert (d["affected_node"], d["offending_edge"]["rule"], d["severity"]) == ("sg-web", "0.0.0.0/0:22/tcp", "high")


def test_drifts_follow_contract_shape(mock_graph):
    for d in detect_drift(mock_graph):
        assert {"drift_id", "type", "affected_node", "offending_edge", "severity", "detected_at"} <= d.keys()
        assert {"source", "target", "rule"} <= d["offending_edge"].keys()


def test_drifts_sorted_by_severity(mock_graph):
    assert [d["severity"] for d in detect_drift(mock_graph)] == ["critical", "high"]


def test_drift_ids_are_stable_across_scans(mock_graph):
    assert [d["drift_id"] for d in detect_drift(mock_graph)] == [d["drift_id"] for d in detect_drift(build_mock_graph())]


def _with_rules(*extra):
    state = mock_cloud_state(drifted=False)
    for src, sg, text in extra:
        state.relationships.append(Relationship(src, sg, REL_ALLOWS_INGRESS, IngressRule.parse(text).to_dict()))
    return build_topology(state)


def test_public_non_admin_port_on_web_tier_is_not_drift():
    assert detect_drift(_with_rules((INTERNET_NODE, "sg-web", "0.0.0.0/0:8443/tcp"))) == []


def test_all_ports_open_is_critical_open_ingress():
    (d,) = detect_drift(_with_rules((INTERNET_NODE, "sg-app", "0.0.0.0/0:all/all")))
    assert (d["type"], d["severity"], d["affected_node"]) == ("open_ingress", "critical", "sg-app")


def test_ipv6_public_rule_is_detected():
    (d,) = detect_drift(_with_rules((INTERNET_NODE, "sg-db", "::/0:5432/tcp")))
    assert d["type"] == "public_db_exposure"


def test_indirect_exposure_needs_a_baseline(healthy_graph):
    g = _with_rules((INTERNET_NODE, "sg-app", "0.0.0.0/0:8080/tcp"))
    assert detect_drift(g) == []  # not a policy violation on its own
    (d,) = detect_drift(g, baseline=healthy_graph)
    assert d["type"] == "indirect_exposure"
    assert d["affected_node"] == "sg-app" and d["target_resource"] == "db-prod-01"
    assert d["path"] == [INTERNET_NODE, "sg-app", "i-app-01", "sg-db", "db-prod-01"]


def test_indirect_supersedes_open_ingress_for_same_rule(healthy_graph):
    g = _with_rules((INTERNET_NODE, "sg-app", "0.0.0.0/0:all/all"))
    (d,) = detect_drift(g, baseline=healthy_graph)
    assert (d["type"], d["severity"]) == ("indirect_exposure", "critical")


def test_new_security_group_attached_to_db_is_detected():
    state = mock_cloud_state(drifted=False)
    state.resources.append(Resource("sg-temp", "security_group", {"name": "temp", "vpc_id": "vpc-prod"}))
    state.relationships += [Relationship("db-prod-01", "sg-temp", REL_ATTACHED_TO),
                            Relationship(INTERNET_NODE, "sg-temp", REL_ALLOWS_INGRESS,
                                         IngressRule.parse("0.0.0.0/0:5432/tcp").to_dict())]
    (d,) = detect_drift(build_topology(state))
    assert d["affected_node"] == "sg-temp" and d["type"] == "public_db_exposure"


def test_sensitive_tag_marks_ec2_as_sensitive():
    state = mock_cloud_state(drifted=False)
    for r in state.resources:
        if r.resource_id == "i-app-01":
            r.attributes["tags"] = {"aerodrift:sensitive": "true"}
    state.relationships.append(Relationship(INTERNET_NODE, "sg-app", REL_ALLOWS_INGRESS,
                                            IngressRule.parse("0.0.0.0/0:8080/tcp").to_dict()))
    (d,) = detect_drift(build_topology(state))
    assert d["type"] == "public_db_exposure" and d["target_resource"] == "i-app-01"


def test_no_internet_node_or_empty_graph():
    assert detect_drift(nx.DiGraph()) == []
    g = build_mock_graph()
    g.remove_node(INTERNET_NODE)
    assert detect_drift(g) == []


def test_exposure_paths(mock_graph):
    assert exposure_paths(mock_graph)["db-prod-01"] == [INTERNET_NODE, "sg-db", "db-prod-01"]


def test_detection_is_fast_on_a_large_graph():
    """Mid-review requirement: detection < 5 s. 5,000 tiers => ~20k nodes."""
    g = nx.DiGraph()
    g.add_node(INTERNET_NODE, resource_type="internet", sensitive=False)
    for i in range(5000):
        sg, inst, dsg, db = f"sg-{i}", f"i-{i}", f"sgdb-{i}", f"db-{i}"
        for n, t in ((sg, "security_group"), (inst, "ec2"), (dsg, "security_group"), (db, "rds")):
            g.add_node(n, resource_type=t, sensitive=(t == "rds"))
        g.add_edge(INTERNET_NODE, sg, kind="ingress", rules=[IngressRule.parse("0.0.0.0/0:443/tcp").to_dict()])
        g.add_edge(sg, inst, kind="attached")
        g.add_edge(inst, dsg, kind="ingress", rules=[IngressRule.parse(f"{sg}:5432/tcp").to_dict()])
        g.add_edge(dsg, db, kind="attached")
    g.add_edge(INTERNET_NODE, "sgdb-4999", kind="ingress", rules=[IngressRule.parse("0.0.0.0/0:5432/tcp").to_dict()])
    base = g.copy()
    base.remove_edge(INTERNET_NODE, "sgdb-4999")
    start = time.perf_counter()
    drifts = detect_drift(g, baseline=base)
    elapsed = time.perf_counter() - start
    assert [d["affected_node"] for d in drifts] == ["sgdb-4999"]
    assert elapsed < 5.0, f"detection took {elapsed:.2f}s"


# ------------------------------------------------------------------ diff / serialisation
def test_diff_between_healthy_and_drifted(healthy_graph, mock_graph):
    diff = diff_topologies(healthy_graph, mock_graph)
    assert {r["rule"] for r in diff.added_rules} == {"0.0.0.0/0:5432/tcp", "0.0.0.0/0:22/tcp"}
    assert diff.newly_exposed == ["db-prod-01"]
    assert not diff.removed_rules and not diff.added_nodes
    back = diff_topologies(mock_graph, healthy_graph)
    assert back.no_longer_exposed == ["db-prod-01"] and len(back.removed_rules) == 2


def test_diff_of_identical_graphs_is_empty(mock_graph):
    diff = diff_topologies(mock_graph, build_mock_graph())
    assert diff.is_empty and diff.summary() == "no topology changes"


def test_diff_detects_added_nodes_and_links(healthy_graph):
    g = healthy_graph.copy()
    g.add_node("sg-new", resource_type="security_group", name="new")
    g.add_edge("sg-new", "db-prod-01", kind="attached")
    diff = diff_topologies(healthy_graph, g)
    assert diff.added_nodes[0]["id"] == "sg-new" and diff.added_links[0]["kind"] == "attached"


def test_graph_serialisation_round_trip(mock_graph):
    data = json.loads(json.dumps(graph_to_dict(mock_graph)))
    g2 = graph_from_dict(data)
    assert diff_topologies(mock_graph, g2).is_empty
    assert detect_drift(g2)[0]["drift_id"] == detect_drift(mock_graph)[0]["drift_id"]


def test_real_pipeline_simulated_cloud(collector, cloud):
    base = build_topology(collector.collect_sync())
    assert detect_drift(base, baseline=base) == []
    cloud.inject_drift("open-db")
    g = build_topology(collector.collect_sync())
    (d,) = detect_drift(g, baseline=base)
    assert d["affected_node"] == cloud.ids["sg_db"] and d["target_resource"] == "db-prod-01"


@pytest.mark.parametrize("scenario,expected_type", [("open-db", "public_db_exposure"),
                                                    ("shadow-sg", "public_db_exposure"),
                                                    ("open-all-app", "indirect_exposure"),
                                                    ("open-ssh", "indirect_exposure")])
def test_every_simulated_scenario_is_detected(collector, cloud, scenario, expected_type):
    base = build_topology(collector.collect_sync())
    inj = cloud.inject_drift(scenario)
    drifts = detect_drift(build_topology(collector.collect_sync()), baseline=base)
    assert [(d["type"], d["affected_node"], d["offending_edge"]["rule"]) for d in drifts] == \
        [(expected_type, inj.group_id, inj.rule)]
