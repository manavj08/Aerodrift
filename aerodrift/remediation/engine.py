"""Remediation engine: drift -> generated code -> sandboxed execution -> record."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from aerodrift.remediation.codegen import (
    MissingDriftFieldError,
    UnsupportedDriftTypeError,
    generate_remediation_code,
)
from aerodrift.remediation.sandbox import (
    SandboxExecutionError,
    SandboxViolation,
    run_remediation,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RemediationRecord:
    drift: dict
    code: str | None
    result: dict
    generated_at: str = field(default_factory=_now)
    executed_at: str | None = None
    verified: bool | None = None          # None = not checked yet
    detection_latency_s: float | None = None  # drift injected -> detected (when known)
    time_to_heal_s: float | None = None       # detected -> verified healed

    @property
    def status(self) -> str:
        return self.result.get("status", "unknown")

    @property
    def succeeded(self) -> bool:
        return self.status in ("success", "noop")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RemediationRecord":
        data = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**data)


def remediate(drift: dict, client, *, dry_run: bool = False) -> RemediationRecord:
    """Generate code for one drift and run it in the sandbox. Never raises
    for expected failure modes — they are captured in the record."""
    try:
        code = generate_remediation_code(drift)
    except (UnsupportedDriftTypeError, MissingDriftFieldError) as exc:
        return RemediationRecord(drift, None, {"status": "unsupported", "message": str(exc)})

    start = time.perf_counter()
    try:
        result = run_remediation(code, client, dry_run=dry_run)
    except SandboxViolation as exc:
        result = {"status": "blocked", "message": f"sandbox rejected generated code: {exc}"}
    except SandboxExecutionError as exc:
        result = {"status": "failed", "message": str(exc)}
    result.setdefault("duration_ms", round((time.perf_counter() - start) * 1000, 2))
    return RemediationRecord(drift, code, result, executed_at=None if dry_run else _now())


def remediate_all(drifts: list[dict], client, *, dry_run: bool = False) -> list[RemediationRecord]:
    return [remediate(d, client, dry_run=dry_run) for d in drifts]
