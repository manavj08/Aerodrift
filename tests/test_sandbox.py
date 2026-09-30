import pytest

from aerodrift.remediation.codegen import generate_remediation_code
from aerodrift.remediation.sandbox import (
    ScopedClient,
    SandboxViolation,
    run_remediation,
    validate_remediation_code,
)

GOOD = ("def remediate_x(ec2):\n    'doc'\n    return ec2.revoke_security_group_ingress("
        "GroupId='sg-1', IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, "
        "'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}])")


class FakeEC2:
    def __init__(self, exc=None):
        self.calls, self.exc = [], exc

    def revoke_security_group_ingress(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return {"Return": True, "ResponseMetadata": {"x": 1}}

    def delete_vpc(self, **kw):
        raise AssertionError("must never be reachable")


def test_valid_code_passes():
    assert validate_remediation_code(GOOD) == ("remediate_x", "revoke_security_group_ingress")


@pytest.mark.parametrize("code,msg", [
    ("x = 1", "exactly one function"),
    (GOOD + "\nprint(1)", "exactly one function"),
    ("import os", "exactly one function"),
    ("def evil(ec2):\n    return ec2.revoke_security_group_ingress()", "must start with"),
    ("def remediate__init__(ec2):\n    return ec2.revoke_security_group_ingress()", "must start with"),
    ("@d\ndef remediate_x(ec2):\n    return ec2.revoke_security_group_ingress()", "decorators"),
    ("def remediate_x(ec2, os):\n    return ec2.revoke_security_group_ingress()", "exactly one parameter"),
    ("def remediate_x(ec2=1):\n    return ec2.revoke_security_group_ingress()", "exactly one parameter"),
    ("def remediate_x(*a):\n    return 1", "exactly one parameter"),
    ("def remediate_x(ec2):\n    import os\n    return ec2.revoke_security_group_ingress()", "single `return"),
    ("def remediate_x(ec2):\n    for i in []: pass\n    return 1", "single `return"),
    ("def remediate_x(ec2):\n    return ec2.delete_vpc(VpcId='v')", "not in the allowed set"),
    ("def remediate_x(ec2):\n    return open('/etc/passwd')", "only methods on"),
    ("def remediate_x(ec2):\n    return ec2.meta.client.delete_vpc()", "only methods on"),
    ("def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress('sg')", "positional"),
    ("def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress(**{'a': 1})", "kwargs"),
    ("def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress(GroupId=__import__('os'))", "literal"),
    ("def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress(GroupId=ec2.__class__)", "literal"),
    ("def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress(GroupId=[x for x in ()])", "literal"),
    ("def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress(GroupId=lambda: 1)", "literal"),
    ("def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress(GroupId={**{}})", "literal"),
    ("def (:", "not valid Python"),
])
def test_validator_rejects(code, msg):
    with pytest.raises(SandboxViolation, match=msg):
        validate_remediation_code(code)


def test_rejected_code_is_never_executed():
    ec2 = FakeEC2()
    with pytest.raises(SandboxViolation):
        run_remediation("def remediate_x(ec2):\n    return ec2.delete_vpc(VpcId='v')", ec2)
    assert ec2.calls == []


def test_executes_and_strips_response_metadata():
    ec2 = FakeEC2()
    result = run_remediation(GOOD, ec2)
    assert result["status"] == "success"
    assert result["response"] == {"Return": True}
    assert ec2.calls == [{"GroupId": "sg-1", "IpPermissions": [
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]}]
    assert result["calls"][0]["action"] == "revoke_security_group_ingress"


def test_dry_run_validates_without_calling():
    ec2 = FakeEC2()
    assert run_remediation(GOOD, ec2, dry_run=True)["status"] == "validated"
    assert ec2.calls == []


def test_missing_rule_is_a_noop_not_a_failure():
    class NotFound(Exception):
        response = {"Error": {"Code": "InvalidPermission.NotFound"}}
    assert run_remediation(GOOD, FakeEC2(NotFound("gone")))["status"] == "noop"


def test_api_error_is_reported_as_failed():
    class Denied(Exception):
        response = {"Error": {"Code": "UnauthorizedOperation"}}
    r = run_remediation(GOOD, FakeEC2(Denied("denied")))
    assert r["status"] == "failed" and r["error_code"] == "UnauthorizedOperation"


def test_scoped_client_blocks_everything_else():
    scoped = ScopedClient(FakeEC2())
    with pytest.raises(PermissionError):
        scoped.delete_vpc
    with pytest.raises(PermissionError):
        scoped._client = None
    assert scoped.revoke_security_group_ingress(GroupId="sg") == {"Return": True, "ResponseMetadata": {"x": 1}}


def test_generated_code_runs_with_no_builtins():
    # Even `len` is unavailable inside the sandbox namespace.
    ec2 = FakeEC2()
    run_remediation(GOOD, ec2)
    code = "def remediate_x(ec2):\n    return ec2.revoke_security_group_ingress(GroupId=len)"
    with pytest.raises(SandboxViolation):
        run_remediation(code, ec2)


def test_real_revocation_against_simulated_aws(cloud):
    inj = cloud.inject_drift("open-db")
    drift = {"drift_id": "drift-t", "type": "public_db_exposure", "affected_node": inj.group_id,
             "offending_edge": {"rule": inj.rule}}
    assert inj.rule in cloud.ingress_rules(inj.group_id)
    result = run_remediation(generate_remediation_code(drift), cloud.ec2)
    assert result["status"] == "success"
    remaining = cloud.ingress_rules(inj.group_id)
    assert inj.rule not in remaining
    assert remaining == [f"{cloud.ids['sg_app']}:5432/tcp"]  # the legitimate rule survives
    # second run: already gone -> noop
    assert run_remediation(generate_remediation_code(drift), cloud.ec2)["status"] == "noop"
