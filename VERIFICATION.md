# Verification — Week 1 (complete) + Week 2 Day 1-3

## Verified — Week 2 Day 3

- `detect_drift()` correctly identifies the mock graph's direct
  internet→DB edge as `public_db_exposure`, confirmed both via unit
  tests and visual dashboard inspection.
- Indirect exposure (DB reachable via an intermediate hop, no direct
  edge) correctly classified as `indirect_exposure`, reporting the first
  hop as the offending edge.
- Non-sensitive resources (e.g. `ec2`) reachable from the internet are
  correctly NOT reported as drift (only `database` is in
  `SENSITIVE_RESOURCE_TYPES` currently).
- Graphs without the internet node, or with no path to any sensitive
  node, correctly return `[]`.
- **Performance**: detection on a 500-node synthetic graph completes in
  well under 5 seconds (measured, not estimated) — satisfies the
  Week 2 mid-project review checkpoint on the placeholder graph.
- `pytest -v` — **46/46 tests passed** (38 Day 2 tests retained/updated +
  8 new detection + performance tests).

## Not verified — Week 2 Day 3

- Performance against Person B's **real, potentially much larger**
  cloud graph — only tested against a synthetic 500-node chain, not real
  AWS-scale topology.
- `SENSITIVE_RESOURCE_TYPES` currently only includes `database` — if the
  real contract requires more resource types (e.g. S3 buckets, secrets
  managers) as "sensitive," this needs updating once confirmed with B.

## Verified — Week 2 Day 2

- `scan` (no flags) renders the dashboard via the real pipeline, showing
  all-healthy since `detect_drift()` placeholder returns `[]` — confirmed
  visually.
- `scan --demo-data` shows drifted rows in red — confirmed visually.
- `status --demo-data` prints readable drift lines; `status --json
  --demo-data` returns valid parseable JSON matching `SAMPLE_DRIFTS`.
- `status --json` (no demo data) returns `[]`.
- `pytest -v` — **38/38 tests passed** (34 Day 1 tests retained + 4 new
  scan/status pipeline tests, replacing 2 stale stub-assertion tests).

## Not verified — Week 2 Day 2

- `--watch` continuous loop — not implemented, flag only prints a note.
- Real drift detection end-to-end — still blocked on Person B's actual
  `detect_drift()` implementation; today's wiring is verified only
  against the placeholder (empty) and `--demo-data` paths.

## Verified — Week 2 Day 1

- `aerodrift demo` visually confirmed: topology table shows 4 mock
  resources, `sg-0a1b2c3` and `db-prod-01` render with red `DRIFTED`
  status, others show green `healthy`.
- `_build_topology_panel()` correctly falls back to "(no data yet)" when
  `graph=None` or the graph is empty.
- `pytest -v` — **34/34 tests passed** (27 Week 1 tests retained + 4 new
  graph-placeholder tests + 3 new dashboard rendering tests).

## Not verified — Week 2 Day 1

- Rendering against Person B's **real** graph — only tested against
  Person C's own placeholder mock graph. Behavior with B's actual node/
  edge attribute names is unverified until B delivers and this file's
  `build_mock_graph()` swap point is replaced.
- Performance at scale (large graphs) — mock graph has only 4 nodes.

## Verified — Day 5

- `aerodrift demo` renders the dashboard in the drifted state (visually
  confirmed: red drift panel, sample resources listed).
- `aerodrift demo --healthy` renders the healthy state.
- `pytest -v` — **27/27 tests passed** (25 Day 1-4 tests retained + 2 new
  `demo` command tests).

## Not verified — Day 5

- `CONTRACT.md` is marked locked per Person C's own workstream, but has
  **not been confirmed in an actual meeting** with Person A and Person B
  in this environment (no multi-person sync occurred here). Treat the
  "locked" status as Person C's readiness checkpoint — still confirm
  with your teammates before Week 2 work depends on it.

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
