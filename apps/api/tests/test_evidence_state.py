import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from app.db.models import AgentStep, SecurityFinding, ValidationResult
from app.services.evidence_state import security_scan_evidence_summary, validation_evidence_summary
from app.services.ci_analyzer import CIAnalyzer


class ScalarResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items

    def first(self):
        return self.items[0] if self.items else None


class SequenceDb:
    def __init__(self, results: list[list[object]]) -> None:
        self.results = list(results)

    async def execute(self, _statement):
        return ScalarResult(self.results.pop(0))


def validation(status: str, patch_hash: str | None = "patch-1") -> ValidationResult:
    return ValidationResult(run_id=uuid4(), command="pytest", status=status, patch_hash=patch_hash)


def security_step(
    status: str,
    *,
    patch_hash: str | None = "patch-1",
    name: str = "RUN_SECURITY_CHECKS",
    not_evaluated: bool = False,
) -> AgentStep:
    output = {"status": status, "scanned_files": 2}
    if patch_hash:
        output["patch_hash"] = patch_hash
    if not_evaluated:
        output["not_evaluated"] = True
    return AgentStep(
        run_id=uuid4(),
        step_name=name,
        status="succeeded" if status == "passed" else status,
        output_json=output,
        created_at=datetime(2026, 7, 13, tzinfo=UTC),
    )


def test_validation_summary_preserves_empty_pending_partial_failed_and_passed_states() -> None:
    assert validation_evidence_summary([], patch_hash=None)["status"] == "unknown"
    assert validation_evidence_summary([], patch_hash="patch-1")["status"] == "not_run"

    pending = validation_evidence_summary(
        [validation("passed"), validation("pending")],
        patch_hash="patch-1",
    )
    assert pending == {
        "status": "pending",
        "patch_hash": "patch-1",
        "total": 2,
        "passed": 1,
        "failed": 0,
        "pending": 1,
        "incomplete": 0,
    }

    assert validation_evidence_summary(
        [validation("passed"), validation("skipped")], patch_hash="patch-1"
    )["status"] == "incomplete"
    assert validation_evidence_summary(
        [validation("passed"), validation("failure")], patch_hash="patch-1"
    )["status"] == "failed"
    assert validation_evidence_summary(
        [validation("passed"), validation("succeeded")], patch_hash="patch-1"
    )["status"] == "passed"
    assert validation_evidence_summary(
        [validation("passed", "old-patch")], patch_hash="patch-1"
    )["status"] == "not_run"


def test_security_summary_requires_current_completed_core_scan() -> None:
    assert security_scan_evidence_summary([], patch_hash=None, findings=[])["status"] == "unknown"
    assert security_scan_evidence_summary([], patch_hash="patch-1", findings=[])["status"] == "not_run"
    assert security_scan_evidence_summary(
        [security_step("blocked", patch_hash=None, not_evaluated=True)],
        patch_hash="patch-1",
        findings=[],
    )["status"] == "incomplete"
    assert security_scan_evidence_summary(
        [security_step("passed", patch_hash="old-patch")],
        patch_hash="patch-1",
        findings=[],
    )["status"] == "not_run"

    passed = security_scan_evidence_summary(
        [security_step("passed")],
        patch_hash="patch-1",
        findings=[],
    )
    assert passed["status"] == "passed"
    assert passed["completed"] is True
    assert passed["finding_count"] == 0
    assert passed["scanned_files"] == 2


def test_security_summary_does_not_hide_failed_or_incomplete_applicable_scans() -> None:
    finding = SecurityFinding(
        run_id=uuid4(),
        patch_hash="patch-1",
        tool="secret-scan",
        severity="high",
        description="secret",
        status="open",
    )
    assert security_scan_evidence_summary(
        [security_step("failed")], patch_hash="patch-1", findings=[finding]
    )["status"] == "failed"
    assert security_scan_evidence_summary(
        [security_step("passed"), security_step("skipped", name="CODEQL_INGEST")],
        patch_hash="patch-1",
        findings=[],
    )["status"] == "incomplete"
    assert security_scan_evidence_summary(
        [security_step("passed"), security_step("pending", name="CODEQL_INGEST")],
        patch_hash="patch-1",
        findings=[],
    )["status"] == "pending"


def test_ci_readiness_requires_every_current_validation_and_completed_security_scan() -> None:
    run_id = uuid4()
    patch_step = AgentStep(
        run_id=run_id,
        step_name="IMPLEMENT_PATCH",
        output_json={"patch_hash": "patch-1"},
        created_at=datetime(2026, 7, 13, tzinfo=UTC),
    )
    passed_scan = security_step("passed")
    passed_scan.run_id = run_id
    mixed_db = SequenceDb(
        [
            [patch_step],
            [validation("passed"), validation("pending")],
        ]
    )
    assert asyncio.run(CIAnalyzer()._can_mark_ready(mixed_db, run_id=run_id)) is False

    passed_validation = validation("passed")
    passed_validation.run_id = run_id
    complete_db = SequenceDb(
        [
            [patch_step],
            [passed_validation],
            [passed_scan],
            [],
            [],
        ]
    )
    assert asyncio.run(CIAnalyzer()._can_mark_ready(complete_db, run_id=run_id)) is True

    no_scan_db = SequenceDb(
        [
            [patch_step],
            [passed_validation],
            [],
            [],
        ]
    )
    assert asyncio.run(CIAnalyzer()._can_mark_ready(no_scan_db, run_id=run_id)) is False
