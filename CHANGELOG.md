# CHANGELOG

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
