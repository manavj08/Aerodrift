# PROJECT_SUMMARY — AeroDrift (team merge: A + B + C)

## Quick overview
Person C's CLI/dashboard/remediation workstream, merged with Person A's
real ingestion and Person B's real graph builder. Currently at Week 3,
Day 1 + integration fix.

## Tech stack
- Python 3.10+
- Rich (CLI dashboard)
- NetworkX (graph)
- boto3 + moto (mock AWS ingestion — Person A)
- pytest (testing)
- argparse (CLI, stdlib)

## What works today
- `aerodrift scan` / `status` — graph + drift detection against Person
  C's placeholder mock graph (real detection still Person B's to build)
- Real (mock-graph) dashboard: topology table + drift-in-red highlighting
- `mid-review-demo` — scripted Week 2 checkpoint walkthrough
- `remediate` — real AST-based code generation for
  `revoke_security_group_ingress` (not yet executed — sandbox is next)
- **Real ingestion → graph pipeline**: Person A's mock EC2 state now
  flows through `adapter.py` into Person B's `build_graph()`, with the
  internet node correctly synthesized so path-finding works
- 76 passing tests

## Known gaps (see CONTRACT.md)
- `detect_drift()` is still Person C's placeholder logic — Person B has
  not yet delivered real drift detection
- Even with the pipeline fix, `detect_drift()` finds no drift on real
  ingestion data yet: `SENSITIVE_RESOURCE_TYPES` doesn't cover security
  groups, and there's an unresolved `"security_group"` vs
  `"SecurityGroup"` casing mismatch — needs a team decision
- Sandbox (`sandbox.py`) and PDF reports (`pdf_report.py`) are still
  stubs (Week 3 Day 2+ / Week 4 work)
- `aerodrift/ingestion/adapter.py` is explicitly temporary — delete once
  A and B agree on one real ingestion→graph shape

## Quick start
```
setup.bat
run.bat demo
run_tests.bat
```

## Important note
`aerodrift/graph/topology.py`'s `detect_drift()` is still a placeholder
— swap for Person B's real detection logic as soon as it's available.
