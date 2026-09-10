# Data Contract — Locked Week 1 (Day 3-4 sync, finalized Day 5)

Agreed between Person A (ingestion), Person B (graph/drift), and
Person C (remediation/CLI/reporting).

**Status: LOCKED for Week 2 start.** Any change after this point must be
re-communicated to all three engineers, since dashboard rendering,
codegen, and the sandbox all depend on this shape.

> Field names/types below follow the project spec. If your team's actual
> sync meeting produced different field names, edit this section — this
> file is the single source of truth for Week 2/3 code.

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

## 5. Sample data (for Week 1 dashboard preview)

Person C's `aerodrift demo` command renders the dashboard against sample
drift objects matching this shape (`aerodrift/cli/main.py::SAMPLE_DRIFTS`).
Run `aerodrift demo` to preview the drifted state, or `aerodrift demo
--healthy` for the no-drift state.
