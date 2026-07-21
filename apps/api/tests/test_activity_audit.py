from datetime import UTC, datetime
from uuid import uuid4

from repopilot_contracts import ActivitySummaryResponse, AuditLogPage

from app.api.routes.activity import _activity_summary_response, _audit_log_item, _audit_log_page
from app.db.models import AuditLog


def audit_fixture(**overrides: object) -> AuditLog:
    values: dict[str, object] = {
        "id": uuid4(),
        "actor_type": "agent",
        "actor_id": "implementation-agent",
        "action": "implementation.completed",
        "entity_type": "agent_run",
        "entity_id": "run-123",
        "metadata_json": {},
        "created_at": datetime(2026, 7, 13, 8, 30, tzinfo=UTC),
    }
    values.update(overrides)
    return AuditLog(**values)


def test_audit_contract_preserves_actor_and_unknown_risk() -> None:
    audit = audit_fixture()

    item = _audit_log_item(audit)
    page = AuditLogPage.model_validate(
        _audit_log_page([audit], total=3, limit=1, offset=0)
    )

    assert item["actor_type"] == "agent"
    assert item["actor_id"] == "implementation-agent"
    assert item["result"] == "recorded"
    assert item["risk_score"] is None
    assert page.total == 3
    assert page.has_more is True
    assert page.is_complete is False
    assert page.items[0].risk_score is None
    assert page.items[0].created_at == datetime(2026, 7, 13, 8, 30, tzinfo=UTC)


def test_audit_contract_preserves_explicit_outcome_and_risk() -> None:
    audit = audit_fixture(
        actor_type="user",
        actor_id="reviewer@example.com",
        metadata_json={"result": "approved", "risk_score": 72, "detail": "reviewed"},
    )

    item = _audit_log_item(audit)

    assert item["actor_type"] == "user"
    assert item["actor_id"] == "reviewer@example.com"
    assert item["result"] == "approved"
    assert item["risk_score"] == 72
    assert item["metadata"] == {
        "result": "approved",
        "risk_score": 72,
        "detail": "reviewed",
    }


def test_audit_page_discloses_complete_first_page() -> None:
    page = AuditLogPage.model_validate(
        _audit_log_page([audit_fixture()], total=1, limit=200, offset=0)
    )

    assert page.has_more is False
    assert page.is_complete is True


def test_activity_summary_contract_is_independent_of_activity_page_size() -> None:
    summary = ActivitySummaryResponse.model_validate(
        _activity_summary_response(
            plans_approved=317,
            pull_request_records=204,
            agent_runs=811,
            reviewed_security_findings=97,
        )
    )

    assert summary.plans_approved == 317
    assert summary.pull_request_records == 204
    assert summary.agent_runs == 811
    assert summary.reviewed_security_findings == 97
