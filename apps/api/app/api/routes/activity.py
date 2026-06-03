from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from repopilot_contracts import ActivityEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AgentRun,
    AgentStep,
    AuditLog,
    EvalRun,
    GitHubEvent,
    Issue,
    PullRequest,
    SecurityFinding,
    ValidationResult,
)
from app.db.session import get_db

router = APIRouter()


@router.get("", response_model=list[ActivityEvent])
async def list_activity(
    limit: int = Query(default=120, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    activities: list[dict[str, object]] = []
    activities.extend(await _audit_activity(db))
    activities.extend(await _step_activity(db))
    activities.extend(await _event_activity(db))
    activities.extend(await _issue_activity(db))
    activities.extend(await _run_activity(db))
    activities.extend(await _validation_activity(db))
    activities.extend(await _security_activity(db))
    activities.extend(await _pr_activity(db))
    activities.extend(await _eval_activity(db))
    activities.sort(key=lambda item: str(item["created_at"]), reverse=True)
    return activities[:limit]


async def _audit_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100))
    return [
        _activity(
            source="audit",
            action=audit.action,
            status="recorded",
            created_at=audit.created_at,
            entity_type=audit.entity_type,
            entity_id=audit.entity_id,
            metadata=audit.metadata_json,
        )
        for audit in result.scalars().all()
    ]


async def _step_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(AgentStep).order_by(AgentStep.created_at.desc()).limit(100))
    return [
        _activity(
            source="agent_step",
            action=step.step_name,
            status=step.status,
            created_at=step.created_at,
            entity_type="agent_run",
            entity_id=str(step.run_id),
            metadata={"error": step.error, "latency_ms": step.latency_ms},
        )
        for step in result.scalars().all()
    ]


async def _event_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(GitHubEvent).order_by(GitHubEvent.received_at.desc()).limit(80))
    return [
        _activity(
            source="github_event",
            action=event.event_type,
            status=event.status,
            created_at=event.received_at,
            entity_type="github_event",
            entity_id=str(event.id),
            metadata={"delivery_id": event.delivery_id, "processed_at": event.processed_at},
        )
        for event in result.scalars().all()
    ]


async def _issue_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(Issue).order_by(Issue.created_at.desc()).limit(80))
    return [
        _activity(
            source="issue",
            action=issue.title,
            status=issue.status,
            created_at=issue.created_at,
            entity_type="issue",
            entity_id=str(issue.id),
            metadata={"number": issue.number, "risk_score": issue.risk_score, "issue_type": issue.issue_type},
        )
        for issue in result.scalars().all()
    ]


async def _run_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(80))
    return [
        _activity(
            source="agent_run",
            action=run.state,
            status=run.state,
            created_at=run.started_at,
            entity_type="agent_run",
            entity_id=str(run.id),
            metadata={"issue_id": str(run.issue_id) if run.issue_id else None, "plan_id": str(run.plan_id) if run.plan_id else None},
        )
        for run in result.scalars().all()
    ]


async def _validation_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(ValidationResult).limit(80))
    return [
        _activity(
            source="validation",
            action=validation.command,
            status=validation.status,
            created_at=datetime.min,
            entity_type="agent_run",
            entity_id=str(validation.run_id),
            metadata={"duration_ms": validation.duration_ms, "summary": validation.parsed_summary},
        )
        for validation in result.scalars().all()
    ]


async def _security_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(SecurityFinding).limit(80))
    return [
        _activity(
            source="security",
            action=finding.tool,
            status=finding.status,
            created_at=datetime.min,
            entity_type="agent_run",
            entity_id=str(finding.run_id),
            metadata={"severity": finding.severity, "file_path": finding.file_path, "description": finding.description},
        )
        for finding in result.scalars().all()
    ]


async def _pr_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(PullRequest).order_by(PullRequest.created_at.desc()).limit(80))
    return [
        _activity(
            source="pull_request",
            action=f"PR #{pr.pr_number}",
            status=pr.status,
            created_at=pr.created_at,
            entity_type="pull_request",
            entity_id=str(pr.id),
            metadata={"url": pr.url, "ci_status": pr.ci_status, "risk_score": pr.risk_score},
        )
        for pr in result.scalars().all()
    ]


async def _eval_activity(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(40))
    return [
        _activity(
            source="eval",
            action=eval_run.benchmark_version,
            status="reported",
            created_at=eval_run.created_at,
            entity_type="eval_run",
            entity_id=str(eval_run.id),
            metadata={"report_uri": eval_run.report_uri, "metrics": eval_run.metrics_json},
        )
        for eval_run in result.scalars().all()
    ]


def _activity(
    *,
    source: str,
    action: str,
    status: str,
    created_at: datetime,
    entity_type: str,
    entity_id: str | None,
    metadata: dict[str, object],
) -> dict[str, object]:
    return {
        "source": source,
        "action": action,
        "status": status,
        "created_at": created_at,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "metadata": metadata,
    }
