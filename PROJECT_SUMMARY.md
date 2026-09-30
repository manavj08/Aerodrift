# AeroDrift — Project Summary (v1.0.0)

**Status: complete.** Every item in the week-wise plan is implemented,
tested (192 tests) and demonstrable offline.

| Plan item | Where | Evidence |
|---|---|---|
| W1 async boto3 ingestion (VPC/EC2/subnet/SG) | `ingestion/collector.py` | concurrent + paginated + multi-region; `test_collector.py` |
| W1 graph foundations | `graph/topology.py::build_topology` | `test_topology.py` |
| W2 internet → private DB path detection | `graph/topology.py::detect_drift` | direct, admin-port and multi-hop drift; `test_topology.py` |
| W2 Rich topology tree | `cli/dashboard.py` | `test_dashboard.py` |
| Mid-review: manual SG change detected < 5 s | `mid-review-demo` | ~0.8 s; `test_daemon.py`, `test_cli.py` |
| Mid-review: drifted resources in red | dashboard | segment-style test in `test_dashboard.py` |
| W3 ast-generated `revoke_security_group_ingress` | `remediation/codegen.py` | `test_codegen.py` (incl. injection attempts) |
| W3 controlled `exec()` sandbox | `remediation/sandbox.py` | `test_sandbox.py` |
| W4 SQLite history + diff between timestamps | `persistence/store.py`, `history`, `diff` | `test_store.py`, `test_cli.py` |
| W4 PDF incident reports | `reports/pdf_report.py`, `report` | `test_pdf_report.py` |
| Final: autonomous self-healing | `daemon.py`, `daemon`, `final-demo` | `test_daemon.py`, `test_cli.py` |

Run `python -m aerodrift final-demo` to see the whole loop: three manual
security-group changes are injected, detected within a second, remediated with
generated code in the sandbox, verified, stored in SQLite (baseline → latest
diff is empty after healing), and written to `final_incident_report.pdf`.

Limitations are listed honestly in README.md → *Known limitations*; the main
one is that the live-AWS path has not been exercised against a real account.
