"""AST-based remediation code generator.

Given a drift object (shape per CONTRACT.md, from Person B), builds an
ast.Call node for the corresponding mock remediation function and
unparses it into runnable source. Built against the CONTRACT.md DRAFT —
Person B's real contract has not been confirmed yet, so drift type
names and the mock remediation signature below must be re-verified once
B delivers (see CONTRACT.md status).

Only revoke_security_group_ingress(sg_id, rule) is implemented, matching
Person A's currently-documented mock signature. Other drift types raise
UnsupportedDriftTypeError rather than guessing at a call that doesn't
exist yet.
"""

import ast


class UnsupportedDriftTypeError(ValueError):
    """Raised when a drift object's type has no known remediation mapping."""


class MissingDriftFieldError(ValueError):
    """Raised when a drift object is missing a field codegen needs."""


# Drift types the mock remediation function currently covers (per
# CONTRACT.md section 2 — only revoke_security_group_ingress exists so far).
_SG_INGRESS_DRIFT_TYPES = {"open_ingress", "public_db_exposure"}


def _require_field(drift: dict, field: str):
    value = drift.get(field)
    if not value:
        raise MissingDriftFieldError(f"drift object missing required field: {field}")
    return value


def _build_call_ast(func_name: str, sg_id: str, rule: str) -> ast.Call:
    """Build the AST for `func_name(sg_id="...", rule="...")`."""
    return ast.Call(
        func=ast.Name(id=func_name, ctx=ast.Load()),
        args=[],
        keywords=[
            ast.keyword(arg="sg_id", value=ast.Constant(value=sg_id)),
            ast.keyword(arg="rule", value=ast.Constant(value=rule)),
        ],
    )


def generate_remediation_code(drift: dict) -> str:
    """Given a drift object, return generated remediation source code.

    Args:
        drift: dict shaped per CONTRACT.md
            (type, affected_node, offending_edge.rule).

    Returns:
        A single Python statement as a string, e.g.:
        'revoke_security_group_ingress(sg_id=\'sg-0a1b2c3\', rule=\'0.0.0.0/0:22/tcp\')'

    Raises:
        MissingDriftFieldError: if `type`, `affected_node`, or
            `offending_edge.rule` is missing.
        UnsupportedDriftTypeError: if `drift["type"]` has no known
            remediation mapping yet.
    """
    drift_type = _require_field(drift, "type")

    if drift_type in _SG_INGRESS_DRIFT_TYPES:
        sg_id = _require_field(drift, "affected_node")
        offending_edge = drift.get("offending_edge") or {}
        rule = offending_edge.get("rule")
        if not rule:
            raise MissingDriftFieldError("drift object missing required field: offending_edge.rule")

        call_node = _build_call_ast("revoke_security_group_ingress", sg_id, rule)
        module = ast.Module(body=[ast.Expr(value=call_node)], type_ignores=[])
        ast.fix_missing_locations(module)
        return ast.unparse(module)

    raise UnsupportedDriftTypeError(
        f"no remediation mapping for drift type '{drift_type}' yet — "
        "add a mock method to CONTRACT.md and this file once available"
    )
