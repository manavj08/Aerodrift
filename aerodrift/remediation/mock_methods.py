"""Placeholder — owned by Person A.

Mock remediation methods the sandbox executes generated code against.
Per CONTRACT.md section 2, Person A's real Week 3 deliverable is mock
methods like `revoke_security_group_ingress(sg_id, rule)` — these have
NOT been received yet (only ingestion, see aerodrift/ingestion/).

This module exists so Person C's sandbox has something real to call and
test against. Replace with Person A's real mock_remediation module once
delivered — the function signature below is the swap seam, matching
CONTRACT.md's documented mock signature.
"""

# In-memory log of "revoked" rules, so callers/tests can assert on what
# the sandbox actually executed without needing real AWS calls.
_revoked_log: list[dict] = []


def revoke_security_group_ingress(sg_id: str, rule: str) -> dict:
    """Mock revocation of a security group ingress rule.

    Returns {"status": "success"|"failed", "message": str}, per
    CONTRACT.md section 2.
    """
    if not sg_id or not rule:
        return {"status": "failed", "message": "sg_id and rule are required"}

    _revoked_log.append({"sg_id": sg_id, "rule": rule})
    return {
        "status": "success",
        "message": f"Revoked ingress rule '{rule}' from security group '{sg_id}' (mock).",
    }


def get_revoked_log() -> list[dict]:
    """Return the in-memory log of mock revocations (for tests/debugging)."""
    return list(_revoked_log)


def clear_revoked_log() -> None:
    """Reset the in-memory log (for test isolation)."""
    _revoked_log.clear()
