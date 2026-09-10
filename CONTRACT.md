# Data Contract — Locked Week 1, Day 3-4 Sync

Agreed between Person A (ingestion), Person B (graph/drift), and
Person C (remediation/CLI/reporting).

> **Note:** This is Person C's working draft, written from the project
> spec. Confirm the exact field names/types with A and B in your actual
> sync meeting and update this file — it's the source of truth for
> `codegen.py` (Week 3) and the dashboard (Week 2).

## 1. Drift object (from Person B)

Shape that `detect_drift(graph)` returns, one entry per drifted resource:

```python
{
    "drift_id": str,          # unique id, e.g. "drift-001"
    "type": str,               # e.g. "open_ingress", "public_db_exposure"
    "affected_node": str,      # resource id in the graph, e.g. "sg-0a1b2c3"
    "offending_edge": {
        "source": str,          # e.g. "0.0.0.0/0"
        "target": str,          # e.g. "sg-0a1b2c3"
        "rule": str,             # e.g. "0.0.0.0/0:22/tcp"
    },
    "severity": str,            # "critical" | "high" | "medium" | "low"
    "detected_at": str,         # ISO 8601 timestamp
}
```

## 2. Mock remediation method signatures (from Person A)

Functions Person C's sandbox will call via generated code:

```python
def revoke_security_group_ingress(sg_id: str, rule: str) -> dict:
    """Returns {"status": "success"|"failed", "message": str}"""

# Additional mock methods to be added by Person A as new drift types
# are supported (e.g. detach_public_ip, restrict_s3_bucket_policy).
```

## 3. What Person C's codegen consumes

Given a drift object, `codegen.generate_remediation_code(drift)` maps
`drift["type"]` to the correct mock remediation call, using
`drift["affected_node"]` and `drift["offending_edge"]["rule"]` as the
call arguments.

## 4. Open items (confirm with team)

- [ ] Exact enum values for `type` and `severity`
- [ ] Whether `offending_edge` can be `null` for non-edge drift types
- [ ] Timestamp format/timezone convention
- [ ] Error contract if a mock remediation method fails
