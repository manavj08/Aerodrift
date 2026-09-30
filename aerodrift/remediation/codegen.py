"""AST-based remediation code generator.

For each drift, AeroDrift *writes a Python function* — built node by node
with the ``ast`` module, never by string templating — that performs the
exact boto3 call needed to roll the drift back, e.g.::

    def remediate_drift_3f9a0c21bd(ec2):
        '''AeroDrift auto-remediation for drift-3f9a0c21bd (public_db_exposure).

        Revokes 0.0.0.0/0:5432/tcp from db-sg (sg-0abc...).'''
        return ec2.revoke_security_group_ingress(
            GroupId='sg-0abc...',
            IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 5432, 'ToPort': 5432,
                            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}])

Every value enters the tree as an ``ast.Constant`` inside ``ast.Dict`` /
``ast.List`` nodes, so a hostile string in a drift object can never become
code. The output is designed to pass ``sandbox.validate_remediation_code``.
"""

from __future__ import annotations

import ast
import re
import sys

from aerodrift.config import DRIFT_INDIRECT, DRIFT_OPEN_INGRESS, DRIFT_PUBLIC_DB
from aerodrift.ingestion.rules import IngressRule, RuleParseError


class UnsupportedDriftTypeError(ValueError):
    """Raised when a drift object's type has no known remediation mapping."""


class MissingDriftFieldError(ValueError):
    """Raised when a drift object is missing a field codegen needs."""


CLIENT_ARG = "ec2"
FUNCTION_PREFIX = "remediate_"

# drift type -> boto3 EC2 action that remediates it
REMEDIATION_ACTIONS = {
    DRIFT_PUBLIC_DB: "revoke_security_group_ingress",
    DRIFT_OPEN_INGRESS: "revoke_security_group_ingress",
    DRIFT_INDIRECT: "revoke_security_group_ingress",
}


def _require(drift: dict, field: str):
    value = drift.get(field)
    if not value:
        raise MissingDriftFieldError(f"drift object missing required field: {field}")
    return value


def literal_to_ast(value) -> ast.expr:
    """Convert a plain Python literal (dict/list/str/int/bool/None) into AST nodes."""
    if isinstance(value, dict):
        return ast.Dict(keys=[ast.Constant(str(k)) for k in value],
                        values=[literal_to_ast(v) for v in value.values()])
    if isinstance(value, (list, tuple)):
        return ast.List(elts=[literal_to_ast(v) for v in value], ctx=ast.Load())
    if value is None or isinstance(value, (str, int, float, bool)):
        return ast.Constant(value)
    raise TypeError(f"cannot embed {type(value).__name__} in generated code")


def function_name_for(drift: dict) -> str:
    raw = drift.get("drift_id") or f"{drift.get('affected_node', 'x')}_{drift.get('type', 'x')}"
    slug = re.sub(r"[^0-9a-zA-Z_]", "_", str(raw))
    slug = re.sub(r"_+", "_", slug).strip("_").lower() or "drift"
    return f"{FUNCTION_PREFIX}{slug}"[:80]


def remediation_plan(drift: dict) -> dict:
    """Resolve a drift into (action, boto3 kwargs) without generating code."""
    drift_type = _require(drift, "type")
    if drift_type not in REMEDIATION_ACTIONS:
        raise UnsupportedDriftTypeError(
            f"no remediation mapping for drift type '{drift_type}' "
            f"(supported: {', '.join(sorted(REMEDIATION_ACTIONS))})")
    group_id = _require(drift, "affected_node")
    edge = drift.get("offending_edge") or {}
    rule_text = edge.get("rule")
    if not rule_text:
        raise MissingDriftFieldError("drift object missing required field: offending_edge.rule")
    detail = drift.get("rule_detail") or {}
    try:
        rule = IngressRule.from_dict(detail) if {"source", "protocol"} <= detail.keys() \
            else IngressRule.parse(rule_text)
    except (RuleParseError, KeyError) as exc:
        raise MissingDriftFieldError(f"offending_edge.rule is not a valid rule: {rule_text!r} ({exc})") from exc
    return {
        "action": REMEDIATION_ACTIONS[drift_type],
        "kwargs": {"GroupId": group_id, "IpPermissions": [rule.to_ip_permission()]},
        "rule": str(rule),
    }


def build_remediation_ast(drift: dict) -> ast.Module:
    plan = remediation_plan(drift)
    name = function_name_for(drift)
    doc = (f"AeroDrift auto-remediation for {drift.get('drift_id', 'unknown drift')} "
           f"({drift['type']}): revokes {plan['rule']} from {drift.get('affected_name', drift['affected_node'])} "
           f"({drift['affected_node']}).")
    call = ast.Call(
        func=ast.Attribute(value=ast.Name(id=CLIENT_ARG, ctx=ast.Load()), attr=plan["action"], ctx=ast.Load()),
        args=[],
        keywords=[ast.keyword(arg=k, value=literal_to_ast(v)) for k, v in plan["kwargs"].items()],
    )
    fn_kwargs = dict(
        name=name,
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=CLIENT_ARG)], vararg=None,
                           kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
        body=[ast.Expr(ast.Constant(doc)), ast.Return(value=call)],
        decorator_list=[],
        returns=None,
    )
    if sys.version_info >= (3, 12):
        fn_kwargs["type_params"] = []
    module = ast.Module(body=[ast.FunctionDef(**fn_kwargs)], type_ignores=[])
    return ast.fix_missing_locations(module)


def generate_remediation_code(drift: dict) -> str:
    """Return the source of a remediation function for ``drift``.

    Raises:
        MissingDriftFieldError: required fields absent or rule unparseable.
        UnsupportedDriftTypeError: no remediation mapping for the drift type.
    """
    return ast.unparse(build_remediation_ast(drift))
