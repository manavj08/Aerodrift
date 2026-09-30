import ast

import pytest

from aerodrift.graph.topology import detect_drift
from aerodrift.remediation.codegen import (
    MissingDriftFieldError,
    UnsupportedDriftTypeError,
    build_remediation_ast,
    generate_remediation_code,
    remediation_plan,
)
from aerodrift.remediation.sandbox import validate_remediation_code


def drift(**over):
    d = {"drift_id": "drift-abc123", "type": "public_db_exposure", "affected_node": "sg-db",
         "affected_name": "db-sg", "offending_edge": {"source": "0.0.0.0/0", "target": "sg-db",
                                                       "rule": "0.0.0.0/0:5432/tcp"}}
    d.update(over)
    return d


def _call(code):
    fn = ast.parse(code).body[0]
    return fn, fn.body[-1].value


def test_generates_a_single_function_with_a_boto3_call():
    code = generate_remediation_code(drift())
    fn, call = _call(code)
    assert isinstance(fn, ast.FunctionDef) and fn.name == "remediate_drift_abc123"
    assert [a.arg for a in fn.args.args] == ["ec2"]
    assert call.func.attr == "revoke_security_group_ingress"
    assert {k.arg: ast.literal_eval(k.value) for k in call.keywords} == {
        "GroupId": "sg-db",
        "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
                           "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]}


def test_ast_is_built_not_templated():
    module = build_remediation_ast(drift())
    assert isinstance(module, ast.Module)
    assert ast.unparse(module) == generate_remediation_code(drift())


@pytest.mark.parametrize("dtype", ["public_db_exposure", "open_ingress", "indirect_exposure"])
def test_every_drift_type_maps_to_revocation(dtype):
    assert remediation_plan(drift(type=dtype))["action"] == "revoke_security_group_ingress"


@pytest.mark.parametrize("rule,perm", [
    ("0.0.0.0/0:all/all", {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}),
    ("::/0:22/tcp", {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "Ipv6Ranges": [{"CidrIpv6": "::/0"}]}),
    ("0.0.0.0/0:1000-2000/udp", {"IpProtocol": "udp", "FromPort": 1000, "ToPort": 2000,
                                 "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}),
])
def test_rule_variants(rule, perm):
    plan = remediation_plan(drift(offending_edge={"rule": rule}))
    assert plan["kwargs"]["IpPermissions"] == [perm]


def test_rule_detail_is_preferred_over_rule_string():
    d = drift(rule_detail={"source": "0.0.0.0/0", "protocol": "tcp", "from_port": 22, "to_port": 22,
                           "source_kind": "cidr"})
    assert remediation_plan(d)["kwargs"]["IpPermissions"][0]["FromPort"] == 22


def test_generated_code_passes_sandbox_validation_for_detected_drift(mock_graph):
    for d in detect_drift(mock_graph):
        validate_remediation_code(generate_remediation_code(d))


def test_injection_attempts_stay_inert_constants():
    evil = "sg-1'); __import__('os').system('rm -rf /'); ('"
    code = generate_remediation_code(drift(affected_node=evil, drift_id="x'); import os; ('"))
    fn, call = _call(code)
    assert len(ast.parse(code).body) == 1
    assert ast.literal_eval(call.keywords[0].value) == evil
    assert fn.name.isidentifier()
    validate_remediation_code(code)  # still only a literal-only call


def test_unsupported_drift_type():
    with pytest.raises(UnsupportedDriftTypeError):
        generate_remediation_code(drift(type="public_s3_bucket"))


@pytest.mark.parametrize("over", [{"type": None}, {"affected_node": None}, {"offending_edge": None},
                                  {"offending_edge": {"source": "x"}}, {"offending_edge": {"rule": "garbage"}}])
def test_missing_or_bad_fields(over):
    with pytest.raises(MissingDriftFieldError):
        generate_remediation_code(drift(**over))
