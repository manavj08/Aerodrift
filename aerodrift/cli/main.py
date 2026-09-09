"""AeroDrift CLI entrypoint.

Run with:
    python -m aerodrift.cli.main <command>

Commands are stubs for now — filled in during later weeks.
"""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aerodrift",
        description="AeroDrift — Agentic Cloud Topology & Remediation Engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("scan", help="Scan cloud state and render topology (Week 2)")
    subparsers.add_parser("status", help="Show current drift status (Week 2)")
    subparsers.add_parser("remediate", help="Generate and run a remediation (Week 3)")
    subparsers.add_parser("report", help="Generate a PDF incident report (Week 4)")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        print("[stub] scan: dashboard rendering not implemented yet (Week 2).")
    elif args.command == "status":
        print("[stub] status: drift status not implemented yet (Week 2).")
    elif args.command == "remediate":
        print("[stub] remediate: code generation not implemented yet (Week 3).")
    elif args.command == "report":
        print("[stub] report: PDF report generation not implemented yet (Week 4).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
