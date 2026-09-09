# Verification — Week 1, Day 1

## Verified

- `python -m venv venv` succeeds.
- `pip install -r requirements.txt` succeeds (rich, networkx, pytest).
- `python -m aerodrift.cli.main scan` runs, exits 0, prints stub message.
- `python -m aerodrift.cli.main status` runs, exits 0, prints stub message.
- `aerodrift.cli.dashboard.build_layout()` builds a `rich.layout.Layout`
  with header/topology/drift_list/footer regions, no errors.
- `pytest -v` — **7/7 tests passed**:
  - `test_cli.py` (3 tests) — CLI commands run, missing command exits non-zero
  - `test_dashboard.py` (2 tests) — layout builds, regions exist
  - `test_codegen.py` (1 test) — confirms `NotImplementedError` (expected, Week 3 work)
  - `test_sandbox.py` (1 test) — confirms `NotImplementedError` (expected, Week 3 work)

## Not verified (out of scope for Day 1)

- `remediate` and `report` CLI commands — stub print only, no real logic yet.
- Dashboard with live data — Week 2 work.
- `.bat` scripts were not run in this environment (Linux sandbox); logic is
  standard venv activation + pip install / pytest invocation, verified
  equivalent commands manually on Linux. Test on Windows before relying on them.

## Known limitations

- `ingestion/mock_aws.py` and `graph/topology.py` are placeholders owned by
  Person C only to unblock standalone testing — they must be replaced with
  Person A's and Person B's real modules once shared.
