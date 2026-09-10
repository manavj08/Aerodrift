# PROJECT_SUMMARY — AeroDrift (Person C)

## Quick overview
Scaffolding for Person C's workstream: CLI, Rich dashboard, remediation
codegen/sandbox, PDF reports. Currently at Week 1, Day 1.

## Tech stack
- Python 3.10+
- Rich (CLI dashboard)
- NetworkX (graph — Person B owns real logic; placeholder here)
- pytest (testing)
- argparse (CLI, stdlib)

## What works today
- `aerodrift scan` / `status` / `remediate` / `report` — CLI stub commands
- Static Rich dashboard layout shell
- 7 passing tests

## Not built yet
- Real drift detection / graph rendering (Week 2)
- AST code generator, sandbox exec (Week 3)
- PDF report generation (Week 4)

## Quick start
```
setup.bat
run.bat demo
run_tests.bat
```

## Important note
`ingestion/mock_aws.py` and `graph/topology.py` are **placeholders** —
swap for Person A's and Person B's real code as soon as it's available.
