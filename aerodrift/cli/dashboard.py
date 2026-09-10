"""Rich dashboard rendering for AeroDrift.

Week 1: layout shell only, no live data.
Week 2: wired to Person B's NetworkX graph + drift output, per the
locked data contract (see CONTRACT.md).
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


def _build_topology_panel(drift_count: int = 0) -> Panel:
    """Placeholder topology panel. Week 2 replaces the body with the
    real graph render, using drift objects per CONTRACT.md to decide
    which nodes render red (drifted) vs default (healthy).
    """
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Resource")
    table.add_column("Status")
    table.add_row("(no data yet)", "—")

    footer = Text(f"\n{drift_count} drifted resource(s)", style="red" if drift_count else "green")
    return Panel(table, title="Topology", subtitle=str(footer) if drift_count else None)


def _build_drift_list_panel(drifts: list | None = None) -> Panel:
    """Placeholder drift list. Week 2 populates from Person B's
    detect_drift() output (shape locked in CONTRACT.md).
    """
    drifts = drifts or []
    if not drifts:
        body = Text("No drift data yet — coming Week 2.", style="dim")
    else:
        body = Text("\n".join(f"[{d.get('severity', '?')}] {d.get('type', '?')}" for d in drifts))
    return Panel(body, title="Drift", border_style="red" if drifts else "grey50")


def _build_footer(status: str = STATUS_HEALTHY) -> Panel:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    style = "green" if status == STATUS_HEALTHY else "bold red"
    label = "OK — no drift detected" if status == STATUS_HEALTHY else "DRIFT DETECTED"
    return Panel(f"Status: {label}   |   Last checked: {now}", style=style)


def build_layout(drifts: list | None = None) -> Layout:
    """Return the dashboard layout.

    Args:
        drifts: optional list of drift objects (see CONTRACT.md). Left
            empty in Week 1 — Week 2 wires this to Person B's graph.
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
    layout["topology"].update(_build_topology_panel(drift_count=len(drifts)))
    layout["drift_list"].update(_build_drift_list_panel(drifts))
    layout["footer"].update(_build_footer(status))

    return layout


def render_shell(drifts: list | None = None) -> None:
    """Print the dashboard once."""
    console.print(build_layout(drifts))


if __name__ == "__main__":
    render_shell()
