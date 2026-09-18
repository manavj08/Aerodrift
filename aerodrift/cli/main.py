"""AeroDrift CLI entrypoint.

Run with:
    python -m aerodrift.cli.main <command> [options]

Command bodies are stubs until their owning week's logic lands, but the
argument surface here is the real interface later weeks will implement
against.
"""

import argparse
import json
import sys
import time

from aerodrift import __version__
from aerodrift.cli.dashboard import render_shell
from aerodrift.graph.topology import build_mock_graph, detect_drift, INTERNET_NODE
from aerodrift.remediation.codegen import (
    generate_remediation_code,
    UnsupportedDriftTypeError,
    MissingDriftFieldError,
)

SAMPLE_DRIFTS = [
    {
        "drift_id": "drift-001",
        "type": "open_ingress",
        "affected_node": "sg-0a1b2c3",
        "offending_edge": {"source": "0.0.0.0/0", "target": "sg-0a1b2c3", "rule": "0.0.0.0/0:22/tcp"},
        "severity": "critical",
        "detected_at": "2026-09-10T09:00:00Z",
    },
    {
        "drift_id": "drift-002",
        "type": "public_db_exposure",
        "affected_node": "db-prod-01",
        "offending_edge": {"source": "0.0.0.0/0", "target": "db-prod-01", "rule": "0.0.0.0/0:5432/tcp"},
        "severity": "critical",
        "detected_at": "2026-09-10T09:01:00Z",
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aerodrift",
        description="AeroDrift — Agentic Cloud Topology & Remediation Engine",
    )
    parser.add_argument(
        "--version", action="version", version=f"aerodrift {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_p = subparsers.add_parser(
        "scan", help="Scan cloud state and render topology (Week 2)"
    )
    scan_p.add_argument(
        "--watch", action="store_true", help="Continuously re-scan and refresh the dashboard"
    )
    scan_p.add_argument(
        "--demo-data",
        action="store_true",
        help="Use sample drift data instead of live detect_drift() output "
        "(useful until Person B's real detection lands)",
    )

    status_p = subparsers.add_parser(
        "status", help="Show current drift status (Week 2)"
    )
    status_p.add_argument(
        "--json", action="store_true", help="Output drift status as JSON instead of a table"
    )
    status_p.add_argument(
        "--demo-data",
        action="store_true",
        help="Use sample drift data instead of live detect_drift() output "
        "(useful until Person B's real detection lands)",
    )

    remediate_p = subparsers.add_parser(
        "remediate", help="Generate and run a remediation (Week 3)"
    )
    remediate_p.add_argument("--sg-id", help="Security group ID to remediate")
    remediate_p.add_argument("--rule", help="Offending rule identifier to revoke")
    remediate_p.add_argument(
        "--dry-run", action="store_true", help="Generate remediation code without executing it"
    )

    report_p = subparsers.add_parser(
        "report", help="Generate a PDF incident report (Week 4)"
    )
    report_p.add_argument(
        "--output", default="incident_report.pdf", help="Output path for the PDF report"
    )

    demo_p = subparsers.add_parser(
        "demo", help="Render the dashboard with sample drift data (Week 1 preview)"
    )
    demo_p.add_argument(
        "--healthy", action="store_true", help="Render the healthy (no-drift) state instead"
    )

    subparsers.add_parser(
        "mid-review-demo",
        help="Scripted joint-demo flow: drift a mock SG, detect, show red, timed (Week 2 checkpoint)",
    )

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        print(f"[verbose] command: {args.command}")

    if args.command == "scan":
        graph = build_mock_graph()
        drifts = SAMPLE_DRIFTS if args.demo_data else detect_drift(graph)
        if args.watch:
            print("[stub] --watch: continuous re-scan loop not implemented yet.")
        render_shell(graph=graph, drifts=drifts)
    elif args.command == "status":
        graph = build_mock_graph()
        drifts = SAMPLE_DRIFTS if args.demo_data else detect_drift(graph)
        if args.json:
            print(json.dumps(drifts, indent=2))
        else:
            if not drifts:
                print("No drift detected.")
            else:
                for d in drifts:
                    print(f"[{d.get('severity', '?')}] {d.get('type', '?')} — {d.get('affected_node', '?')}")
    elif args.command == "remediate":
        if not args.sg_id or not args.rule:
            print("error: --sg-id and --rule are required", file=sys.stderr)
            return 2
        drift = {
            "type": "open_ingress",
            "affected_node": args.sg_id,
            "offending_edge": {"source": INTERNET_NODE, "target": args.sg_id, "rule": args.rule},
        }
        try:
            code = generate_remediation_code(drift)
        except (UnsupportedDriftTypeError, MissingDriftFieldError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Generated remediation code:\n  {code}")
        if args.dry_run:
            print("(dry-run: not executed — sandbox execution lands Week 3 Day 2+)")
        else:
            print("(sandbox execution not implemented yet — this will run in Week 3)")
    elif args.command == "report":
        print(f"[stub] report: would write to {args.output} — not implemented yet (Week 4).")
    elif args.command == "demo":
        drifts = [] if args.healthy else SAMPLE_DRIFTS
        graph = build_mock_graph()
        render_shell(graph=graph, drifts=drifts)
    elif args.command == "mid-review-demo":
        run_mid_review_demo()

    return 0


def run_mid_review_demo() -> None:
    """Scripted flow for the Week 2 mid-project review:
    drift a mock SG -> detect under 5s -> Rich dashboard shows red.

    Scenario (per the project spec): an engineer accidentally opens a
    security group directly to the internet, creating a new path to the
    production database. This mirrors "is there a path from the Internet
    to Database X?" — the project's core use case.
    """
    print("Step 1/3: Building baseline topology...")
    graph = build_mock_graph()
    render_shell(graph=graph, drifts=detect_drift(graph))

    print(
        "\nStep 2/3: Simulating drift — an engineer opens a new security "
        "group directly to the internet, which sits in front of the "
        "database..."
    )
    # "Drift a mock SG": a new SG is opened to 0.0.0.0/0, and it fronts
    # the database, creating a new internet -> DB path.
    graph.add_node("sg-drift-demo", resource_type="security_group")
    graph.add_edge(INTERNET_NODE, "sg-drift-demo", rule="0.0.0.0/0:0-65535/tcp")
    graph.add_edge("sg-drift-demo", "db-prod-01", rule="internal")

    print("Step 3/3: Detecting drift...")
    start = time.monotonic()
    drifts = detect_drift(graph)
    elapsed = time.monotonic() - start
    print(f"Detection completed in {elapsed:.3f}s (target: <5s)\n")

    render_shell(graph=graph, drifts=drifts)


if __name__ == "__main__":
    sys.exit(main())
