"""AeroDrift CLI.

    python -m aerodrift.cli.main <command> [options]

By default every command runs against a moto-backed *simulated* AWS
account seeded with a secure 3-tier production estate (see
``aerodrift.ingestion.simulated_cloud``). Pass ``--scenario`` to apply the
manual mistakes the tool is built to catch, or ``--live`` to read real AWS
with your normal boto3 credentials (changes to live AWS additionally
require ``--yes``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from aerodrift import __version__
from aerodrift.cli.dashboard import build_dashboard, build_diff_table, render_dashboard
from aerodrift.config import INTERNET_NODE
from aerodrift.daemon import AeroDriftDaemon, CycleResult
from aerodrift.graph.topology import build_mock_graph, detect_drift, diff_topologies
from aerodrift.ingestion.rules import IngressRule, RuleParseError
from aerodrift.ingestion.simulated_cloud import SimulatedCloud
from aerodrift.persistence.store import SnapshotNotFound, SnapshotStore
from aerodrift.remediation.codegen import (
    MissingDriftFieldError,
    UnsupportedDriftTypeError,
    generate_remediation_code,
)
from aerodrift.remediation.engine import remediate
from aerodrift.remediation.sandbox import SandboxViolation, run_remediation
from aerodrift.reports.pdf_report import generate_incident_report
from aerodrift.runtime import one_shot_scan, open_environment, run_drift_scenario

SCENARIOS = SimulatedCloud.SCENARIOS
DEFAULT_REMEDIATION_SCENARIOS = ["open-db", "open-ssh"]
DETECTION_TARGET_S = 5.0


def _console() -> Console:
    # Resolved per call so pytest's capsys / redirected stdout are honoured.
    return Console(file=sys.stdout)


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


# --------------------------------------------------------------------- parser
def _add_env_args(p: argparse.ArgumentParser, *, scenarios_default_note: str = "") -> None:
    p.add_argument("--scenario", action="append", choices=SCENARIOS, default=None,
                   help="Drift to inject into the simulated cloud (repeatable)" + scenarios_default_note)
    p.add_argument("--live", action="store_true", help="Use real AWS via your boto3 credentials")
    p.add_argument("--region", default=None, help="AWS region (default: us-east-1 / your profile)")
    p.add_argument("--profile", default=None, help="boto3 profile name for --live")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aerodrift",
                                     description="AeroDrift — Agentic Cloud Topology & Remediation Engine")
    parser.add_argument("--version", action="version", version=f"aerodrift {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="Ingest cloud state, build the graph, render the topology dashboard")
    _add_env_args(p)
    p.add_argument("--offline", "--demo-data", dest="offline", action="store_true",
                   help="Render the built-in offline mock topology instead of ingesting")
    p.add_argument("--watch", action="store_true", help="Keep polling and refresh the dashboard live")
    p.add_argument("--interval", type=float, default=2.0, help="Polling interval for --watch (seconds)")
    p.add_argument("--duration", type=float, default=None, help="Stop --watch after N seconds")
    p.add_argument("--heal", action="store_true", help="With --watch (simulated): auto-remediate drift")
    p.add_argument("--inject", action="append", choices=SCENARIOS, default=None,
                   help="With --watch (simulated): inject this drift while watching (repeatable)")
    p.add_argument("--inject-after", type=float, default=3.0, help="Seconds before --inject fires")

    p = sub.add_parser("status", help="Print current drift (text or JSON)")
    _add_env_args(p)
    p.add_argument("--offline", "--demo-data", dest="offline", action="store_true",
                   help="Use the built-in offline mock topology")
    p.add_argument("--json", action="store_true", help="Output drift as JSON")

    p = sub.add_parser("remediate", help="Generate AST remediation code for drift and run it in the sandbox")
    _add_env_args(p, scenarios_default_note=f"; simulated default: {' '.join(DEFAULT_REMEDIATION_SCENARIOS)}")
    p.add_argument("--drift-id", help="Only remediate this drift id")
    p.add_argument("--dry-run", action="store_true", help="Generate and validate code, do not execute")
    p.add_argument("--sg-id", help="Manual target: security group id (use with --rule)")
    p.add_argument("--rule", help="Manual target: rule to revoke, e.g. 0.0.0.0/0:22/tcp")
    p.add_argument("--yes", action="store_true", help="Required to change live AWS")

    p = sub.add_parser("daemon", help="Run the self-healing daemon (poll -> detect -> heal -> verify -> persist)")
    _add_env_args(p)
    p.add_argument("--interval", type=float, default=2.0, help="Polling interval (seconds)")
    p.add_argument("--cycles", type=int, default=None, help="Stop after N cycles")
    p.add_argument("--duration", type=float, default=None, help="Stop after N seconds")
    p.add_argument("--no-heal", action="store_true", help="Detect only; never remediate")
    p.add_argument("--inject", action="append", choices=SCENARIOS, default=None,
                   help="(simulated) inject this drift while running (repeatable)")
    p.add_argument("--inject-after", type=float, default=3.0, help="Seconds before --inject fires")
    p.add_argument("--db", default="aerodrift.db", help="SQLite history database")
    p.add_argument("--report", default=None, help="Write a PDF incident report on exit")
    p.add_argument("--yes", action="store_true", help="Required for auto-heal against live AWS")

    p = sub.add_parser("history", help="List stored topology snapshots and incidents")
    p.add_argument("--db", default="aerodrift.db")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("diff", help="Diff the topology between two snapshots / timestamps")
    p.add_argument("ref_from", help="Snapshot id, ISO timestamp, 'baseline' or 'latest'")
    p.add_argument("ref_to", nargs="?", default="latest", help="Snapshot id, ISO timestamp or 'latest'")
    p.add_argument("--db", default="aerodrift.db")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("report", help="Generate a PDF incident report")
    _add_env_args(p, scenarios_default_note=f"; simulated default: {' '.join(DEFAULT_REMEDIATION_SCENARIOS)}")
    p.add_argument("--output", default="incident_report.pdf", help="Output PDF path")
    p.add_argument("--no-execute", action="store_true", help="Generate remediation code but do not run it")
    p.add_argument("--from-db", default=None, metavar="DB",
                   help="Build the report from incidents already stored in this SQLite DB")
    p.add_argument("--yes", action="store_true", help="Required to change live AWS")

    p = sub.add_parser("demo", help="Render the dashboard for the offline mock topology")
    p.add_argument("--healthy", action="store_true", help="Render the healthy (no-drift) state")

    sub.add_parser("mid-review-demo",
                   help="Mid-project checkpoint: drift an SG while the daemon polls; prove detection < 5 s")
    p = sub.add_parser("self-heal-demo", help="Detect -> generate -> sandbox execute -> verify, with dashboards")
    p.add_argument("--scenario", action="append", choices=SCENARIOS, default=None)
    p = sub.add_parser("final-demo", help="Final review: full self-heal loop + SQLite history + diff + PDF")
    p.add_argument("--output", default="final_incident_report.pdf")
    p.add_argument("--db", default="aerodrift_final_demo.db")
    return parser


# ------------------------------------------------------------------ helpers
def _print_drift_lines(drifts, console):
    if not drifts:
        console.print("No drift detected.", style="green")
        return
    for d in drifts:
        edge = d.get("offending_edge") or {}
        console.print(f"[{d.get('severity', '?')}] {d.get('type', '?')} — "
                      f"{d.get('affected_name', d.get('affected_node', '?'))} ({d.get('affected_node', '?')}) "
                      f"rule {edge.get('rule', '?')} -> {d.get('target_name', d.get('target_resource', '?'))}  "
                      f"[{d.get('drift_id', '?')}]", markup=False, highlight=False)


def _cycle_line(r: CycleResult) -> str:
    t = r.timings_ms
    parts = [f"cycle {r.cycle}: {r.final_graph.number_of_nodes()} nodes",
             f"collect {t.get('collect_ms', 0):.0f} ms", f"detect {t.get('detect_ms', 0):.2f} ms",
             f"{len(r.drifts)} drift"]
    if r.new_drifts:
        parts.append(f"{len(r.new_drifts)} NEW")
    for rec in r.records:
        tag = "verified" if rec.verified else ("NOT verified" if rec.verified is False else rec.status)
        parts.append(f"healed {rec.drift.get('affected_name')} {rec.drift['offending_edge']['rule']} ({tag})")
    return " | ".join(parts)


async def _inject_later(env, scenarios, delay, console=None):
    if not scenarios:
        return
    await asyncio.sleep(delay)
    for sc in scenarios:
        inj = await asyncio.to_thread(env.cloud.inject_drift, sc)
        env.injections.append(inj)
        if console is not None:
            console.print(f">> injected drift: {inj.description}", style="yellow", markup=False)


def _run_daemon_loop(env, args, console, *, heal: bool, store=None, live_ui: bool = False,
                     cycles: int | None = None) -> AeroDriftDaemon:
    """Run the daemon with optional drift injection, rendering each cycle."""
    daemon = AeroDriftDaemon(env.collector, store=store, interval=args.interval, auto_heal=heal)

    async def main(live=None):
        await daemon.establish_baseline()
        if live is None:
            console.print(f"baseline recorded ({daemon.baseline.number_of_nodes()} nodes)"
                          + (f", snapshot #{daemon.baseline_snapshot_id}" if daemon.baseline_snapshot_id else ""))

        def on_cycle(r):
            if live is not None:
                live.update(build_dashboard(r.final_graph, r.final_drifts, daemon.records + r.records,
                                            info=_cycle_line(r), subtitle=f"{env.label} · every {args.interval:g}s"))
            else:
                console.print(_cycle_line(r), markup=False, highlight=False)
        daemon.on_cycle = on_cycle

        task = asyncio.create_task(_inject_later(env, getattr(args, "inject", None), args.inject_after,
                                                 None if live is not None else console))
        try:
            await daemon.run(max_cycles=cycles, duration=args.duration)
        finally:
            task.cancel()

    try:
        if live_ui:
            with Live(Panel("collecting…"), console=console, refresh_per_second=4) as live:
                asyncio.run(main(live))
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\nstopped.")
    return daemon


# ----------------------------------------------------------------- commands
def cmd_scan(args, console) -> int:
    if args.offline:
        graph = build_mock_graph()
        render_dashboard(graph, detect_drift(graph), subtitle="offline mock topology", out=console)
        return 0
    if args.live and (args.inject or args.heal):
        _err("--inject/--heal are only available on the simulated cloud from `scan`; "
             "use `daemon --live --yes` to self-heal live AWS")
        return 2
    with open_environment(live=args.live, region=args.region, scenarios=args.scenario,
                          profile=args.profile) as env:
        if not args.watch:
            state, graph, drifts = one_shot_scan(env)
            info = f"ingest {state.total_ms:.0f} ms ({len(state.api_timings_ms)} concurrent API calls)"
            render_dashboard(graph, drifts, info=info, subtitle=env.label, out=console)
            return 0
        daemon = _run_daemon_loop(env, args, console, heal=args.heal, live_ui=console.is_terminal)
        if daemon.history and not console.is_terminal:
            last = daemon.history[-1]
            render_dashboard(last.final_graph, last.final_drifts, daemon.records, subtitle=env.label, out=console)
    return 0


def cmd_status(args, console) -> int:
    if args.offline:
        drifts = detect_drift(build_mock_graph())
    else:
        with open_environment(live=args.live, region=args.region, scenarios=args.scenario,
                              profile=args.profile) as env:
            _, _, drifts = one_shot_scan(env)
    if args.json:
        print(json.dumps(drifts, indent=2, default=str))
    else:
        _print_drift_lines(drifts, console)
    return 0


def cmd_remediate(args, console) -> int:
    if bool(args.sg_id) != bool(args.rule):
        _err("--sg-id and --rule must be used together")
        return 2

    if args.sg_id:  # manual target
        try:
            rule = IngressRule.parse(args.rule)
        except RuleParseError as exc:
            _err(str(exc))
            return 2
        drift = {"drift_id": f"manual-{args.sg_id}", "type": "open_ingress", "affected_node": args.sg_id,
                 "offending_edge": {"source": INTERNET_NODE, "target": args.sg_id, "rule": str(rule)},
                 "rule_detail": rule.to_dict(), "severity": "high",
                 "detected_at": datetime.now(timezone.utc).isoformat()}
        code = generate_remediation_code(drift)
        console.print("Generated remediation code:")
        console.print(code, markup=False, highlight=False)
        if args.dry_run or not args.live:
            result = run_remediation(code, None, dry_run=True)
            note = "" if args.dry_run else " (manual targets only execute with --live --yes)"
            console.print(f"Sandbox validation: {result['status']} — dry run, not executed{note}")
            return 0
        if not args.yes:
            _err("refusing to change live AWS without --yes")
            return 2
        with open_environment(live=True, region=args.region, profile=args.profile) as env:
            record = remediate(drift, env.ec2)
        console.print(f"Executed in sandbox — status: {record.status}  {record.result.get('message', '')}",
                      markup=False)
        return 0 if record.succeeded else 1

    if args.live and not args.dry_run and not args.yes:
        _err("refusing to change live AWS without --yes (or use --dry-run)")
        return 2
    scenarios = args.scenario if (args.scenario or args.live) else DEFAULT_REMEDIATION_SCENARIOS
    with open_environment(live=args.live, region=args.region, scenarios=scenarios, profile=args.profile) as env:
        for inj in env.injections:
            console.print(f"simulated drift: {inj.description}", style="yellow", markup=False)
        _, _, drifts = one_shot_scan(env)
        if args.drift_id:
            drifts = [d for d in drifts if d["drift_id"] == args.drift_id]
            if not drifts:
                _err(f"no drift with id {args.drift_id}")
                return 1
        if not drifts:
            console.print("No drift detected — nothing to remediate.", style="green")
            return 0
        failed = 0
        for drift in drifts:
            record = remediate(drift, env.ec2, dry_run=args.dry_run)
            console.print(f"\n{drift['type']} on {drift.get('affected_name')} ({drift['affected_node']}) — "
                          f"{drift['offending_edge']['rule']}", style="bold", markup=False)
            if record.code:
                console.print(record.code, markup=False, highlight=False)
            label = "Validated in sandbox (dry run: not executed)" if args.dry_run else "Executed in sandbox"
            console.print(f"{label} — status: {record.status}  {record.result.get('message', '')}",
                          markup=False, highlight=False)
            failed += 0 if (record.succeeded or record.status == "validated") else 1
        if not args.dry_run:
            _, _, after = one_shot_scan(env)
            remaining = {d["drift_id"] for d in after} & {d["drift_id"] for d in drifts}
            if remaining:
                console.print(f"Verification: {len(remaining)} drift(s) still present", style="red")
                failed += 1
            else:
                console.print(f"Verification: re-ingested cloud state, {len(drifts)} drift(s) gone.", style="green")
        return 1 if failed else 0


def cmd_daemon(args, console) -> int:
    if args.live and not args.no_heal and not args.yes:
        _err("auto-heal against live AWS requires --yes (or pass --no-heal)")
        return 2
    if args.inject and args.live:
        _err("--inject only works with the simulated cloud")
        return 2
    with SnapshotStore(args.db) as store, open_environment(
            live=args.live, region=args.region, scenarios=args.scenario, profile=args.profile) as env:
        console.print(f"AeroDrift daemon on {env.label} · interval {args.interval:g}s · "
                      f"auto-heal {'off' if args.no_heal else 'ON'} · history -> {args.db}", markup=False)
        daemon = _run_daemon_loop(env, args, console, heal=not args.no_heal, store=store, cycles=args.cycles)
        if daemon.history:
            last = daemon.history[-1]
            render_dashboard(last.final_graph, last.final_drifts, daemon.records, subtitle=env.label, out=console)
        if args.report:
            diffs = []
            if daemon.baseline is not None and daemon.previous is not None:
                diffs.append(("Baseline -> current", diff_topologies(daemon.baseline, daemon.previous)))
            generate_incident_report(args.report, daemon.records, diffs=diffs, environment=env.label)
            console.print(f"Incident report written to {args.report}", markup=False)
    return 0


def cmd_history(args, console) -> int:
    with SnapshotStore(args.db) as store:
        snaps = store.list_snapshots(args.limit)
        incidents = store.list_incidents(args.limit)
    t = Table(title=f"Topology snapshots ({args.db})")
    for col in ("id", "taken_at (UTC)", "label", "nodes", "edges", "drift"):
        t.add_column(col, overflow="fold")
    for s in snaps:
        t.add_row(str(s.id), s.taken_at, (s.label or "") + (" [cyan](baseline)[/cyan]" if s.is_baseline else ""),
                  str(s.node_count), str(s.edge_count), f"[red]{s.drift_count}[/red]" if s.drift_count else "0")
    console.print(t)
    t = Table(title="Remediation incidents")
    for col in ("id", "type", "security group", "rule", "status", "verified"):
        t.add_column(col, overflow="fold")
    for i in incidents:
        d = i.get("drift", {})
        t.add_row(str(i["incident_id"]), d.get("type", "?"), d.get("affected_name", d.get("affected_node", "?")),
                  (d.get("offending_edge") or {}).get("rule", "?"), i.get("status", "?"),
                  {True: "[green]yes[/green]", False: "[red]no[/red]"}.get(i.get("verified"), "—"))
    console.print(t)
    if not snaps:
        console.print("No snapshots yet — run `aerodrift daemon` or `aerodrift final-demo`.", style="dim")
    return 0


def cmd_diff(args, console) -> int:
    with SnapshotStore(args.db) as store:
        try:
            a, b, diff = store.diff(args.ref_from, args.ref_to)
        except (SnapshotNotFound, ValueError) as exc:
            _err(str(exc))
            return 1
    if args.json:
        print(json.dumps({"from": {"id": a.id, "taken_at": a.taken_at}, "to": {"id": b.id, "taken_at": b.taken_at},
                          "diff": diff.to_dict()}, indent=2))
        return 0
    console.print(build_diff_table(diff, f"#{a.id} {a.taken_at[:19]}", f"#{b.id} {b.taken_at[:19]}"))
    return 0


def cmd_report(args, console) -> int:
    if args.from_db:
        with SnapshotStore(args.from_db) as store:
            incidents = store.list_incidents()
            diffs = []
            try:
                a, b, d = store.diff("baseline", "latest")
                diffs.append((f"Baseline (#{a.id}) -> latest (#{b.id})", d))
            except SnapshotNotFound:
                pass
        if not incidents:
            console.print("No incidents stored — nothing to report on.")
            return 0
        generate_incident_report(args.output, list(reversed(incidents)), diffs=diffs,
                                 environment=f"history from {args.from_db}")
        console.print(f"Incident report written to {args.output}", markup=False)
        return 0

    if args.live and not args.no_execute and not args.yes:
        _err("refusing to change live AWS without --yes (or use --no-execute)")
        return 2
    scenarios = args.scenario if (args.scenario or args.live) else DEFAULT_REMEDIATION_SCENARIOS
    with open_environment(live=args.live, region=args.region, scenarios=scenarios, profile=args.profile) as env:
        _, before, drifts = one_shot_scan(env)
        if not drifts:
            console.print("No drift detected — nothing to report on.")
            return 0
        records = [remediate(d, env.ec2, dry_run=args.no_execute) for d in drifts]
        diffs = []
        if not args.no_execute:
            _, after, remaining = one_shot_scan(env)
            still = {d["drift_id"] for d in remaining}
            for r in records:
                r.verified = r.succeeded and r.drift["drift_id"] not in still
            diffs.append(("Before -> after remediation", diff_topologies(before, after)))
        generate_incident_report(args.output, records, diffs=diffs, environment=env.label)
    console.print(f"Incident report written to {args.output} ({len(records)} incident(s))", markup=False)
    return 0


def cmd_demo(args, console) -> int:
    graph = build_mock_graph(drifted=not args.healthy)
    render_dashboard(graph, detect_drift(graph), subtitle="offline mock topology", out=console)
    return 0


def run_mid_review_demo(console=None) -> int:
    console = console or _console()
    console.rule("[bold]Mid-project review: graph audit")
    console.print("Step 1/3: seeding simulated AWS, recording the secure baseline; daemon polls every 1s")
    outcome = run_drift_scenario(
        ["open-db"], heal=False, interval=1.0, inject_after=1.2,
        on_inject=lambda i: console.print(f"Step 2/3: engineer changes AWS by hand -> {i.description}",
                                          style="yellow", markup=False))
    render_dashboard(outcome.baseline, detect_drift(outcome.baseline), subtitle="baseline", out=console)
    if outcome.drifted is None:
        console.print("FAIL: drift was not detected before the timeout", style="red")
        return 1
    lat = outcome.detection_latency_s
    console.print(f"Step 3/3: daemon detected the new internet -> database path {lat:.3f}s after the change "
                  f"(graph query {outcome.drifted.timings_ms['detect_ms']:.2f} ms)")
    render_dashboard(outcome.drifted.graph, outcome.drifted.drifts, subtitle="after manual change", out=console)
    ok = lat < DETECTION_TARGET_S
    console.print(f"{'PASS' if ok else 'FAIL'}: detection in {lat:.3f}s (target < {DETECTION_TARGET_S:g}s); "
                  "drifted resources highlighted in red", style="bold green" if ok else "bold red")
    return 0 if ok else 1


def run_self_heal_demo(scenarios=None, console=None) -> int:
    console = console or _console()
    scenarios = scenarios or ["open-db", "open-ssh"]
    console.rule("[bold]Self-heal loop")
    outcome = run_drift_scenario(
        scenarios, heal=True, interval=1.0, inject_after=1.0,
        on_inject=lambda i: console.print(f">> {i.description}", style="yellow", markup=False))
    if outcome.drifted is None:
        console.print("drift was not detected before the timeout", style="red")
        return 1
    console.print(f"Step 1/4: detected {len(outcome.drifted.drifts)} drift(s) in {outcome.detection_latency_s:.3f}s")
    render_dashboard(outcome.drifted.graph, outcome.drifted.drifts, subtitle="drift detected", out=console)
    console.print("Step 2/4: generated remediation code (Python ast):")
    for rec in outcome.records:
        console.print(rec.code or f"# not generated: {rec.result.get('message')}", markup=False, highlight=False)
    console.print("Step 3/4: executed in sandbox (no builtins, scoped boto3 client):")
    for rec in outcome.records:
        console.print(f"  {rec.drift['affected_name']}: {rec.status} — {rec.result.get('message', '')}",
                      markup=False, highlight=False)
    console.print("Step 4/4: re-ingested AWS state to verify:")
    for rec in outcome.records:
        console.print(f"  {rec.drift['drift_id']}: {'verified healed' if rec.verified else 'NOT healed'}"
                      + (f" in {rec.time_to_heal_s:.3f}s" if rec.time_to_heal_s is not None else ""))
    render_dashboard(outcome.healed_graph, outcome.healed_drifts, outcome.records, subtitle="after self-heal",
                     out=console)
    return 0 if all(r.verified for r in outcome.records) else 1


def run_final_demo(output_path: str, db_path: str = "aerodrift_final_demo.db", console=None) -> int:
    console = console or _console()
    console.rule("[bold]AeroDrift final review")
    scenarios = ["open-db", "open-all-app", "open-ssh"]
    with SnapshotStore(db_path) as store:
        store.clear_baseline()  # each demo run seeds a fresh simulated cloud
        console.print("Step 1/5: simulated AWS seeded; daemon records baseline and polls every 1s")
        outcome = run_drift_scenario(
            scenarios, heal=True, interval=1.0, inject_after=1.2, store=store,
            on_inject=lambda i: console.print(f"  manual change: {i.description}", style="yellow", markup=False))
        if outcome.drifted is None:
            console.print("drift was not detected before the timeout", style="red")
            return 1
        d = outcome.drifted
        console.print(f"Step 2/5: detected {len(d.drifts)} drift(s) {outcome.detection_latency_s:.3f}s after the "
                      f"change (ingest {d.timings_ms['collect_ms']:.0f} ms, graph query {d.timings_ms['detect_ms']:.2f} ms)")
        render_dashboard(d.graph, d.drifts, subtitle="drift detected", out=console)
        console.print("Step 3/5: AST-generated remediation, executed in the sandbox and verified:")
        for rec in d.records:
            console.print(rec.code, markup=False, highlight=False)
            console.print(f"  -> {rec.status}, {'verified healed' if rec.verified else 'NOT verified'}"
                          + (f" in {rec.time_to_heal_s:.3f}s" if rec.time_to_heal_s is not None else ""))
        render_dashboard(outcome.healed_graph, outcome.healed_drifts, d.records, subtitle="self-healed", out=console)
        console.print(f"Step 4/5: SQLite history in {db_path} — diff between two timestamps:")
        base = store.get_snapshot("baseline", load=False)
        drifted_snap = store.get_snapshot(d.snapshot_id, load=False)
        _, _, diff = store.diff(base.taken_at, drifted_snap.taken_at)
        console.print(build_diff_table(diff, f"baseline @ {base.taken_at[11:23]}",
                                       f"drifted @ {drifted_snap.taken_at[11:23]}"))
        _, _, healed_diff = store.diff("baseline", "latest")
        console.print(f"  baseline -> latest (after self-heal): {healed_diff.summary()}")
        console.print(f"Step 5/5: writing PDF incident report to {output_path}")
        generate_incident_report(output_path, d.records, diffs=outcome.diffs, metrics=outcome.metrics(),
                                 environment="simulated AWS (moto)")
    ok = all(r.verified for r in d.records) and outcome.detection_latency_s < DETECTION_TARGET_S
    console.print(f"{'DONE' if ok else 'INCOMPLETE'}: {sum(bool(r.verified) for r in d.records)}/{len(d.records)} "
                  f"drift(s) self-healed; report at {output_path}", style="bold green" if ok else "bold red",
                  markup=False)
    return 0 if ok else 1


COMMANDS = {
    "scan": cmd_scan, "status": cmd_status, "remediate": cmd_remediate, "daemon": cmd_daemon,
    "history": cmd_history, "diff": cmd_diff, "report": cmd_report, "demo": cmd_demo,
}


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = _console()
    if args.verbose:
        console.print(f"[verbose] command: {args.command}", markup=False)
    try:
        if args.command == "mid-review-demo":
            return run_mid_review_demo(console)
        if args.command == "self-heal-demo":
            return run_self_heal_demo(args.scenario, console)
        if args.command == "final-demo":
            return run_final_demo(args.output, args.db, console)
        return COMMANDS[args.command](args, console)
    except SandboxViolation as exc:
        _err(f"sandbox rejected generated code: {exc}")
        return 1
    except (UnsupportedDriftTypeError, MissingDriftFieldError) as exc:
        _err(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
