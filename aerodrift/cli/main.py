"""AeroDrift CLI entrypoint.

Run with:
    python -m aerodrift.cli.main <command> [options]

Command bodies are stubs until their owning week's logic lands, but the
argument surface here is the real interface later weeks will implement
against.
"""

import argparse
import sys

from aerodrift import __version__


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

    status_p = subparsers.add_parser(
        "status", help="Show current drift status (Week 2)"
    )
    status_p.add_argument(
        "--json", action="store_true", help="Output drift status as JSON instead of a table"
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

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        print(f"[verbose] command: {args.command}")

    if args.command == "scan":
        mode = "watch mode" if args.watch else "single scan"
        print(f"[stub] scan ({mode}): dashboard rendering not implemented yet (Week 2).")
    elif args.command == "status":
        fmt = "JSON" if args.json else "table"
        print(f"[stub] status ({fmt}): drift status not implemented yet (Week 2).")
    elif args.command == "remediate":
        if not args.sg_id or not args.rule:
            print("error: --sg-id and --rule are required", file=sys.stderr)
            return 2
        action = "dry-run" if args.dry_run else "execute"
        print(
            f"[stub] remediate ({action}): sg={args.sg_id} rule={args.rule} "
            "— code generation not implemented yet (Week 3)."
        )
    elif args.command == "report":
        print(f"[stub] report: would write to {args.output} — not implemented yet (Week 4).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
