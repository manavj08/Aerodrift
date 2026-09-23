"""Tests for aerodrift.remediation.mock_methods placeholder — Week 3 Day 2.

NOTE: this module is Person A's responsibility (per CONTRACT.md section
2 — mock remediation method signatures). Person A has only delivered
ingestion so far, not remediation methods. These tests cover Person C's
placeholder used to build/test the sandbox before A's real module lands.
Delete this file once A's tests replace it.
"""

import pytest

from aerodrift.remediation.mock_methods import (
    revoke_security_group_ingress,
    get_revoked_log,
    clear_revoked_log,
)


@pytest.fixture(autouse=True)
def _reset_log():
    clear_revoked_log()
    yield
    clear_revoked_log()


def test_revoke_security_group_ingress_returns_success():
    result = revoke_security_group_ingress("sg-1", "0.0.0.0/0:22/tcp")
    assert result["status"] == "success"
    assert "sg-1" in result["message"]


def test_revoke_security_group_ingress_logs_the_call():
    revoke_security_group_ingress("sg-1", "0.0.0.0/0:22/tcp")
    assert get_revoked_log() == [{"sg_id": "sg-1", "rule": "0.0.0.0/0:22/tcp"}]


def test_revoke_security_group_ingress_fails_on_missing_args():
    result = revoke_security_group_ingress("", "0.0.0.0/0:22/tcp")
    assert result["status"] == "failed"
    assert get_revoked_log() == []


def test_clear_revoked_log_resets_state():
    revoke_security_group_ingress("sg-1", "rule-1")
    clear_revoked_log()
    assert get_revoked_log() == []
