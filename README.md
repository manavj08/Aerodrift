# AeroDrift — Person C Workstream (Remediation, CLI & Reporting)

Agentic cloud topology & remediation engine. This repo covers **Person C's**
individual assignment: CLI, Rich dashboard, AST-based code generator,
sandboxed executor, and PDF incident reports.

Status: **Week 3, Day 1 (team merge + integration fix) — 76 tests passing.**

## What's here (team merge + adapter fix, additive to Week 3 Day 1 solo)

Person A (Ashutosh) and Person B (Prasanth) delivered real ingestion and
graph-construction code. This section documents the merge and a bug fix
found by actually running the combined pipeline, not just the individual
pieces' own tests.

- **Person A's real ingestion** (`aerodrift/ingestion/mock_client.py`,
  `schema.py`): moto-backed mock EC2 state, `Resource`/`Relationship`
  dataclasses. Replaces the old `mock_aws.py` placeholder.
- **Person B's real graph builder** (`aerodrift/graph/builder.py`):
  `build_graph(resources, connections)`. `detect_drift()` in
  `topology.py` is still Person C's placeholder logic — B has not yet
  delivered real drift detection.
- **`aerodrift/ingestion/adapter.py`** — a documented, explicitly
  **temporary** bridge between A's dataclass output and B's dict-based
  `build_graph()` input, since their shapes were never actually agreed
  on (see `CONTRACT.md`).
- **Bug found and fixed**: running the real pipeline by hand (ingestion →
  adapter → graph → `detect_drift()`) showed it silently found **zero
  drift**, despite Person A's mock security group having a genuinely
  open `0.0.0.0/0:22` rule. The adapter now synthesizes the missing
  internet node/edge from that rule — clearly marked as a workaround,
  not a real ingestion feature.
- **Still open (not fixed, deliberately)**: `detect_drift()` still finds
  zero drift on the real pipeline even after the fix above, because
  `SENSITIVE_RESOURCE_TYPES` doesn't cover security groups and there's a
  casing mismatch (`"security_group"` vs `"SecurityGroup"`). This is a
  team policy decision, not something to guess at — see `CONTRACT.md`.
- Test suite: 72 (initial merge) → **76 passing** (4 new adapter tests,
  1 stale test fixed).

## What's here (Week 3 Day 1, additive to Week 2)

- **Real `codegen.generate_remediation_code(drift)`** — builds an
  `ast.Call` node (not string templating) for
  `revoke_security_group_ingress(sg_id, rule)` and unparses it to source.
  Built against **`CONTRACT.md`'s draft shape** — Person B has not
  confirmed the real contract yet, so drift type names here
  (`open_ingress`, `public_db_exposure`) and Person A's mock signature
  are assumptions pending confirmation.
- Unsupported drift types (e.g. `indirect_exposure`, which has no direct
  rule to revoke) raise `UnsupportedDriftTypeError` rather than
  generating something wrong.
- Missing/malformed drift fields raise `MissingDriftFieldError` with a
  clear message.
- Values are inserted via `ast.Constant`, not string formatting — a
  drift's `rule` string can't break out of the generated call (tested
  with an injection-attempt payload).
- **`remediate` CLI command wired to real codegen** — no longer a stub.
  Prints the generated code; `--dry-run` explicitly does not execute it
  (execution lands with the sandbox, Week 3 Day 2+).
- Test suite expanded from 53 → 63 tests.

## What's here (Week 2 Day 5, additive to Day 4)

- **Dashboard hardened for real-world graph size and data quality**,
  ahead of Person B's real (likely larger, differently-shaped) module:
  - Topology table now caps at `MAX_TOPOLOGY_ROWS` (25) — drifted nodes
    are always shown in full; healthy nodes beyond the cap are summarized
    as "N more healthy resource(s)" instead of rendering an unbounded table.
  - `_drifted_node_ids()` now tolerates malformed drift entries (missing/
    `None` `affected_node`, non-dict entries) without crashing rendering.
- Test suite expanded from 50 → 53 tests.
- **Week 2 complete** — dashboard renders real topology, highlights
  drift in red, `mid-review-demo` scripts the checkpoint flow, and
  rendering is now defensive against data it hasn't seen yet.

## What's here (Week 2 Day 4, additive to Day 3)

- New CLI command: **`aerodrift mid-review-demo`** — scripts the exact
  joint-demo flow from your assignment's Week 2 checkpoint: builds the
  baseline topology, simulates an engineer opening a new security group
  directly to the internet (fronting the database), detects the
  resulting drift, times the detection, and renders the dashboard with
  the newly-drifted resource shown in red. Single command, ready for the
  review.
- Dashboard/topology panel confirmed to correctly handle **multiple
  simultaneous drifts** (not just the single DB-exposure case) — added
  tests covering 2+ drifted resources rendering together.
- Test suite expanded from 46 → 50 tests.

## What's here (Week 2 Day 3, additive to Day 2)

- **`detect_drift()` placeholder is no longer a no-op.** It now does real
  NetworkX path-finding from `0.0.0.0/0` to sensitive resources (currently:
  `database` nodes) — the exact "is there a path from the Internet to
  Database X?" use case from the project spec. `scan`/`status` now show
  genuine drift on the mock graph **without needing `--demo-data`**.
- Detects both direct exposure (`public_db_exposure` — internet edge
  straight to the DB) and indirect exposure (`indirect_exposure` — DB
  reachable via intermediate hops), reporting severity `critical` and a
  contract-shaped drift object either way.
- `--demo-data` is kept for testing against the fixed `SAMPLE_DRIFTS`
  set, useful for consistent screenshots/demos independent of graph changes.
- Added a performance test proving detection completes well under 5
  seconds on a 500-node graph — relevant to the Week 2 mid-project
  review checkpoint ("drift detection under 5 seconds").
- Test suite expanded from 38 → 46 tests.

## What's here (Week 2 Day 2, additive to Day 1)

- **`scan` and `status` are no longer stubs** — both now call
  `build_mock_graph()` + `detect_drift()` and render real output through
  the dashboard/drift-list panels. Because `detect_drift()` is still
  Person B's placeholder (always returns `[]`), `scan`/`status` will
  show "no drift" until B's real detection lands — this is expected and
  documented, not a bug.
- Added `--demo-data` flag to both `scan` and `status` — bypasses the
  placeholder `detect_drift()` and uses `SAMPLE_DRIFTS` instead, so you
  can see drift-highlighting behavior today without waiting on B.
- `status --json` now returns real (empty, until B delivers) or demo
  drift data as JSON, not a stub string.
- `--watch` on `scan` prints an honest "not implemented yet" note — the
  continuous re-scan loop itself is not built (out of scope for today;
  flag exists for the future interface).
- Test suite expanded from 34 → 38 tests.

## What's here (Week 2 Day 1, additive to Week 1)

- **`_build_topology_panel()` now renders actual graph nodes** — walks a
  NetworkX `DiGraph`'s nodes and shows resource name / type / status,
  replacing the "(no data yet)" placeholder row. Drifted nodes (matched
  by `affected_node` against drift objects, per `CONTRACT.md`) render in
  red with a `DRIFTED` status; others show `healthy`.
- `build_layout()` / `render_shell()` now take a `graph` parameter
  alongside `drifts`.
- **`aerodrift/graph/topology.py` placeholder expanded** with
  `build_mock_graph()` — a small representative topology (internet → SG →
  EC2 → DB, plus a simulated drift edge straight to the DB) so the
  dashboard has real-shaped data to render. **This entire file is Person
  B's responsibility — replace it wholesale once B delivers.**
- `aerodrift demo` now renders the mock graph through the real topology
  panel (previously just showed the drift list with an empty topology).
- Test suite expanded from 27 → 34 tests (new `test_graph_placeholder.py`
  covers the mock graph; `test_dashboard.py` covers real rendering).

## What's here (Day 5, additive to Day 3-4)

- New CLI command: `aerodrift demo [--healthy]` — renders the dashboard
  against sample drift data matching the locked contract shape. Useful
  to preview the shell before Week 2's real data is wired in, and as a
  quick smoke test for teammates.
- `CONTRACT.md` marked **locked** — per your assignment's "End of Week 1:
  data contract locked with both teammates" checkpoint. Update it only
  with team agreement from here on.
- Test suite expanded from 25 → 27 tests.

## What's here (Day 3-4, additive to Day 2)

- **`CONTRACT.md`** — drift object shape (from Person B) and mock
  remediation method signatures (from Person A), drafted per the project
  spec. **Update this file with the actual agreed values from your real
  sync meeting** — it's the source of truth Week 2/3 code depends on.
- Dashboard shell rewritten to be drift-aware: `build_layout(drifts=...)`
  now accepts a list of drift objects and switches header/footer/panel
  styling between healthy (green) and drifted (red) states. Still no
  live data source — Week 2 wires in Person B's real `detect_drift()`
  output using the shape locked in `CONTRACT.md`.
- Dashboard split into named helper functions (`_build_header`,
  `_build_topology_panel`, `_build_drift_list_panel`, `_build_footer`)
  so Week 2 can swap each piece independently.
- Test suite expanded from 16 → 25 tests (9 new dashboard tests).

## What's here (Day 2, additive to Day 1)

- CLI commands now take real arguments (the interface later weeks will
  implement against), while command bodies remain stubs:
  - `scan [--watch]`
  - `status [--json]`
  - `remediate --sg-id SG_ID --rule RULE [--dry-run]` (sg-id/rule required)
  - `report [--output PATH]` (defaults to `incident_report.pdf`)
  - `--verbose` / `-v` and `--version` global flags
- Expanded test suite: 16 tests covering every flag and the
  `remediate` required-argument validation (exit code 2 if missing).

## What's here (Day 1)

- CLI entrypoint (`aerodrift/cli/main.py`) — commands `scan`, `status`,
  `remediate`, `report`. All currently print a stub message; real logic
  lands in later weeks per the assignment plan.
- Rich dashboard shell (`aerodrift/cli/dashboard.py`) — static layout only
  (header / topology / drift list / footer), no live data yet.
- Empty stubs for Week 3–4 work: `remediation/codegen.py`,
  `remediation/sandbox.py`, `reports/pdf_report.py` — each raises
  `NotImplementedError` on purpose so tests can assert they're not built yet.
- **Placeholder modules for Person A and B's parts**
  (`ingestion/mock_aws.py`, `graph/topology.py`) so this project runs
  standalone today. Replace these with the real modules once A and B share
  their code — do not build real logic into these files yourself.
- Test suite covering the CLI and dashboard shell (7 tests, all passing).

## Requirements

- Python 3.10+
- Windows (setup scripts use Command Prompt / `.bat`)

## Setup (Windows)

```
setup.bat
```

This creates a venv, activates it, and installs `requirements.txt`.

### Manual setup

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```
run.bat scan
run.bat status
run.bat demo
run.bat mid-review-demo
run.bat remediate --sg-id sg-0a1b2c3 --rule "0.0.0.0/0:22/tcp"
run.bat remediate --sg-id sg-123 --rule "0.0.0.0/0:80/tcp" --dry-run
```

Or manually:
```
venv\Scripts\activate
python -m aerodrift.cli.main remediate --sg-id sg-0a1b2c3 --rule "0.0.0.0/0:22/tcp"
```

`remediate` now generates real AST-based code for
`revoke_security_group_ingress` — it does not execute it yet (that's the
sandbox, coming next in Week 3).

## Test

```
run_tests.bat
```

Or manually:
```
venv\Scripts\activate
pytest -v
```

Expected: **63 passed**.

## Folder structure

```
aerodrift/
  aerodrift/
    cli/
      main.py          # CLI entrypoint (argparse)
      dashboard.py      # Rich dashboard shell
    remediation/
      codegen.py        # AST code generator (stub — Week 3)
      sandbox.py         # Restricted exec() sandbox (stub — Week 3)
    reports/
      pdf_report.py      # PDF incident report (stub — Week 4)
    ingestion/
      mock_aws.py         # PLACEHOLDER for Person A — replace, don't build
    graph/
      topology.py          # PLACEHOLDER for Person B — replace, don't build
  tests/
    test_cli.py
    test_dashboard.py
    test_codegen.py
    test_sandbox.py
  requirements.txt
  setup.bat
  run.bat
  run_tests.bat
```

## Why argparse

Stdlib, zero extra dependency, sufficient for the 4 stub commands this
project needs. Can swap to `click`/`typer` later without much rework since
command logic is thin.

## Data contract

See **`CONTRACT.md`** — **locked** as of Week 1 close. Drift object shape
and mock remediation method signatures. Week 2/3 code depends on this
shape; changes after this point need team agreement.

## Troubleshooting

- **`ModuleNotFoundError: rich` / `networkx`** — venv not activated, or
  `pip install -r requirements.txt` didn't run. Re-run `setup.bat`.
- **`python` not recognized** — Python not on PATH; reinstall Python and
  check "Add to PATH" during install.
- **Tests not found** — run `pytest` from the project root (where
  `requirements.txt` lives), not from inside `aerodrift/`.

## Completed (Day 1)

- [x] Project scaffolding and package layout
- [x] CLI entrypoint with stub commands
- [x] Rich dashboard shell (static layout)
- [x] Stub modules for Week 3–4 work
- [x] Placeholder modules for A/B's parts
- [x] Test suite (7 tests passing)

## Completed (Day 2)

- [x] Real CLI argument surface for all 4 commands
- [x] Validation for `remediate` required args
- [x] Global `--verbose` / `--version` flags
- [x] Expanded test suite (16 tests passing)

## Completed (Day 3-4)

- [x] `CONTRACT.md` drafted — drift object shape + mock remediation signatures
- [x] Dashboard rewritten to be drift-aware (healthy vs drifted styling)
- [x] Dashboard split into independently-testable helper functions
- [x] Expanded test suite (25 tests passing)

## Completed (Day 5 — Week 1 done)

- [x] `aerodrift demo` command for previewing the dashboard with sample data
- [x] `CONTRACT.md` finalized/locked for Week 2
- [x] Test suite (27 tests passing)

## Completed (Week 2, Day 1)

- [x] Real topology rendering — dashboard walks actual graph nodes/edges
- [x] Drift-to-red-highlighting wired end-to-end (`affected_node` match)
- [x] Mock graph placeholder for standalone dev (`build_mock_graph()`)
- [x] Test suite (34 tests passing)

## Completed (Week 2, Day 2)

- [x] `scan` and `status` wired to real graph + drift pipeline (no longer stubs)
- [x] `--demo-data` flag on `scan`/`status` for testing without B's real detection
- [x] `status --json` returns real JSON drift data
- [x] Test suite (38 tests passing)

## Completed (Week 2, Day 3)

- [x] Real `detect_drift()` — NetworkX path-finding, internet → sensitive resource
- [x] Direct vs indirect exposure classification
- [x] Performance verified (<5s on 500-node graph, mid-review checkpoint)
- [x] Test suite (46 tests passing)

## Completed (Week 2, Day 4)

- [x] `mid-review-demo` command — scripted, timed joint-demo flow
- [x] Dashboard verified correct with multiple simultaneous drifts
- [x] Test suite (50 tests passing)

## Completed (Week 2, Day 5 — Week 2 done)

- [x] Topology table capped at 25 rows with truncation summary (drifted
      nodes always shown in full)
- [x] Drift-object parsing hardened against malformed entries
- [x] Test suite (53 tests passing)

## Week 2 summary

- Dashboard renders real (mock) topology with drift highlighted in red
- `detect_drift()` placeholder performs genuine NetworkX path-finding
- `mid-review-demo` provides a one-command checkpoint rehearsal
- Rendering is defensive against larger/messier real data

## Completed (Week 3, Day 1)

- [x] Real `ast`-based `generate_remediation_code()` — builds and
      unparses `revoke_security_group_ingress(sg_id, rule)` calls
- [x] Unsupported/missing-field error handling with clear exceptions
- [x] Injection-safety confirmed (values via `ast.Constant`)
- [x] `remediate` CLI wired to real codegen
- [x] Test suite (63 tests passing)

## Remaining before Week 3 continues

- [ ] **Confirm real contract with Person B** — `open_ingress` /
      `public_db_exposure` type names and the mock signature are drawn
      from `CONTRACT.md`'s draft, not yet confirmed
- [ ] Build the sandboxed `exec()` executor (`sandbox.py`) — next step,
      to actually run the generated code against Person A's mock methods
- [ ] Extend codegen once Person A adds more mock remediation methods
      (currently only `revoke_security_group_ingress` exists)
- [ ] Handle `indirect_exposure` drift type once its remediation
      mapping is defined by the team
