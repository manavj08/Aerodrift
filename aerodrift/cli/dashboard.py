"""Rich dashboard rendering for AeroDrift.

Week 1: layout shell only, no live data.
Week 2: renders Person B's NetworkX graph + drift output, per the
locked data contract (see CONTRACT.md). Currently wired against the
placeholder graph in aerodrift/graph/topology.py until B delivers.
"""

from datetime import datetime, timezone

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

STATUS_HEALTHY = "healthy"
STATUS_DRIFTED = "drifted"


def _build_header() -> Panel:
    title = Text("AeroDrift", style="bold cyan")
    title.append("  —  Cloud Topology & Remediation", style="cyan")
    return Panel(title, style="bold")


def _drifted_node_ids(drifts: list) -> set:
    """Extract the set of affected_node ids from drift objects (per CONTRACT.md).

    Tolerates malformed entries (missing/None affected_node) so a single
    bad drift object from Person B's future implementation doesn't crash
    dashboard rendering.
    """
    ids = set()
    for d in drifts:
        node_id = d.get("affected_node") if isinstance(d, dict) else None
        if node_id:
            ids.add(node_id)
    return ids


MAX_TOPOLOGY_ROWS = 25


def _build_topology_panel(graph=None, drifts: list | None = None) -> Panel:
    """Render actual graph nodes as rows, highlighting drifted ones in red.

    Args:
        graph: a networkx.DiGraph (or None if no graph is available yet).
        drifts: drift objects (per CONTRACT.md) used to mark rows red.

    Drifted nodes are always shown; if the graph has more healthy nodes
    than fit, they're truncated with a note rather than rendering an
    unbounded table (defensive for Person B's real, likely larger graph).
    """
    drifts = drifts or []
    drifted_ids = _drifted_node_ids(drifts)

    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Resource")
    table.add_column("Type")
    table.add_column("Status")

    if graph is None or graph.number_of_nodes() == 0:
        table.add_row("(no data yet)", "—", "—")
    else:
        nodes = list(graph.nodes(data=True))
        # Show all drifted nodes first, then fill remaining rows with
        # healthy nodes up to the cap.
        drifted_nodes = [(n, a) for n, a in nodes if n in drifted_ids]
        healthy_nodes = [(n, a) for n, a in nodes if n not in drifted_ids]
        remaining = max(MAX_TOPOLOGY_ROWS - len(drifted_nodes), 0)
        shown = drifted_nodes + healthy_nodes[:remaining]
        hidden_count = len(nodes) - len(shown)

        for node_id, attrs in shown:
            resource_type = attrs.get("resource_type", "unknown")
            if node_id in drifted_ids:
                table.add_row(f"[red]{node_id}[/red]", resource_type, "[bold red]DRIFTED[/bold red]")
            else:
                table.add_row(str(node_id), resource_type, "[green]healthy[/green]")

        if hidden_count > 0:
            table.add_row(f"[dim]... {hidden_count} more healthy resource(s)[/dim]", "", "")

    footer = Text(f"\n{len(drifted_ids)} drifted resource(s)", style="red" if drifted_ids else "green")
    return Panel(table, title="Topology", subtitle=str(footer) if drifted_ids else None)


def _build_drift_list_panel(drifts: list | None = None) -> Panel:
    """Drift list populated from Person B's detect_drift() output
    (shape locked in CONTRACT.md).
    """
    drifts = drifts or []
    if not drifts:
        body = Text("No drift detected.", style="dim green")
    else:
        lines = [
            f"[{d.get('severity', '?')}] {d.get('type', '?')} — {d.get('affected_node', '?')}"
            for d in drifts
        ]
        body = Text("\n".join(lines), style="red")
    return Panel(body, title="Drift", border_style="red" if drifts else "grey50")


def _build_footer(status: str = STATUS_HEALTHY) -> Panel:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    style = "green" if status == STATUS_HEALTHY else "bold red"
    label = "OK — no drift detected" if status == STATUS_HEALTHY else "DRIFT DETECTED"
    return Panel(f"Status: {label}   |   Last checked: {now}", style=style)


def build_layout(graph=None, drifts: list | None = None) -> Layout:
    """Return the dashboard layout.

    Args:
        graph: optional networkx.DiGraph from Person B (placeholder for now).
        drifts: optional list of drift objects (see CONTRACT.md).
    """
    drifts = drifts or []
    status = STATUS_DRIFTED if drifts else STATUS_HEALTHY

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="topology", ratio=2),
        Layout(name="drift_list", ratio=1),
    )

    layout["header"].update(_build_header())
    layout["topology"].update(_build_topology_panel(graph=graph, drifts=drifts))
    layout["drift_list"].update(_build_drift_list_panel(drifts))
    layout["footer"].update(_build_footer(status))

    return layout


def render_shell(graph=None, drifts: list | None = None) -> None:
    """Print the dashboard once."""
    console.print(build_layout(graph=graph, drifts=drifts))


if __name__ == "__main__":
    render_shell()
