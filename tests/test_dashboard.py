"""Rich dashboard rendering: topology tree, drift highlighting, panels, diff table."""
from rich.console import Console

from aerodrift.cli.dashboard import (
    _drifted_node_ids, _drifted_rules, build_dashboard,
    build_diff_table, build_layout, build_topology_tree, render_dashboard,
)
from aerodrift.graph.topology import build_mock_graph, detect_drift, diff_topologies


def _render(renderable, width=160, color=False):
    con = Console(record=True, width=width, color_system="truecolor" if color else None, force_terminal=color)
    con.print(renderable)
    return con, con.export_text()


def test_drifted_node_ids_includes_sg_and_target(mock_graph):
    drifts = detect_drift(mock_graph)
    ids = _drifted_node_ids(drifts)
    assert "sg-db" in ids and "db-prod-01" in ids


def test_drifted_node_ids_tolerates_malformed():
    assert _drifted_node_ids(None) == set()
    assert _drifted_node_ids(["junk", 3, None, {}, {"affected_node": None}]) == set()
    assert _drifted_node_ids([{"affected_node": "sg-1"}]) == {"sg-1"}


def test_drifted_rules(mock_graph):
    rules = _drifted_rules(detect_drift(mock_graph))
    assert any(sg == "sg-db" and "0.0.0.0/0" in rule for sg, rule in rules)
    assert _drifted_rules([{"offending_edge": "not-a-dict"}]) == set()


def test_tree_contains_topology(mock_graph):
    _, text = _render(build_topology_tree(mock_graph, detect_drift(mock_graph)))
    for name in ("Internet", "vpc", "db-prod-01", "web-01", "app-01"):
        assert name.lower() in text.lower()


def test_drifted_resources_are_red(mock_graph):
    drifts = detect_drift(mock_graph)
    con = Console(width=160)
    segments = list(con.render(build_topology_tree(mock_graph, drifts)))
    red = [s.text for s in segments if s.style and s.style.color and s.style.color.name == "red"]
    joined = " ".join(red)
    assert "db-prod-01" in joined and "db-sg" in joined
    assert "web-02" not in joined and "app-01" not in joined  # healthy resources stay plain


def test_healthy_tree_has_no_red_markers(healthy_graph):
    _, text = _render(build_topology_tree(healthy_graph, detect_drift(healthy_graph)))
    assert "✗" not in text


def test_empty_graph_tree_renders():
    _, text = _render(build_topology_tree(None, []))
    assert text.strip()


def test_dashboard_drifted_panels(mock_graph):
    drifts = detect_drift(mock_graph)
    _, text = _render(build_dashboard(mock_graph, drifts, info="hello-info", subtitle="sub-x"))
    assert "hello-info" in text and "sub-x" in text
    assert "DRIFT DETECTED" in text
    assert "public_db_exposure" in text or "db exposure" in text.lower()


def test_dashboard_healthy_status(healthy_graph):
    _, text = _render(build_dashboard(healthy_graph, []))
    assert "no drift detected" in text


def test_dashboard_with_records(mock_graph):
    from aerodrift.remediation.engine import remediate
    drifts = detect_drift(mock_graph)
    records = [remediate(d, None, dry_run=True) for d in drifts]
    _, text = _render(build_dashboard(mock_graph, drifts, records))
    assert "validated" in text.lower()


def test_build_layout_alias():
    assert build_layout is build_dashboard


def test_render_dashboard_to_console(mock_graph):
    con = Console(record=True, width=160)
    render_dashboard(mock_graph, detect_drift(mock_graph), out=con)
    assert "db-prod-01" in con.export_text()


def test_diff_table_shows_changes(mock_graph, healthy_graph):
    diff = diff_topologies(healthy_graph, mock_graph)
    _, text = _render(build_diff_table(diff, "before", "after"))
    assert "0.0.0.0/0" in text
    assert "exposed" in text.lower()


def test_diff_table_empty(healthy_graph):
    diff = diff_topologies(healthy_graph, healthy_graph)
    assert diff.is_empty
    _, text = _render(build_diff_table(diff))
    assert "no" in text.lower()


def test_narrow_terminal_stacks_panels(mock_graph):
    _, text = _render(build_dashboard(mock_graph, detect_drift(mock_graph)), width=90)
    assert "public_db_exposure" in text and "Attack paths" in text
    assert max(len(l) for l in text.splitlines()) <= 90
