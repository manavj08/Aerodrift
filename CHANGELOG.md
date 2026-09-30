# CHANGELOG

## v1.0.0 — Project completion
- **Ingestion**: new `AWSCollector` (asyncio.gather + to_thread, semaphore,
  pagination, multi-region, per-call timings) for VPCs, subnets, SGs, EC2
  and RDS; `IngressRule` model; moto-backed `SimulatedCloud` with drift
  scenarios `open-db`, `open-ssh`, `open-all-app`, `shadow-sg`.
- **Graph**: `build_topology` with contains/attached/ingress edges, SG-reference
  and private-CIDR expansion; real `detect_drift` (public DB exposure, admin/all
  port exposure, baseline-aware multi-hop `indirect_exposure`); fixed a
  quadratic path search (22 s → < 0.5 s on 20k nodes); topology diffs and
  JSON (de)serialisation.
- **Remediation**: `affected_node` is now the security group; AST code
  generator; AST-allowlist sandbox with empty builtins and a scoped client;
  function names collapse repeated underscores so hostile drift ids can
  never produce dunder names.
- **Persistence**: SQLite snapshot/incident store with diff by id,
  `baseline`, `latest` or timestamp.
- **Daemon**: poll → detect → heal → immediate verify → persist loop.
- **CLI**: `scan --watch/--heal/--inject`, `status`, `remediate`, `daemon`,
  `history`, `diff`, `report --from-db`, `mid-review-demo`, `self-heal-demo`,
  `final-demo`; `--live` changes require `--yes`; `python -m aerodrift`.
- **Dashboard**: full topology tree with per-rule ✓/✗, attack paths,
  remediation log; stacks panels on terminals narrower than 150 columns.
- **PDF**: status banner, executive summary, per-incident detail with the
  generated code, topology diffs.
- Removed `ingestion/adapter.py`, `remediation/mock_methods.py` and their tests.
- Tests: 192 passing (dashboard, PDF and CLI suites rewritten).

## Week 4
- Wired the `report` CLI command to `generate_incident_report()`: detects
  drift (or uses `--sg-id`/`--rule`), generates remediation code, runs it
  in the sandbox (skippable with `--no-execute`), writes a real PDF.
  `--sg-id` without `--rule` (or the reverse) exits 2 with an error.
- Added `final-demo` CLI command: detect -> generate -> execute -> PDF
  report, per the Week 4 Definition of Done.
- Replaced the two stub-output `report` tests (which would now write PDFs
  into the working directory) with `tmp_path`-based tests that check the
  file is a real PDF; added tests for targeting, error paths, and that
  `--no-execute` really does not invoke the mock remediation.
- Added 4 `final-demo` tests.
- Extended the `public_db_exposure` open item in `CONTRACT.md` to note
  the mismatch now also lands in the generated PDF, and added an
  ownership table (section 4b) recording which Person A / Person B
  deliverables are still placeholders or absent.
- Test suite: 96 -> **115 passing**.

## Week 3 close-out
- Added `self-heal-demo` CLI command: scripted, timed walkthrough of the
  full loop (detect → generate → execute → re-render), rehearsing Week
  4's final review ("full self-heal loop + PDF report").
- Explicitly documented (in code, CLI output, and `CONTRACT.md`) that
  `public_db_exposure` drift's `affected_node` (a database) cannot be
  correctly remediated by the only mock method that exists
  (`revoke_security_group_ingress`, which expects a security group) —
  the demo still runs it to prove the mechanism, not the correctness.
- Added 5 tests to `tests/test_cli.py`, including one asserting the
  mismatch-disclosure text stays present.
- Test suite: 92 → **96 passing**.

## Week 3, Day 2
- Implemented real `sandbox.run_sandboxed()`: restricted `exec()`,
  minimal safe-builtins allowlist, only executes single-call statements
  against a caller-supplied `allowed_globals` set.
- Added `aerodrift/remediation/mock_methods.py` — placeholder mock
  remediation method, since Person A has not yet delivered real mock
  remediation methods (only ingestion so far). See `CONTRACT.md` section 2.
- Wired `remediate` CLI to actually execute generated code (previously
  only printed it); `--dry-run` now meaningfully skips execution.
- Added 13 sandbox tests (correctness + security: blocked imports, eval,
  disallowed calls, multi-statement injection, invalid syntax) and 4
  `mock_methods.py` placeholder tests.
- Updated 2 `test_cli.py` remediate tests to assert on real sandbox
  execution output instead of the old stub message.
- Test suite: 76 → **92 passing**.

## Merge — Person A (Ashutosh) + Person B (Prasanth) + Person C combined
- **Person A (ingestion):** added real `aerodrift/ingestion/mock_client.py`
  (`get_mock_ec2_state()`, moto-backed EC2/SecurityGroup mock) and
  `aerodrift/ingestion/schema.py` (`Resource`, `Relationship` dataclasses),
  replacing the placeholder `mock_aws.py`. 2 tests added.
- **Person B (graph):** added real `aerodrift/graph/builder.py`
  (`build_graph(resources, connections)`) and `aerodrift/graph/contract.py`
  (field-name reference). `topology.py`'s `detect_drift()` is still
  Person C's placeholder — Person B has not yet delivered real drift
  detection, only graph construction. 4 tests added.
- **Integration gap found and bridged, not silently resolved:** Person
  A's dataclass output and Person B's dict-based `build_graph()` input use
  incompatible, never-agreed-upon shapes. Added
  `aerodrift/ingestion/adapter.py` as an explicit, documented **temporary**
  bridge (see `CONTRACT.md` open items) — not a substitute for the team
  agreeing on one real ingestion/graph contract. 3 new tests cover it,
  including a live end-to-end run (ingestion → adapter → graph →
  `detect_drift`) confirming the pipeline executes without error.
- Fixed a latent bug: Person B's `sample_data.py` labels DB nodes `"rds"`,
  but `detect_drift()`'s `SENSITIVE_RESOURCE_TYPES` only recognized
  `"database"` — his own sample data would have shown zero drift.
  Widened the set; flagged in `CONTRACT.md` as unconfirmed.
- Test suite: 63 (Person C, Week 3 Day 1) + 2 (A) + 4 (B) + 3 (adapter)
  = **72 passing**.

## Adapter fix — real pipeline now actually detects drift (partially)
- **Bug found**: running the real ingestion → adapter → graph → 
  `detect_drift()` pipeline by hand (not just the existing "does it run"
  tests) showed it silently found **zero drift**, despite Person A's mock
  data having a genuinely open `0.0.0.0/0:22` security group rule.
  Root cause: `detect_drift()` requires a literal graph node named
  `"0.0.0.0/0"` to search from, and nothing in the real pipeline ever
  created it — the open-ingress fact sat unused in
  `Resource.attributes["ingress"]`.
- **Fix**: `adapter.py` gained `_synthesize_internet_exposure()`, which
  parses each resource's `ingress` attribute (format:
  `"{cidr}:{port}"`) and, when the CIDR is `0.0.0.0/0`, adds the missing
  internet node and an inbound edge to that resource. Clearly marked as
  a workaround for one specific string format Person A's mock client
  produces today — not a general ingestion feature.
- **Still open, not fixed**: even with the internet node present,
  `detect_drift()` now correctly finds a path from the internet to the
  security group, but still reports **zero drift**, because
  `SENSITIVE_RESOURCE_TYPES` (`{"database", "rds"}`) doesn't cover
  `SecurityGroup`/`EC2Instance`, and there's a separate casing mismatch
  (`topology.py`'s own mock graph uses `"security_group"`, Person A's
  real data uses `"SecurityGroup"`). Deliberately NOT guessed at — see
  `CONTRACT.md` open items; this needs a team decision on what counts as
  drift and which casing is authoritative.
- Added 4 new tests to `tests/test_adapter.py`: 2 proving the internet
  node/edge are now synthesized correctly, 1 proving the full pipeline
  now has real internet→SG reachability, and 1 that deliberately
  documents (rather than hides) the remaining zero-drift gap. Fixed 1
  stale test whose hardcoded node/edge counts didn't account for the
  new synthesized node.
- Test suite: 72 → **76 passing**.

## Week 3, Day 1
- Implemented real `codegen.generate_remediation_code()` using Python's
  `ast` module — builds and unparses
  `revoke_security_group_ingress(sg_id, rule)` calls.
- Added `UnsupportedDriftTypeError` and `MissingDriftFieldError` for
  clear failure modes.
- Wired `remediate` CLI command to real codegen (was a stub).
- Replaced the old placeholder `test_codegen.py` with 11 real tests,
  including an injection-safety test.
- **Note:** built against `CONTRACT.md`'s draft shape — pending
  confirmation from Person B.

## Week 2, Day 5 (Week 2 complete)
- Topology table capped at `MAX_TOPOLOGY_ROWS` (25); drifted nodes always
  shown in full, healthy nodes beyond the cap summarized.
- `_drifted_node_ids()` hardened against malformed drift entries.
- Added 3 defensive-rendering tests.

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
