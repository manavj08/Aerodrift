# AeroDrift — Agentic Cloud Topology & Remediation Graph

AeroDrift is a self-healing drift-remediation daemon for AWS network security.
It polls the AWS APIs concurrently (boto3 + asyncio), models the estate as a
NetworkX directed graph, finds new paths from the internet (`0.0.0.0/0`) to
private databases, writes the exact `revoke_security_group_ingress` call with
Python's `ast` module, executes it in a restricted `exec()` sandbox, verifies
the fix by re-ingesting, stores every topology snapshot in SQLite, and writes
PDF incident reports. Everything is shown in a Rich terminal dashboard.

Everything runs offline against a **simulated AWS account** (moto), so no
credentials are needed for development, tests or demos. `--live` switches to
real AWS using your normal boto3 credentials.

## Quick start

```bash
python -m venv venv && source venv/bin/activate      # Windows: setup.bat
pip install -r requirements.txt
python -m aerodrift final-demo                        # the whole story in ~5 s
python -m pytest -q                                   # 192 tests
```

On Windows, `run.bat <command>` and `run_tests.bat` wrap the same commands.

## The self-healing loop

```
 boto3 (async, paginated, concurrent)        NetworkX DiGraph
 VPCs / subnets / SGs / EC2 / RDS  ───────▶  internet → SG → instance/DB
            ▲                                        │ detect_drift()
            │ verify (immediate re-collect)          ▼
 sandbox exec() ◀── ast-generated code ◀── drift: SG + offending rule
            │
            └──▶ SQLite snapshots + incidents ──▶ diff / PDF report
```

1. **Ingest** — `AWSCollector` fires `describe_vpcs / subnets /
   security_groups / instances / db_instances` concurrently
   (`asyncio.gather` + `asyncio.to_thread`, bounded by a semaphore, full
   pagination, multiple regions). A full estate ingests in ~30–40 ms on the
   simulator; per-call timings are recorded.
2. **Model** — `build_topology()` produces a directed graph with three edge
   kinds: `contains` (VPC → subnet → resource), `attached` (SG → resource)
   and `ingress` (source → SG, carrying the rules). The internet is a node.
   Rules that reference another SG or a private CIDR are expanded to the
   instances they actually admit, so multi-hop paths are real.
3. **Detect** — `detect_drift(graph, baseline)`:
   * `public_db_exposure` (critical) — a public rule on an SG attached to a
     sensitive resource (RDS, or tagged `aerodrift:sensitive` /
     `Tier=data|database|private`).
   * `open_ingress` — a public rule opening an admin port (22, 3389,
     5985/5986 → high) or all ports (critical).
   * `indirect_exposure` — a rule that is *new since the baseline* and
     creates an internet → … → database path (e.g. the app tier opened to the
     world, which the DB SG trusts). Path-finding BFS starts only from new
     edges, so it stays fast on large graphs (20k nodes < 0.5 s).
   Every drift names the **security group to fix** (`affected_node`), the
   offending rule, the endangered resource and the full attack path.
4. **Generate** — `generate_remediation_code()` builds an `ast.FunctionDef`
   node by node and unparses it, e.g.
   ```python
   def remediate_drift_64ad7c1e04(ec2):
       """AeroDrift auto-remediation for drift-64ad7c1e04 (public_db_exposure): ..."""
       return ec2.revoke_security_group_ingress(GroupId='sg-…', IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 5432, 'ToPort': 5432, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}])
   ```
   Only the offending rule is revoked; legitimate rules stay.
5. **Sandbox** — `run_remediation()` first validates the AST against an
   allowlist (exactly one `remediate_*` function taking `ec2`, a docstring,
   one `return ec2.<allowed action>(...)` with literal-only arguments; no
   imports, names, attributes, dunders or loops), then `exec()`s it with
   `__builtins__ = {}` and hands it a scoped client proxy that exposes only the
   allowed EC2 actions. `InvalidPermission.NotFound` is reported as `noop`.
6. **Verify & persist** — the daemon re-collects immediately, confirms the
   drift is gone, and records snapshots (only when the topology changes) and
   incidents in SQLite.

## Commands

| Command | What it does |
|---|---|
| `scan [--scenario S] [--watch --heal --inject S]` | One-shot (or live-refreshing) dashboard |
| `scan --offline` | Dashboard over built-in mock data, no AWS/moto at all |
| `status [--json]` | Drift list as text or JSON |
| `remediate [--dry-run] [--drift-id ID]` | Generate → sandbox → execute → verify |
| `remediate --sg-id sg-… --rule 0.0.0.0/0:22/tcp` | Manual target (dry-run unless `--live --yes`) |
| `daemon [--db F] [--cycles N/--duration S] [--no-heal] [--report F]` | Continuous poll → detect → heal → verify → persist |
| `history [--db F]` | Stored snapshots and incidents |
| `diff FROM [TO] [--json]` | Topology diff; refs are snapshot ids, ISO timestamps, `baseline` or `latest` |
| `report [--no-execute] [--from-db F] [--output F]` | PDF incident report |
| `demo [--healthy]` | Offline dashboard |
| `mid-review-demo` | Mid-project review: manual SG change detected < 5 s, drift in red |
| `self-heal-demo` | Week 3: detect → generate → sandbox → verify, with dashboards |
| `final-demo [--output F] [--db F]` | Final review: full loop + SQLite diff + PDF |

Simulated drift scenarios (`--scenario` = present at start, `--inject` =
applied while the daemon runs):

* `open-db` — db-sg opened to `0.0.0.0/0:5432` (the use-case story)
* `open-ssh` — web-sg opened to `0.0.0.0/0:22`
* `open-all-app` — app-sg opened to the world on all protocols (indirect path to the DB)
* `shadow-sg` — a new world-open SG attached to nothing (not flagged: no path)

Timestamps for `diff` are resolved to the latest snapshot at or before the
given time, e.g. `aerodrift diff 2026-09-30T12:00 latest`.

### Live AWS

```bash
aerodrift scan --live --region eu-west-1 --profile prod     # read-only
aerodrift daemon --live --no-heal                            # read-only monitoring
aerodrift daemon --live --yes --db prod.db                   # self-healing
```

Anything that changes live AWS requires `--yes`. Required IAM permissions:
`ec2:DescribeVpcs`, `ec2:DescribeSubnets`, `ec2:DescribeSecurityGroups`,
`ec2:DescribeInstances`, `rds:DescribeDBInstances`, and for healing
`ec2:RevokeSecurityGroupIngress`.

## Measured results (simulator, this machine)

| Metric | Target | Measured |
|---|---|---|
| Manual SG change → drift in graph | < 5 s | ~0.8 s at a 1 s poll interval |
| Ingestion (5 concurrent API calls) | — | 30–40 ms |
| Graph drift query | — | ~1 ms (14 nodes); < 0.5 s at 20k nodes |
| Remediation + verification | — | ~0.05 s per drift |

Detection latency is dominated by the poll interval; the graph work is
milliseconds.

## Project layout

```
aerodrift/
  config.py                 canonical types, sensitivity rules, admin ports
  ingestion/  collector.py  async boto3 collector + normalisation
              rules.py      IngressRule model (parse/print/IpPermissions)
              schema.py     Resource / Relationship / CloudState
              simulated_cloud.py  moto-backed 3-tier estate + drift injection
              mock_client.py      original Week-1 mock client
  graph/      topology.py   graph build, drift detection, paths, diffs, (de)serialisation
              builder.py, contract.py   original Week-1 graph builder
  remediation/ codegen.py   ast code generator
               sandbox.py   AST validation + restricted exec
               engine.py    remediate / RemediationRecord
  persistence/store.py      SQLite snapshots + incidents + diff by timestamp
  daemon.py                 self-healing loop
  runtime.py                environments (simulated/live), scenario runner
  cli/        main.py       argparse CLI, demos
              dashboard.py  Rich dashboard + diff table
  reports/pdf_report.py     ReportLab incident reports
tests/                      192 tests (pytest)
```

## Known limitations

* **Live AWS is implemented but untested here** — all tests and demos run on
  moto. Try it read-only (`scan --live`, `daemon --live --no-heal`) first.
* Exposure is modelled at the security-group layer. A world-open SG is
  treated as internet-exposed without checking route tables, internet
  gateways, NACLs or whether an instance has a public IP — this errs on the
  side of flagging.
* Reachability between tiers ignores ports (any allowed SG-to-SG rule counts
  as a hop), so `indirect_exposure` can flag a new public SSH rule on the web
  tier because the web tier can reach the app tier, which reaches the DB.
* Only IPv4/IPv6 CIDR and SG-reference rules are modelled (prefix lists are
  ignored). Egress rules, IAM, and GCP are out of scope.
* The sandbox is defence in depth for code that AeroDrift itself generated;
  CPython `exec()` is not a security boundary for arbitrary hostile code.
