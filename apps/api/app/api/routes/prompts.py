from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from repopilot_contracts import AgentRunState
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AgentRun, AgentStep, Installation, Issue, Repository
from app.db.session import get_db
from app.services.audit import record_audit
from app.services.auth import CurrentUser, get_current_user
from app.services.planning import PlanningService
from app.services.runtime_secrets import effective_settings
from app.services.security_envelope import rate_limit
from app.services.triage import TriageService

router = APIRouter()


class PromptSubmitRequest(BaseModel):
    repository_id: str | None = None
    title: str = Field(min_length=4, max_length=180)
    prompt: str = Field(min_length=8, max_length=8000)
    auto_plan: bool = False


@router.post("", status_code=202)
async def submit_prompt(
    request: PromptSubmitRequest,
    _rate_limit: None = Depends(rate_limit("prompts", limit_attr="rate_limit_expensive_per_minute")),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    repository = await _resolve_repository(db, repository_id=request.repository_id)
    issue_number = await _next_issue_number(db, repository=repository)
    issue = Issue(
        repository_id=repository.id,
        number=issue_number,
        title=request.title,
        body_hash=_text_hash(request.prompt),
        status="new",
    )
    db.add(issue)
    await db.flush()

    run = AgentRun(issue_id=issue.id, state=AgentRunState.TRIAGE_ISSUE.value, model_used=effective_settings(settings).model_name)
    db.add(run)
    await db.flush()

    triage = await TriageService().triage_with_model(db, run_id=run.id, issue_id=str(issue.id), title=issue.title, body=request.prompt)
    issue.issue_type = triage.issue_type.value
    issue.complexity = triage.complexity.value
    issue.risk_score = triage.risk_score
    issue.status = _status_for_recommended_action(triage.recommended_action)
    run.state = _state_for_recommended_action(triage.recommended_action)
    db.add(
        AgentStep(
            run_id=run.id,
            step_name=AgentRunState.TRIAGE_ISSUE.value,
            input_hash=_payload_hash({"title": request.title, "prompt": request.prompt}),
            output_json=triage.model_dump(mode="json"),
            status="succeeded",
        )
    )
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="prompt.submitted",
        entity_type="issue",
        entity_id=str(issue.id),
        metadata={"run_id": str(run.id), "repository_id": str(repository.id), "recommended_action": triage.recommended_action},
    )
    await db.commit()
    await db.refresh(issue)
    await db.refresh(run)

    plan_payload: dict[str, object] | None = None
    if request.auto_plan and triage.recommended_action == "plan":
        try:
            plan, plan_run = await PlanningService().generate_plan(db, issue_id=issue.id)
            plan_payload = {"plan_id": str(plan.id), "run_id": str(plan_run.id), "plan": plan.plan_json}
        except ValueError:
            plan_payload = None

    return {
        "status": "accepted",
        "issue": {
            "id": str(issue.id),
            "number": issue.number,
            "title": issue.title,
            "status": issue.status,
            "risk_score": issue.risk_score,
            "issue_type": issue.issue_type,
        },
        "run": {"id": str(run.id), "state": run.state},
        "triage": triage.model_dump(mode="json"),
        "plan": plan_payload,
    }


async def _resolve_repository(db: AsyncSession, *, repository_id: str | None) -> Repository:
    if repository_id:
        repository = await db.get(Repository, UUID(repository_id))
        if repository is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        return repository

    repository = await db.scalar(select(Repository).order_by(Repository.created_at.desc()))
    if repository is not None:
        return repository

    installation = await db.scalar(select(Installation).where(Installation.github_installation_id == "local-prompts"))
    if installation is None:
        installation = Installation(
            github_installation_id="local-prompts",
            account_name="local",
            permissions_json={"source": "prompt-console"},
        )
        db.add(installation)
        await db.flush()
    repository = Repository(
        installation_id=installation.id,
        owner="local",
        name="RepoPilot",
        default_branch="main",
    )
    db.add(repository)
    await db.flush()
    return repository


async def _next_issue_number(db: AsyncSession, *, repository: Repository) -> int:
    current = await db.scalar(select(func.max(Issue.number)).where(Issue.repository_id == repository.id))
    return int(current or 0) + 1


def _status_for_recommended_action(recommended_action: str) -> str:
    if recommended_action == "ask_info":
        return "needs_info"
    if recommended_action == "human_review":
        return "needs_human_review"
    if recommended_action == "reject":
        return "rejected"
    return "agent_ready"


def _state_for_recommended_action(recommended_action: str) -> str:
    if recommended_action == "plan":
        return AgentRunState.WAIT_FOR_APPROVAL.value
    if recommended_action == "human_review":
        return AgentRunState.POLICY_REVIEW_PLAN.value
    if recommended_action == "reject":
        return AgentRunState.REJECTED.value
    return AgentRunState.NEEDS_INFO.value


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_hash(payload: dict[str, object]) -> str:
    return _text_hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))
