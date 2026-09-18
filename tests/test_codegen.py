"""Tests for aerodrift.remediation.codegen — Week 3 Day 1.

Built against the CONTRACT.md DRAFT (not yet confirmed by Person B).
Re-verify these tests once B's real contract lands.
"""

import ast

import pytest

from aerodrift.remediation.codegen import (
    generate_remediation_code,
    MissingDriftFieldError,
    UnsupportedDriftTypeError,
)


def _drift(**overrides):
    base = {
        "drift_id": "drift-001",
        "type": "public_db_exposure",
        "affected_node": "db-prod-01",
        "offending_edge": {"source": "0.0.0.0/0", "target": "db-prod-01", "rule": "0.0.0.0/0:5432/tcp"},
        "severity": "critical",
        "detected_at": "2026-09-10T09:00:00Z",
    }
    base.update(overrides)
    return base


def test_generates_correct_function_call_for_public_db_exposure():
    code = generate_remediation_code(_drift())
    assert code == "revoke_security_group_ingress(sg_id='db-prod-01', rule='0.0.0.0/0:5432/tcp')"


def test_generates_correct_function_call_for_open_ingress():
    drift = _drift(
        type="open_ingress",
        affected_node="sg-0a1b2c3",
        offending_edge={"source": "0.0.0.0/0", "target": "sg-0a1b2c3", "rule": "0.0.0.0/0:22/tcp"},
    )
    code = generate_remediation_code(drift)
    assert code == "revoke_security_group_ingress(sg_id='sg-0a1b2c3', rule='0.0.0.0/0:22/tcp')"


def test_generated_code_is_valid_python():
    code = generate_remediation_code(_drift())
    # Should parse without raising — proves it's syntactically valid.
    tree = ast.parse(code)
    assert isinstance(tree.body[0], ast.Expr)
    assert isinstance(tree.body[0].value, ast.Call)
    assert tree.body[0].value.func.id == "revoke_security_group_ingress"


def test_generated_code_is_executable_against_mock_function():
    calls = []

    def revoke_security_group_ingress(sg_id, rule):
        calls.append((sg_id, rule))
        return {"status": "success", "message": "ok"}

    code = generate_remediation_code(_drift())
    exec(code, {"revoke_security_group_ingress": revoke_security_group_ingress})
    assert calls == [("db-prod-01", "0.0.0.0/0:5432/tcp")]


def test_unsupported_drift_type_raises():
    with pytest.raises(UnsupportedDriftTypeError):
        generate_remediation_code(_drift(type="indirect_exposure"))


def test_missing_type_raises():
    drift = _drift()
    del drift["type"]
    with pytest.raises(MissingDriftFieldError):
        generate_remediation_code(drift)


def test_missing_affected_node_raises():
    drift = _drift()
    del drift["affected_node"]
    with pytest.raises(MissingDriftFieldError):
        generate_remediation_code(drift)


def test_missing_offending_edge_raises():
    drift = _drift()
    del drift["offending_edge"]
    with pytest.raises(MissingDriftFieldError):
        generate_remediation_code(drift)


def test_missing_rule_in_offending_edge_raises():
    drift = _drift(offending_edge={"source": "0.0.0.0/0", "target": "db-prod-01"})
    with pytest.raises(MissingDriftFieldError):
        generate_remediation_code(drift)


def test_null_offending_edge_raises():
    drift = _drift(offending_edge=None)
    with pytest.raises(MissingDriftFieldError):
        generate_remediation_code(drift)


def test_handles_special_characters_in_rule_safely():
    # Values go through ast.Constant, not string formatting, so quotes/
    # injection attempts in the rule string can't break out of the call.
    drift = _drift(offending_edge={"source": "x", "target": "db-prod-01", "rule": "0.0.0.0/0:22/tcp'); import os; os.system('rm -rf /'"})
    code = generate_remediation_code(drift)
    tree = ast.parse(code)
    # Still parses as a single, safe call expression — not multiple statements.
    assert len(tree.body) == 1
    assert isinstance(tree.body[0].value, ast.Call)
