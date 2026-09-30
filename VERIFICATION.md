# Verification — v1.0.0

What was actually run for the final release, and what was not.

## Verified

* `python -m pytest -q` → **192 passed** (Python 3.12, boto3 1.43.92,
  moto 5.2.3, networkx 3.6.1, rich 13.9.4, reportlab 4.4.10, pypdf 4.3.1).
* `final-demo`: three manual SG changes (`open-db`, `open-all-app`,
  `open-ssh`) detected **0.83 s** after the change at a 1 s poll interval
  (ingest 31 ms, graph query 0.9 ms); all three revoked by AST-generated code
  in the sandbox and verified healed (~0.04 s); legitimate rules (443/80 on
  web-sg, app-sg→db-sg 5432, internal SSH) untouched; SQLite
  `diff baseline latest` empty after healing; 3-page PDF rendered to images
  and inspected (banner, summary, incident table, per-incident code boxes,
  diff section, footers).
* `mid-review-demo`: detection well under the 5 s target; drifted SG and DB
  shown in red (asserted on rendered segment styles in `test_dashboard.py`).
* Every CLI command is exercised by `tests/test_cli.py`, including the
  refusal paths (`--live` without `--yes` → exit 2, `--sg-id` without
  `--rule` → exit 2, `scan --live --inject` → exit 2) and history/diff/report
  against a database produced by a real daemon run.
* Sandbox: rejects imports, extra statements, dunder names, non-literal
  arguments, disallowed actions and injection attempts through drift ids /
  rule text (`test_sandbox.py`, `test_codegen.py`).
* Performance: `detect_drift` with a baseline on a 20k-node synthetic graph
  runs in < 0.5 s (was 22 s before the BFS fix).
* Dashboard renders without broken borders at 90, 120 and 160+ columns.

## Not verified

* **Real AWS.** The `--live` path uses the same collector and remediation
  code as the simulator, but it has not been run against a real account.
  Start read-only: `scan --live` / `daemon --live --no-heal`.
* The `.bat` scripts were not run on Windows.
* Exposure is inferred from security groups only (no route-table / IGW /
  NACL / public-IP checks) — see README → Known limitations.
