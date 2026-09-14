# CHANGELOG

## Week 2, Day 4
- Added `mid-review-demo` CLI command: scripted, timed walkthrough of
  the Week 2 checkpoint flow (drift a mock SG → detect <5s → dashboard
  shows red).
- Verified dashboard correctness with multiple simultaneous drifted
  resources (previously only tested with a single drift).
- Added `tests/test_cli.py` coverage for `mid-review-demo`; added
  multi-drift tests to `tests/test_dashboard.py`.

## Week 2, Day 3
- `detect_drift()` placeholder is now real logic: NetworkX path-finding
  from `0.0.0.0/0` to sensitive resources (`database` nodes).
- Classifies drift as `public_db_exposure` (direct edge) or
  `indirect_exposure` (reachable via intermediate hops).
- `scan`/`status` now show genuine drift without `--demo-data`.
- Added performance test: detection on a 500-node graph in <5s, per the
  Week 2 mid-project review checkpoint.
- Updated `tests/test_graph_placeholder.py` and `tests/test_cli.py` to
  match real (non-empty) default detection output.

## Week 2, Day 2
- `scan` and `status` wired to real `build_mock_graph()` +
  `detect_drift()` pipeline — no longer stub print statements.
- Added `--demo-data` flag to `scan`/`status` for testing drift
  highlighting before Person B's real detection lands.
- `status --json` returns real JSON, not a stub string.
- `--watch` now prints an honest "not implemented" note instead of a
  generic stub message.
- Updated `tests/test_cli.py` — replaced 2 stale stub-assertion tests
  with 6 real pipeline tests.

## Week 2, Day 1
- `_build_topology_panel()` now renders real graph nodes/edges instead of
  a placeholder row; drifted nodes highlighted red per `affected_node`
  match against drift objects.
- `build_layout()` / `render_shell()` gained a `graph` parameter.
- Added `build_mock_graph()` to `aerodrift/graph/topology.py` placeholder
  — swap point for Person B's real module.
- `aerodrift demo` now shows the mock graph through real rendering.
- Added `tests/test_graph_placeholder.py`; expanded `test_dashboard.py`.

## Day 5 (Week 1 — complete)
- Added `aerodrift demo [--healthy]` CLI command — renders the dashboard
  with sample drift data matching the contract shape.
- `CONTRACT.md` marked locked for Week 2 start.
- Expanded `tests/test_cli.py` with 2 new tests for `demo`.

## Day 3-4 (Week 1)
- Added `CONTRACT.md` — drift object shape and mock remediation method
  signatures (draft, to be confirmed with Person A/B).
- Rewrote `dashboard.py`: drift-aware `build_layout(drifts=...)`, split
  into `_build_header` / `_build_topology_panel` / `_build_drift_list_panel`
  / `_build_footer` helpers for independent testing and Week 2 swap-in.
- Expanded `tests/test_dashboard.py` from 2 to 11 tests.

## Day 2 (Week 1)
- `remediate` command now requires `--sg-id` and `--rule`; exits 2 with an
  error message if missing.
- Added `--watch` to `scan`, `--json` to `status`, `--dry-run` to
  `remediate`, `--output` to `report`.
- Added global `--verbose` / `-v` and `--version` flags.
- Expanded `tests/test_cli.py` from 3 to 12 tests covering every new flag.

## Day 1 (Week 1)
- Initial project scaffolding, CLI stub, Rich dashboard shell, stub modules
  for Week 3–4 work, placeholder modules for Person A/B.
