from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from app.db.models import AgentStep, SecurityFinding, ValidationResult

PASS_STATUSES = {"passed", "success", "succeeded"}
FAIL_STATUSES = {"failed", "failure", "error"}
PENDING_STATUSES = {"pending", "queued", "running", "in_progress"}
INCOMPLETE_STATUSES = {"blocked", "cancelled", "skipped", "unknown", "not_run", "not-run"}
SECURITY_STEP_NAMES = {"RUN_SECURITY_CHECKS", "CODEQL_INGEST"}


def validation_evidence_summary(
    validations: Iterable[ValidationResult],
    *,
    patch_hash: str | None,
) -> dict[str, object]:
    if not patch_hash:
        return _validation_payload(status="unknown", patch_hash=None, statuses=[])

    applicable = [item for item in validations if item.patch_hash == patch_hash]
    statuses = [_normalized(item.status) for item in applicable]
    if not statuses:
        status = "not_run"
    elif any(item in FAIL_STATUSES for item in statuses):
        status = "failed"
    elif any(item in PENDING_STATUSES for item in statuses):
        status = "pending"
    elif all(item in PASS_STATUSES for item in statuses):
        status = "passed"
    else:
        status = "incomplete"
    return _validation_payload(status=status, patch_hash=patch_hash, statuses=statuses)


def security_scan_evidence_summary(
    steps: Iterable[AgentStep],
    *,
    patch_hash: str | None,
    findings: Iterable[SecurityFinding],
) -> dict[str, object]:
    finding_list = list(findings)
    if not patch_hash:
        return _security_payload(
            status="unknown",
            completed=False,
            patch_hash=None,
            findings=finding_list,
            applicable_steps=[],
        )

    security_steps = [step for step in steps if step.step_name in SECURITY_STEP_NAMES]
    applicable_steps = [step for step in security_steps if _step_patch_hash(step) == patch_hash]
    core_steps = [step for step in applicable_steps if step.step_name == "RUN_SECURITY_CHECKS"]

    if not core_steps:
        attempted_unbound_scan = any(
            step.step_name == "RUN_SECURITY_CHECKS"
            and isinstance(step.output_json, dict)
            and bool(step.output_json.get("not_evaluated"))
            for step in security_steps
        )
        return _security_payload(
            status="incomplete" if attempted_unbound_scan else "not_run",
            completed=False,
            patch_hash=patch_hash,
            findings=finding_list,
            applicable_steps=applicable_steps,
        )

    statuses = [_security_step_status(step) for step in applicable_steps]
    if any(item in FAIL_STATUSES for item in statuses):
        status = "failed"
    elif any(item in PENDING_STATUSES for item in statuses):
        status = "pending"
    elif statuses and all(item in PASS_STATUSES for item in statuses):
        status = "passed"
    else:
        status = "incomplete"
    return _security_payload(
        status=status,
        completed=status in {"passed", "failed"},
        patch_hash=patch_hash,
        findings=finding_list,
        applicable_steps=applicable_steps,
    )


def _validation_payload(*, status: str, patch_hash: str | None, statuses: list[str]) -> dict[str, object]:
    return {
        "status": status,
        "patch_hash": patch_hash,
        "total": len(statuses),
        "passed": sum(item in PASS_STATUSES for item in statuses),
        "failed": sum(item in FAIL_STATUSES for item in statuses),
        "pending": sum(item in PENDING_STATUSES for item in statuses),
        "incomplete": sum(item in INCOMPLETE_STATUSES or item not in PASS_STATUSES | FAIL_STATUSES | PENDING_STATUSES for item in statuses),
    }


def _security_payload(
    *,
    status: str,
    completed: bool,
    patch_hash: str | None,
    findings: list[SecurityFinding],
    applicable_steps: list[AgentStep],
) -> dict[str, object]:
    latest = max(applicable_steps, key=lambda step: _datetime_sort_key(step.created_at), default=None)
    scanned_files = [
        value
        for step in applicable_steps
        if isinstance(step.output_json, dict)
        for value in [step.output_json.get("scanned_files")]
        if isinstance(value, int) and value >= 0
    ]
    return {
        "status": status,
        "completed": completed,
        "patch_hash": patch_hash,
        "finding_count": len(findings),
        "scanned_files": max(scanned_files) if scanned_files else None,
        "completed_at": latest.created_at if latest and completed else None,
        "sources": sorted({step.step_name for step in applicable_steps}),
    }


def _security_step_status(step: AgentStep) -> str:
    output_status = step.output_json.get("status") if isinstance(step.output_json, dict) else None
    if isinstance(step.output_json, dict) and step.output_json.get("not_evaluated"):
        return "incomplete"
    return _normalized(str(output_status or step.status))


def _step_patch_hash(step: AgentStep) -> str | None:
    if not isinstance(step.output_json, dict):
        return None
    value = step.output_json.get("patch_hash")
    return str(value) if value else None


def _normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _datetime_sort_key(value: datetime | None) -> datetime:
    return value or datetime.min
