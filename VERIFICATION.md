# Verification — Week 1, Day 1–4

## Verified — Day 3-4

- `build_layout(drifts=[])` renders the healthy state without error.
- `build_layout(drifts=[{...}])` renders the drifted state without error.
- Each dashboard helper (`_build_header`, `_build_topology_panel`,
  `_build_drift_list_panel`, `_build_footer`) builds independently.
- `pytest -v` — **25/25 tests passed** (16 Day 1-2 tests retained + 9 new
  dashboard tests).

## Not verified — Day 3-4

- `CONTRACT.md` field names/types are a **draft based on the project
  spec**, not confirmed with Person A/B in an actual meeting. Update the
  file and re-verify against their real modules once available.
- Dashboard drift-aware styling has not been visually reviewed against
  real drift data (no real data exists yet — Week 2 work).

## Verified — Day 2

- All 4 CLI commands accept and correctly handle their new flags
  (`--watch`, `--json`, `--sg-id`/`--rule`/`--dry-run`, `--output`).
- `remediate` without `--sg-id`/`--rule` exits with code 2 and prints an
  error to stderr (validated, not just argparse's own error).
- `--verbose` and `--version` global flags work.
- `pytest -v` — **16/16 tests passed** (7 Day 1 tests retained + 9 new).

## Verified — Day 1

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
