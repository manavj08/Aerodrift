# Data Contract — v1.0.0 (final)

This supersedes the Week-1 contract. The original fields are unchanged;
fields were only **added**. All open items from earlier weeks are resolved
(see the bottom of this file).

## 1. Graph (`graph/topology.py::build_topology`)

`networkx.DiGraph`. Node ids are AWS ids; the internet is the node
`"0.0.0.0/0"` (`config.INTERNET_NODE`).

Node attributes: `name`, `resource_type` (canonical lower-case:
`internet | vpc | subnet | security_group | ec2 | rds`), `vpc_id`,
`sensitive` (bool), plus type-specific extras (e.g. `cidr`).

Edge attribute `kind`:

| kind | direction | meaning |
|---|---|---|
| `contains` | VPC → subnet → resource | placement |
| `attached` | SG → resource | SG protects resource |
| `ingress` | source → SG | traffic admitted; `rules=[{source, protocol, from_port, to_port, source_kind, rule}]` |

`source` of an ingress edge is the internet node, another SG (SG
reference), or an instance in a private CIDR the rule admits.

## 2. Drift object (`detect_drift(graph, baseline=None)`)

```python
{
    # --- original Week-1 fields ---
    "drift_id": "drift-666cf09401",    # stable sha1 of (type, sg, rule, target)
    "type": "public_db_exposure",      # | "open_ingress" | "indirect_exposure"
    "affected_node": "sg-db",          # ALWAYS the security group to fix
    "offending_edge": {"source": "0.0.0.0/0", "target": "sg-db", "rule": "0.0.0.0/0:5432/tcp"},
    "severity": "critical",            # critical | high | medium | low
    "detected_at": "2026-09-30T12:39:35+00:00",
    # --- added ---
    "affected_name": "db-sg",
    "target_resource": "db-prod-01", "target_name": "db-prod-01",
    "rule_detail": {"source": "0.0.0.0/0", "protocol": "tcp", "from_port": 5432,
                    "to_port": 5432, "source_kind": "cidr"},
    "path": ["0.0.0.0/0", "sg-db", "db-prod-01"],
    "path_names": ["Internet", "db-sg", "db-prod-01"],
    "description": "db-prod-01 is reachable from the internet via db-sg (0.0.0.0/0:5432/tcp)",
    "remediation": {"action": "revoke_security_group_ingress", "group_id": "sg-db",
                    "rule": "0.0.0.0/0:5432/tcp"},
}
```

Rule strings are `SOURCE:PORTS/PROTO` — `0.0.0.0/0:22/tcp`,
`0.0.0.0/0:1000-2000/udp`, `0.0.0.0/0:all/all`, `sg-abc:8080/tcp`.

## 3. Remediation

`generate_remediation_code(drift) -> str` returns source for exactly one
function `remediate_<slug>(ec2)` that returns
`ec2.revoke_security_group_ingress(GroupId=..., IpPermissions=[...])`.

`run_remediation(code, client, dry_run=False) -> dict` returns
`{"status": "success" | "noop" | "failed" | "validated", "message": str, ...}`
and raises `SandboxViolation` if the code fails AST validation. The client is
a real boto3 EC2 client (moto in tests); there are no mock methods.

`remediate(drift, client, dry_run=False) -> RemediationRecord` with
`to_dict()` keys: `drift, code, result, status, generated_at, executed_at,
verified, detection_latency_s, time_to_heal_s`.

## 4. Persistence (`persistence/store.py`)

SQLite tables `snapshots` (graph as JSON via `graph_to_dict`, node/edge/drift
counts, label, `is_baseline`) and `incidents` (record JSON, status,
verified). References accepted by `resolve()`/`diff()`: snapshot id,
`latest`, `baseline`, or an ISO timestamp (latest snapshot at or before it).

## Resolved open items from earlier weeks

* `affected_node` pointed at the database, not the SG, so remediation
  targeted the wrong resource → now always the SG; the endangered resource is
  `target_resource`.
* Type casing mismatch (`EC2`/`ec2`/`database`) between ingestion and graph →
  canonical lower-case types with `config.normalize_type()` aliases.
* Temporary `ingestion/adapter.py` → removed; the collector emits the graph
  schema directly.
* Placeholder `remediation/mock_methods.py` → removed; generated code calls the
  real boto3 API, exercised against moto.
* Placeholder `detect_drift` → real NetworkX path-finding with baseline
  awareness.
