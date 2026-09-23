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

**Status as of Week 3 Day 2**: Person A has delivered real ingestion
(`aerodrift/ingestion/`) but has **not yet delivered real mock
remediation methods**. `aerodrift/remediation/mock_methods.py` is Person
C's placeholder implementing the signature above, built so
`sandbox.py` has something real to execute and test against. Swap it
for Person A's real module once delivered — `sandbox.run_sandboxed()`'s
`allowed_globals` parameter is the seam; no other code should need to
change if the signature matches.

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
- [ ] **Ingestion -> graph shape was never actually agreed on.** Person A's
      `get_mock_ec2_state()` returns `Resource`/`Relationship` dataclasses
      (`aerodrift/ingestion/schema.py`); Person B's `build_graph()`
      (`aerodrift/graph/builder.py`) expects dicts with a different,
      non-overlapping key set. `aerodrift/ingestion/adapter.py` is a
      **temporary** bridge with guessed defaults (`exposure`, `cidr`,
      `port`, `protocol`, `direction` are not real data) — it is not a
      substitute for A and B agreeing on one real shape. Delete it once
      they do.
- [x] ~~`detect_drift()` found zero drift on real A+B pipeline output~~ —
      **FIXED**: `adapter.py` now synthesizes an internet node
      (`INTERNET_NODE = "0.0.0.0/0"`) and an inbound edge whenever a
      resource's `attributes["ingress"]` string shows a public
      (`0.0.0.0/0:PORT`) rule, since nothing in the real pipeline created
      that node before. See `adapter.py`'s `_synthesize_internet_exposure()`
      docstring — this is a workaround for one specific string format
      Person A's mock client happens to produce today, not a general
      ingestion feature. Covered by `tests/test_adapter.py`.
- [ ] **STILL OPEN, not fixed by the above**: even with the internet node
      now present, `detect_drift()` reports **zero drift** on the real A+B
      pipeline (`tests/test_adapter.py::test_detect_drift_still_finds_nothing_on_real_data_pending_type_alignment`
      documents this). Two compounding causes:
      1. `SENSITIVE_RESOURCE_TYPES` in `topology.py` is `{"database", "rds"}`
         — an internet-facing `SecurityGroup`/`EC2Instance` alone is never
         flagged. Team needs to decide: should a directly-exposed SG/EC2
         count as drift on its own, or only when it fronts something in
         `SENSITIVE_RESOURCE_TYPES`?
      2. Casing mismatch: `topology.py`'s own mock graph uses lowercase
         `"security_group"`; Person A's real mock data uses PascalCase
         `"SecurityGroup"`. If SGs are added to `SENSITIVE_RESOURCE_TYPES`,
         the exact casing needs to be confirmed and made consistent, or
         `detect_drift()` needs to normalize case.
      I deliberately did NOT guess at either of these — they're policy
      decisions (what counts as drift, what casing is authoritative), not
      shape-bridging like the internet-node fix above.
- [ ] `SENSITIVE_RESOURCE_TYPES` in `topology.py` was widened to include
      `"rds"` alongside `"database"` because Person B's `sample_data.py`
      labels DB nodes `"rds"` (real-AWS-style typing) while the original
      placeholder only recognized `"database"`. This was my inference to
      keep the demo pipeline from silently showing zero drift — not a
      confirmed team decision. Confirm the real resource-type enum.
- [ ] `graph/contract.py`'s `NODE_FIELDS`/`EDGE_FIELDS` (Person B's own
      draft schema) were never cross-checked against this file or against
      Person A's ingestion schema — see the adapter note above.

## 5. Sample data (for Week 1 dashboard preview)

Person C's `aerodrift demo` command renders the dashboard against sample
drift objects matching this shape (`aerodrift/cli/main.py::SAMPLE_DRIFTS`).
Run `aerodrift demo` to preview the drifted state, or `aerodrift demo
--healthy` for the no-drift state.
