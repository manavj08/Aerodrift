# AeroDrift — Person C Workstream (Remediation, CLI & Reporting)

Agentic cloud topology & remediation engine. This repo covers **Person C's**
individual assignment: CLI, Rich dashboard, AST-based code generator,
sandboxed executor, and PDF incident reports.

Status: **Week 2, Day 1 — real topology rendering.**

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
```

Or manually:
```
venv\Scripts\activate
python -m aerodrift.cli.main scan
python -m aerodrift.cli.main demo
python -m aerodrift.cli.main demo --healthy
```

`demo` now shows a real (mock) topology table with drifted rows in red —
run it to see Week 2's rendering work.

## Test

```
run_tests.bat
```

Or manually:
```
venv\Scripts\activate
pytest -v
```

Expected: **34 passed**.

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

## Remaining (Week 2)

- [ ] Replace `aerodrift/graph/topology.py` placeholder with Person B's
      real module once delivered — swap point is `build_mock_graph()` /
      `detect_drift()`
- [ ] Wire `scan`/`status` commands to the real graph + live drift detection
- [ ] Mid-project review: joint demo, drift detection under 5 seconds
