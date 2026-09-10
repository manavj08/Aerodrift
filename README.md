# AeroDrift — Person C Workstream (Remediation, CLI & Reporting)

Agentic cloud topology & remediation engine. This repo covers **Person C's**
individual assignment: CLI, Rich dashboard, AST-based code generator,
sandboxed executor, and PDF incident reports.

Status: **Week 1, Day 2 — CLI expansion.**

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
```

Or manually:
```
venv\Scripts\activate
python -m aerodrift.cli.main scan
```

## Test

```
run_tests.bat
```

Or manually:
```
venv\Scripts\activate
pytest -v
```

Expected: **16 passed**.

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

## Data contract (to finalize Week 1, Day 3-4 sync)

Not yet locked with Person B/A. Once agreed, document here:
- Drift object shape (type, affected node, offending edge/rule)
- Mock remediation method signatures (e.g. `revoke_security_group_ingress(sg_id, rule)`)

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

## Remaining (Week 1, Days 3–5)

- [ ] Day 3–4: sync with A & B, lock data contract
- [ ] Day 5: finish dashboard shell polish, document contract
