"""Rich terminal dashboard for AeroDrift.

Renders the NetworkX topology as a text tree (Internet exposure first,
then VPC -> subnet -> resource, then each VPC's security groups and
their rules), with drifted security groups, rules and exposed resources
highlighted in red. Side panels show the drift list, the exact attack
path(s), and the remediation log. ``build_dashboard`` returns a single
renderable so it works for one-shot printing and inside ``rich.live``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from aerodrift.config import (
    INTERNET_NODE,
    TYPE_EC2,
    TYPE_RDS,
    TYPE_SECURITY_GROUP,
    TYPE_SUBNET,
    TYPE_VPC,
)

console = Console()

STATUS_HEALTHY = "healthy"
STATUS_DRIFTED = "drifted"
MAX_TREE_RESOURCES = 40
_SEV_STYLE = {"critical": "bold white on red", "high": "bold red", "medium": "yellow", "low": "green"}
# Single-width glyphs only: emoji widths vary by terminal and break borders.
_ICONS = {TYPE_VPC: "▣ ", TYPE_SUBNET: "▢ ", TYPE_EC2: "● ", TYPE_RDS: "◆ ", TYPE_SECURITY_GROUP: "◇ "}


# ----------------------------------------------------------------- helpers
def _drifted_node_ids(drifts: list) -> set:
    """Security groups and resources implicated by drift (tolerates bad entries)."""
    ids = set()
    for d in drifts or []:
        if not isinstance(d, dict):
            continue
        for key in ("affected_node", "target_resource"):
            if d.get(key):
                ids.add(d[key])
    return ids


def _drifted_rules(drifts: list) -> set:
    out = set()
    for d in drifts or []:
        if isinstance(d, dict) and isinstance(d.get("offending_edge"), dict):
            out.add((d.get("affected_node"), d["offending_edge"].get("rule")))
    return out


def _name(graph, node):
    return graph.nodes[node].get("name", node) if node in graph else str(node)


def _edges_of(graph, node, kind, reverse=False):
    it = graph.in_edges(node, data=True) if reverse else graph.out_edges(node, data=True)
    return [(u, v, d) for u, v, d in it if d.get("kind") == kind]


def _label(graph, node, drifted, extra=""):
    a = graph.nodes[node]
    rtype = a.get("resource_type", "unknown")
    icon = _ICONS.get(rtype, "• ")
    name = a.get("name", node)
    ident = f" [dim]{node}[/dim]" if name != node else ""
    lock = " [magenta]sensitive[/magenta]" if a.get("sensitive") else ""
    if node in drifted:
        return f"{icon}[bold red]{name}[/bold red]{ident} [red]({rtype}){lock} DRIFTED[/red]{extra}"
    return f"{icon}[bold]{name}[/bold]{ident} [dim]({rtype})[/dim]{lock}{extra}"


# ------------------------------------------------------------------ panels
def _build_header(subtitle: str | None = None) -> Panel:
    title = Text("AeroDrift", style="bold cyan")
    title.append("  —  Agentic Cloud Topology & Remediation", style="cyan")
    if subtitle:
        title.append(f"   ·   {subtitle}", style="dim")
    return Panel(title, box=box.HEAVY, style="bold")


def build_topology_tree(graph=None, drifts: list | None = None) -> Tree:
    drifts = drifts or []
    drifted = _drifted_node_ids(drifts)
    bad_rules = _drifted_rules(drifts)
    root = Tree("[bold]Cloud topology[/bold]", guide_style="grey50")
    if graph is None or graph.number_of_nodes() == 0:
        root.add("[dim](no data yet)[/dim]")
        return root

    # Internet exposure
    if INTERNET_NODE in graph:
        inet = root.add("◎ [bold]Internet[/bold] [dim]0.0.0.0/0[/dim]")
        exposures = _edges_of(graph, INTERNET_NODE, "ingress")
        if not exposures:
            inet.add("[dim]no public ingress[/dim]")
        for _, sg, data in sorted(exposures, key=lambda e: _name(graph, e[1])):
            parts = []
            for r in data.get("rules", []):
                rule = r.get("rule", "?")
                port = rule.split(":", 1)[-1]
                parts.append(f"[bold red]{port}[/bold red]" if (sg, rule) in bad_rules else f"[green]{port}[/green]")
            inet.add(f"→ {_label(graph, sg, drifted)}  {' '.join(parts)}")

    # VPC -> subnet -> resource
    vpcs = [n for n, a in graph.nodes(data=True) if a.get("resource_type") == TYPE_VPC]
    placed = set()
    shown = 0
    for vpc in sorted(vpcs, key=lambda n: _name(graph, n)):
        a = graph.nodes[vpc]
        vbranch = root.add(_label(graph, vpc, drifted, f" [dim]{a.get('cidr', '')}[/dim]"))
        subnets = [v for _, v, _ in _edges_of(graph, vpc, "contains")]
        for sn in sorted(subnets, key=lambda n: _name(graph, n)):
            children = [v for _, v, _ in _edges_of(graph, sn, "contains")]
            if not children:
                continue
            sbranch = vbranch.add(_label(graph, sn, drifted, f" [dim]{graph.nodes[sn].get('cidr', '')}[/dim]"))
            for res in sorted(children, key=lambda n: _name(graph, n)):
                placed.add(res)
                if shown >= MAX_TREE_RESOURCES:
                    continue
                shown += 1
                sgs = [u for u, _, _ in _edges_of(graph, res, "attached", reverse=True)]
                sg_txt = ", ".join(
                    f"[red]{_name(graph, s)}[/red]" if s in drifted else _name(graph, s) for s in sgs)
                sbranch.add(_label(graph, res, drifted, f"  [cyan]⟵ {sg_txt}[/cyan]" if sgs else ""))
        # security groups of this VPC
        groups = [n for n, x in graph.nodes(data=True)
                  if x.get("resource_type") == TYPE_SECURITY_GROUP and x.get("vpc_id") == vpc]
        if groups:
            gbranch = vbranch.add("◇ [bold]Security groups[/bold]")
            for sg in sorted(groups, key=lambda n: _name(graph, n)):
                placed.add(sg)
                sgb = gbranch.add(_label(graph, sg, drifted))
                seen = set()
                for u, _, d in _edges_of(graph, sg, "ingress", reverse=True):
                    for r in d.get("rules", []):
                        rule = r.get("rule", "?")
                        if rule in seen:
                            continue
                        seen.add(rule)
                        shown_rule = rule
                        if r.get("source_kind") == "group" and r.get("source") in graph:
                            shown_rule = rule.replace(r["source"], _name(graph, r["source"]), 1)
                        if (sg, rule) in bad_rules:
                            sgb.add(f"[bold red]✗ allow {shown_rule}  ← DRIFT[/bold red]")
                        else:
                            sgb.add(f"[green]✓[/green] allow {shown_rule}")
                if not seen:
                    sgb.add("[dim]no ingress[/dim]")

    # anything not placed (mock graphs, resources without subnet info)
    others = [n for n, a in graph.nodes(data=True)
              if n not in placed and n != INTERNET_NODE and a.get("resource_type") not in (TYPE_VPC, TYPE_SUBNET)]
    if others:
        obr = root.add("[bold]Other resources[/bold]")
        for n in sorted(others, key=str)[: max(MAX_TREE_RESOURCES - shown, 5)]:
            obr.add(_label(graph, n, drifted))
    if shown >= MAX_TREE_RESOURCES:
        hidden = len([n for n in placed if graph.nodes[n].get("resource_type") in (TYPE_EC2, TYPE_RDS)]) - shown
        if hidden > 0:
            root.add(f"[dim]… {hidden} more resource(s) not shown[/dim]")
    return root


def _build_topology_panel(graph=None, drifts: list | None = None) -> Panel:
    drifts = drifts or []
    n = len(_drifted_node_ids(drifts))
    subtitle = f"[red]{n} resource(s) implicated in drift[/red]" if drifts else "[green]no drift[/green]"
    return Panel(build_topology_tree(graph, drifts), title="Topology", subtitle=subtitle,
                 border_style="red" if drifts else "green")


def _build_drift_list_panel(drifts: list | None = None) -> Panel:
    drifts = [d for d in (drifts or []) if isinstance(d, dict)]
    if not drifts:
        return Panel(Text("No drift detected.", style="dim green"), title="Drift", border_style="grey50")
    table = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False)
    table.add_column("Sev", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("SG", overflow="fold")
    table.add_column("Rule", no_wrap=True)
    for d in drifts:
        sev = d.get("severity", "?")
        edge = d.get("offending_edge") or {}
        table.add_row(Text(sev.upper(), style=_SEV_STYLE.get(sev, "")), d.get("type", "?"),
                      f"[red]{d.get('affected_name', d.get('affected_node', '?'))}[/red]", edge.get("rule", "?"))
    return Panel(table, title=f"Drift ({len(drifts)})", border_style="red")


def _build_path_panel(drifts: list | None = None) -> Panel:
    drifts = [d for d in (drifts or []) if isinstance(d, dict) and d.get("path_names")]
    if not drifts:
        return Panel(Text("No internet path to a sensitive resource.", style="dim green"),
                     title="Attack paths", border_style="grey50")
    lines = Text()
    seen = set()
    for d in drifts:
        key = tuple(d["path_names"])
        if key in seen:
            continue
        seen.add(key)
        rule_port = (d.get("offending_edge") or {}).get("rule", "").split(":", 1)[-1]
        for i, name in enumerate(d["path_names"]):
            style = "bold red" if i == len(d["path_names"]) - 1 else ("red" if i == 1 else "white")
            lines.append(name, style=style)
            if i < len(d["path_names"]) - 1:
                lines.append(f" ─{rule_port}→ " if i == 0 else " → ", style="dim")
        lines.append("\n")
    return Panel(lines, title="Attack paths", border_style="red")


def _build_remediation_panel(records: list | None = None) -> Panel:
    records = records or []
    if not records:
        return Panel(Text("No remediation actions yet.", style="dim"), title="Remediation log", border_style="grey50")
    table = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False)
    table.add_column("Action")
    table.add_column("Target")
    table.add_column("Result", no_wrap=True)
    for r in records[-8:]:
        rec = r.to_dict() if hasattr(r, "to_dict") else r
        drift = rec.get("drift", {})
        status = rec.get("status") or rec.get("result", {}).get("status", "?")
        verified = rec.get("verified")
        style = "green" if status in ("success", "noop") else ("yellow" if status == "validated" else "red")
        tag = " ✔ verified" if verified else (" ✘ not verified" if verified is False else "")
        table.add_row(f"revoke {(drift.get('offending_edge') or {}).get('rule', '?')}",
                      drift.get("affected_name", drift.get("affected_node", "?")),
                      Text(f"{status}{tag}", style=style))
    return Panel(table, title="Remediation log", border_style="green")


def _build_footer(status: str = STATUS_HEALTHY, info: str | None = None) -> Panel:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    style = "green" if status == STATUS_HEALTHY else "bold red"
    label = "OK — no drift detected" if status == STATUS_HEALTHY else "DRIFT DETECTED"
    text = f"Status: {label}   |   Last checked: {now}"
    if info:
        text += f"   |   {info}"
    return Panel(text, style=style)


def build_dashboard(graph=None, drifts: list | None = None, records: list | None = None,
                    info: str | None = None, subtitle: str | None = None) -> Group:
    drifts = drifts or []
    status = STATUS_DRIFTED if drifts else STATUS_HEALTHY
    body = _ResponsiveBody(_build_topology_panel(graph, drifts),
                           Group(_build_drift_list_panel(drifts), _build_path_panel(drifts),
                                 _build_remediation_panel(records)))
    return Group(_build_header(subtitle), body, _build_footer(status, info))


SIDE_BY_SIDE_MIN_WIDTH = 150


class _ResponsiveBody:
    """Two columns on wide terminals, stacked panels on narrow ones."""

    def __init__(self, left, right):
        self.left, self.right = left, right

    def __rich_console__(self, console, options):
        if options.max_width >= SIDE_BY_SIDE_MIN_WIDTH:
            grid = Table.grid(expand=True, padding=(0, 1))
            grid.add_column(ratio=3)
            grid.add_column(ratio=2)
            grid.add_row(self.left, self.right)
            yield grid
        else:
            yield self.left
            yield self.right


# Backwards-compatible name used by earlier weeks' code/tests.
build_layout = build_dashboard


def render_dashboard(graph=None, drifts=None, records=None, info=None, subtitle=None, out: Console | None = None):
    (out or console).print(build_dashboard(graph, drifts, records, info, subtitle))


def render_shell(graph=None, drifts: list | None = None) -> None:
    render_dashboard(graph=graph, drifts=drifts)


def build_diff_table(diff, label_a: str = "A", label_b: str = "B") -> Panel:
    """Render a TopologyDiff as a colour-coded change table."""
    table = Table(box=box.SIMPLE_HEAD, expand=True)
    table.add_column("", width=2)
    table.add_column("Change")
    table.add_column("Detail")
    for n in diff.added_nodes:
        table.add_row("[green]+[/green]", "resource added", f"{n['name']} ({n['resource_type']})")
    for n in diff.removed_nodes:
        table.add_row("[red]-[/red]", "resource removed", f"{n['name']} ({n['resource_type']})")
    for r in diff.added_rules:
        table.add_row("[green]+[/green]", "ingress rule", f"{r['rule']} → {r['target_name']} [dim](from {r['source_name']})[/dim]")
    for r in diff.removed_rules:
        table.add_row("[red]-[/red]", "ingress rule", f"{r['rule']} → {r['target_name']} [dim](from {r['source_name']})[/dim]")
    for l in diff.added_links:
        table.add_row("[green]+[/green]", f"{l['kind']} link", f"{l['source_name']} → {l['target_name']}")
    for l in diff.removed_links:
        table.add_row("[red]-[/red]", f"{l['kind']} link", f"{l['source_name']} → {l['target_name']}")
    for n in diff.newly_exposed:
        table.add_row("[bold red]![/bold red]", "[bold red]newly internet-exposed[/bold red]", n)
    for n in diff.no_longer_exposed:
        table.add_row("[green]✓[/green]", "exposure closed", n)
    if diff.is_empty:
        table.add_row("", "[dim]no changes[/dim]", "")
    return Panel(table, title=f"Topology diff: {label_a} → {label_b}", subtitle=diff.summary())


if __name__ == "__main__":
    from aerodrift.graph.topology import build_mock_graph, detect_drift
    g = build_mock_graph()
    render_dashboard(g, detect_drift(g))
