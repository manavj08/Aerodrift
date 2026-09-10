# CHANGELOG

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
