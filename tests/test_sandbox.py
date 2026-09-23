"""Tests for aerodrift.remediation.sandbox — Week 3 Day 2.

Covers both correctness (does the sandbox correctly run allowed code)
and security (does it correctly block disallowed code).
"""

import pytest

from aerodrift.remediation.sandbox import run_sandboxed, SandboxExecutionError
from aerodrift.remediation.mock_methods import (
    revoke_security_group_ingress,
    clear_revoked_log,
    get_revoked_log,
)


@pytest.fixture(autouse=True)
def _reset_mock_log():
    clear_revoked_log()
    yield
    clear_revoked_log()


ALLOWED = {"revoke_security_group_ingress": revoke_security_group_ingress}


# --- Correctness ---------------------------------------------------------

def test_runs_allowed_call_and_returns_mock_result():
    code = "revoke_security_group_ingress(sg_id='sg-1', rule='0.0.0.0/0:22/tcp')"
    result = run_sandboxed(code, ALLOWED)
    assert result["status"] == "success"
    assert "sg-1" in result["message"]


def test_runs_allowed_call_and_actually_invokes_the_mock_function():
    code = "revoke_security_group_ingress(sg_id='sg-2', rule='0.0.0.0/0:80/tcp')"
    run_sandboxed(code, ALLOWED)
    log = get_revoked_log()
    assert log == [{"sg_id": "sg-2", "rule": "0.0.0.0/0:80/tcp"}]


def test_integrates_with_codegen_output():
    """End-to-end: codegen -> sandbox, matching the real remediate flow."""
    from aerodrift.remediation.codegen import generate_remediation_code

    drift = {
        "type": "open_ingress",
        "affected_node": "sg-0a1b2c3",
        "offending_edge": {"source": "0.0.0.0/0", "target": "sg-0a1b2c3", "rule": "0.0.0.0/0:22/tcp"},
    }
    code = generate_remediation_code(drift)
    result = run_sandboxed(code, ALLOWED)
    assert result["status"] == "success"
    assert get_revoked_log() == [{"sg_id": "sg-0a1b2c3", "rule": "0.0.0.0/0:22/tcp"}]


def test_mock_function_failure_propagates_as_failed_status():
    code = "revoke_security_group_ingress(sg_id='', rule='0.0.0.0/0:22/tcp')"
    result = run_sandboxed(code, ALLOWED)
    assert result["status"] == "failed"


# --- Security: disallowed function calls ----------------------------------

def test_rejects_call_to_function_not_in_allowed_set():
    code = "some_other_function(sg_id='sg-1', rule='x')"
    with pytest.raises(SandboxExecutionError, match="not in the allowed set"):
        run_sandboxed(code, ALLOWED)


def test_rejects_multiple_statements():
    code = "revoke_security_group_ingress(sg_id='sg-1', rule='x')\nprint('extra')"
    with pytest.raises(SandboxExecutionError, match="single function-call statement"):
        run_sandboxed(code, ALLOWED)


def test_rejects_non_call_expression():
    code = "1 + 1"
    with pytest.raises(SandboxExecutionError):
        run_sandboxed(code, ALLOWED)


def test_rejects_invalid_syntax():
    code = "this is not : valid python(("
    with pytest.raises(SandboxExecutionError, match="not valid Python"):
        run_sandboxed(code, ALLOWED)


# --- Security: restricted builtins -----------------------------------------

def test_blocks_filesystem_access_via_open():
    # `open` isn't in ALLOWED and isn't a safe builtin, so it's not
    # reachable as a bare name call — but codegen only ever produces
    # single-call statements against ALLOWED, so this also proves the
    # allowed-function check catches it even before builtins matter.
    code = "open('/etc/passwd', 'r')"
    with pytest.raises(SandboxExecutionError, match="not in the allowed set"):
        run_sandboxed(code, ALLOWED)


def test_blocks_import_statement():
    code = "import os"
    with pytest.raises(SandboxExecutionError):
        run_sandboxed(code, ALLOWED)


def test_blocks_dunder_import_call():
    code = "__import__('os')"
    with pytest.raises(SandboxExecutionError, match="not in the allowed set"):
        run_sandboxed(code, ALLOWED)


def test_blocks_eval_call():
    code = "eval('1+1')"
    with pytest.raises(SandboxExecutionError, match="not in the allowed set"):
        run_sandboxed(code, ALLOWED)


def test_safe_builtins_do_not_expose_import():
    """Directly verify __builtins__ inside the sandbox has no import-capable names."""
    from aerodrift.remediation.sandbox import _SAFE_BUILTINS

    assert "__import__" not in _SAFE_BUILTINS
    assert "open" not in _SAFE_BUILTINS
    assert "eval" not in _SAFE_BUILTINS
    assert "exec" not in _SAFE_BUILTINS
    assert "compile" not in _SAFE_BUILTINS
    assert "getattr" not in _SAFE_BUILTINS
    assert "setattr" not in _SAFE_BUILTINS
    assert "__build_class__" not in _SAFE_BUILTINS
