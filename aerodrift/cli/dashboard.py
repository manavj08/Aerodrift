"""Rich dashboard rendering for AeroDrift.

Week 1: layout shell only, no live data.
Week 2: wired to Person B's NetworkX graph + drift output.
"""

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel

console = Console()


def build_layout() -> Layout:
    """Return the dashboard layout shell (no live data yet)."""
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

    layout["header"].update(Panel("AeroDrift — Cloud Topology & Remediation", style="bold cyan"))
    layout["topology"].update(Panel("Topology view (coming Week 2)", title="Topology"))
    layout["drift_list"].update(Panel("Drift list (coming Week 2)", title="Drift"))
    layout["footer"].update(Panel("Status: OK", style="green"))

    return layout


def render_shell() -> None:
    """Print the static dashboard shell once."""
    console.print(build_layout())


if __name__ == "__main__":
    render_shell()
