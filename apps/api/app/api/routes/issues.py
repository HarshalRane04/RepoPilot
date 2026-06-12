from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Issue, Plan, Repository
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_issue_access, require_role
from app.services.planning import PlanningService
from app.services.security_envelope import rate_limit
from app.services.triage import TriageService

router = APIRouter()


class TriageRequest(BaseModel):
    body: str = ""


@router.get("")
async def list_issues(
    limit: int = Query(default=200, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    require_role(current_user, "viewer")
    result = await db.execute(select(Issue).order_by(Issue.created_at.desc()).limit(limit))
    issues = result.scalars().all()
    response: list[dict[str, object]] = []
    for issue in issues:
        repository = await db.get(Repository, issue.repository_id)
        plan = await _latest_plan_for_issue(db, issue)
        run = await _latest_run_for_issue(db, issue)
        response.append(_issue_response(issue, repository=repository, plan=plan, run=run))
    return response


@router.post("/{issue_id}/plan", status_code=202)
async def generate_issue_plan(
    issue_id: UUID,
    _rate_limit: None = Depends(rate_limit("issue-plan", limit_attr="rate_limit_expensive_per_minute")),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        issue = await require_issue_access(db, issue_id=issue_id, current_user=current_user, action="write")
        plan, run = await PlanningService().generate_plan(db, issue_id=issue.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "waiting_for_approval",
        "issue_id": str(issue_id),
        "plan_id": str(plan.id),
        "run_id": str(run.id),
        "plan": plan.plan_json,
    }


@router.get("/{issue_id}")
async def get_issue(
    issue_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    issue = await require_issue_access(db, issue_id=issue_id, current_user=current_user, action="read")
    repository = await db.get(Repository, issue.repository_id)
    plan = await _latest_plan_for_issue(db, issue)
    run = await _latest_run_for_issue(db, issue)
    return _issue_response(issue, repository=repository, plan=plan, run=run)


@router.post("/{issue_id}/triage")
async def triage_issue(
    issue_id: UUID,
    request: TriageRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    issue = await require_issue_access(db, issue_id=issue_id, current_user=current_user, action="write")

    run = await _latest_run_for_issue(db, issue)
    if run is not None:
        result = await TriageService().triage_with_model(db, run_id=run.id, issue_id=str(issue.id), title=issue.title, body=request.body)
    else:
        result = TriageService().triage(issue_id=str(issue.id), title=issue.title, body=request.body)
    issue.issue_type = result.issue_type.value
    issue.complexity = result.complexity.value
    issue.risk_score = result.risk_score
    issue.status = _status_for_recommended_action(result.recommended_action)
    await db.commit()
    await db.refresh(issue)

    response = _issue_response(issue)
    response["triage"] = result.model_dump(mode="json")
    return response


async def _latest_plan_for_issue(db: AsyncSession, issue: Issue) -> Plan | None:
    result = await db.execute(
        select(Plan).where(Plan.issue_id == issue.id).order_by(Plan.version.desc()).limit(1)
    )
    return result.scalars().first()


async def _latest_run_for_issue(db: AsyncSession, issue: Issue) -> AgentRun | None:
    result = await db.execute(
        select(AgentRun).where(AgentRun.issue_id == issue.id).order_by(AgentRun.started_at.desc()).limit(1)
    )
    return result.scalars().first()


def _issue_response(
    issue: Issue,
    *,
    repository: Repository | None = None,
    plan: Plan | None = None,
    run: AgentRun | None = None,
) -> dict[str, object]:
    response: dict[str, object] = {
        "id": str(issue.id),
        "repository_id": str(issue.repository_id),
        "number": issue.number,
        "title": issue.title,
        "issue_type": issue.issue_type,
        "complexity": issue.complexity,
        "risk_score": issue.risk_score,
        "status": issue.status,
        "created_at": issue.created_at,
    }
    if repository is not None:
        response["repository"] = {
            "id": str(repository.id),
            "owner": repository.owner,
            "name": repository.name,
            "default_branch": repository.default_branch,
            "last_indexed_sha": repository.last_indexed_sha,
        }
    if plan is not None:
        response["plan"] = {
            "id": str(plan.id),
            "approval_status": plan.approval_status,
            "version": plan.version,
            "approved_at": plan.approved_at,
            "plan": plan.plan_json,
        }
    if run is not None:
        response["run"] = {
            "id": str(run.id),
            "state": run.state,
            "total_tokens": run.total_tokens,
            "total_cost": run.total_cost,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
        }
    return response


def _status_for_recommended_action(recommended_action: str) -> str:
    if recommended_action == "ask_info":
        return "needs_info"
    if recommended_action == "human_review":
        return "needs_human_review"
    if recommended_action == "reject":
        return "rejected"
    return "agent_ready"
