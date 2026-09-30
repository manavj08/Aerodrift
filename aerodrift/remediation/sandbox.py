"""Execution sandbox for generated remediation code.

Three independent layers, each sufficient to stop the common failure
modes on its own:

1. **Static AST allowlist** (``validate_remediation_code``). The source
   must be exactly one ``def remediate_*(ec2):`` whose body is an optional
   docstring plus ``return ec2.<allowed_action>(Key=<literal>, ...)``.
   Only literals may appear as arguments; no other names, attributes,
   imports, loops, lambdas, comprehensions or dunder access can exist.
2. **Empty builtins.** The code is ``exec``'d with ``__builtins__ = {}``
   in a fresh namespace, so even a validator bug gives it no ``open``,
   ``__import__``, ``eval``, etc.
3. **Least-privilege client proxy.** The function receives a
   ``ScopedClient`` that exposes only the allowlisted boto3 actions, not
   the real client, so it cannot call ``delete_vpc`` & co even if (1)
   and (2) were both bypassed.

CPython has no perfect in-process sandbox; this design is appropriate
because the code comes from ``codegen.py``'s fixed AST builders rather
than free text, and the layers above make an accidental codegen bug fail
closed.
"""

from __future__ import annotations

import ast
import time

# boto3 EC2 actions generated code may invoke.
ALLOWED_ACTIONS = frozenset({"revoke_security_group_ingress"})
FUNCTION_PREFIX = "remediate_"
CLIENT_ARG = "ec2"


class SandboxViolation(ValueError):
    """Generated code failed static validation and was NOT executed."""


class SandboxExecutionError(RuntimeError):
    """Generated code passed validation but failed to load/run."""


def _is_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return node.value is None or isinstance(node.value, (str, int, float, bool))
    if isinstance(node, (ast.List, ast.Tuple)):
        return all(_is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and isinstance(k, ast.Constant) and isinstance(k.value, str)
                   for k in node.keys) and all(_is_literal(v) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float))
    return False


def validate_remediation_code(code: str, allowed_actions=ALLOWED_ACTIONS) -> tuple[str, str]:
    """Statically validate generated code. Returns (function_name, action)."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxViolation(f"generated code is not valid Python: {exc}") from exc

    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise SandboxViolation("code must be exactly one function definition")
    fn = tree.body[0]
    if not fn.name.startswith(FUNCTION_PREFIX) or not fn.name.isidentifier() or "__" in fn.name:
        raise SandboxViolation(f"function name {fn.name!r} must start with {FUNCTION_PREFIX!r}")
    if fn.decorator_list or fn.returns is not None or getattr(fn, "type_params", None):
        raise SandboxViolation("decorators, annotations and type params are not allowed")
    a = fn.args
    if (a.posonlyargs or a.vararg or a.kwonlyargs or a.kwarg or a.defaults or a.kw_defaults
            or [x.arg for x in a.args] != [CLIENT_ARG] or a.args[0].annotation is not None):
        raise SandboxViolation(f"function must take exactly one parameter named {CLIENT_ARG!r}")

    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        raise SandboxViolation("function body must be a single `return ec2.<action>(...)`")
    call = body[0].value
    func = call.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id == CLIENT_ARG):
        raise SandboxViolation(f"only methods on {CLIENT_ARG!r} may be called")
    if func.attr not in allowed_actions:
        raise SandboxViolation(f"action {func.attr!r} is not in the allowed set {sorted(allowed_actions)}")
    if call.args:
        raise SandboxViolation("positional arguments are not allowed; use keywords")
    for kw in call.keywords:
        if kw.arg is None:
            raise SandboxViolation("**kwargs expansion is not allowed")
        if not _is_literal(kw.value):
            raise SandboxViolation(f"argument {kw.arg!r} must be a literal value")
    return fn.name, func.attr


class ScopedClient:
    """Proxy exposing only allowlisted actions of a boto3 client."""

    __slots__ = ("_client", "_allowed", "calls")

    def __init__(self, client, allowed_actions=ALLOWED_ACTIONS):
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_allowed", frozenset(allowed_actions))
        object.__setattr__(self, "calls", [])

    def __getattr__(self, name):
        if name not in self._allowed:
            raise PermissionError(f"action {name!r} is not permitted in the remediation sandbox")
        target = getattr(self._client, name)

        def invoke(**kwargs):
            self.calls.append({"action": name, "kwargs": kwargs})
            return target(**kwargs)
        return invoke

    def __setattr__(self, name, value):
        raise PermissionError("ScopedClient is read-only")


def _error_code(exc) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return (response.get("Error") or {}).get("Code")
    return None


def run_remediation(code: str, client, *, dry_run: bool = False,
                    allowed_actions=ALLOWED_ACTIONS) -> dict:
    """Validate and (unless ``dry_run``) execute generated remediation code.

    Returns a result dict:
        status: "success" | "noop" | "failed" | "validated"
        message: human-readable outcome
        action, function, duration_ms, calls, (response | error_code)

    Raises:
        SandboxViolation: static validation failed; nothing was executed.
        SandboxExecutionError: the code could not even be loaded.
    """
    fn_name, action = validate_remediation_code(code, allowed_actions)
    if dry_run:
        return {"status": "validated", "message": "passed sandbox validation (dry run, not executed)",
                "action": action, "function": fn_name, "duration_ms": 0.0, "calls": []}

    namespace: dict = {"__builtins__": {}}
    try:
        exec(compile(code, "<aerodrift-generated>", "exec"), namespace)  # noqa: S102 - validated above
        fn = namespace[fn_name]
    except Exception as exc:
        raise SandboxExecutionError(f"could not load generated code: {exc}") from exc

    scoped = ScopedClient(client, allowed_actions)
    start = time.perf_counter()
    try:
        response = fn(scoped)
    except PermissionError as exc:
        raise SandboxViolation(str(exc)) from exc
    except Exception as exc:
        code_ = _error_code(exc)
        duration = round((time.perf_counter() - start) * 1000, 2)
        if code_ == "InvalidPermission.NotFound":
            return {"status": "noop", "message": "rule already absent — nothing to revoke",
                    "action": action, "function": fn_name, "error_code": code_,
                    "duration_ms": duration, "calls": scoped.calls}
        return {"status": "failed", "message": f"{type(exc).__name__}: {exc}", "action": action,
                "function": fn_name, "error_code": code_, "duration_ms": duration, "calls": scoped.calls}
    duration = round((time.perf_counter() - start) * 1000, 2)
    if isinstance(response, dict):
        response = {k: v for k, v in response.items() if k != "ResponseMetadata"}
    ok = not (isinstance(response, dict) and response.get("Return") is False)
    return {
        "status": "success" if ok else "failed",
        "message": f"{action} executed ({duration} ms)",
        "action": action, "function": fn_name, "response": response,
        "duration_ms": duration, "calls": scoped.calls,
    }
