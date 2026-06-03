from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from repopilot_contracts import CIAnalysisRequest, CIAnalysisResult, PullRequestSummaryResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Issue, Plan, PullRequest, Repository, SecurityFinding, ValidationResult
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_pr_access
from app.services.ci_analyzer import CIAnalyzer
from app.services.revision_planner import RevisionPlanner

router = APIRouter()


class RevisionPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(default="", max_length=4000)


@router.get("", response_model=list[PullRequestSummaryResponse])
async def list_pull_requests(
    limit: int = Query(default=100, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    result = await db.execute(select(PullRequest).order_by(PullRequest.created_at.desc()).limit(limit))
    prs = result.scalars().all()
    return [await _pr_summary(pr, db) for pr in prs]


@router.get("/{pr_id}/summary", response_model=PullRequestSummaryResponse)
async def get_pr_summary(pr_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    pr = await db.get(PullRequest, pr_id)
    if pr is None:
        raise HTTPException(status_code=404, detail="Pull request not found")
    return await _pr_summary(pr, db)


async def _pr_summary(pr: PullRequest, db: AsyncSession) -> dict[str, object]:
    run = await db.get(AgentRun, pr.run_id)
    issue = await db.get(Issue, run.issue_id) if run and run.issue_id else None
    repository = await db.get(Repository, issue.repository_id) if issue else None
    plan = await db.get(Plan, run.plan_id) if run and run.plan_id else None
    validations = (await db.execute(select(ValidationResult).where(ValidationResult.run_id == pr.run_id))).scalars().all()
    findings = (await db.execute(select(SecurityFinding).where(SecurityFinding.run_id == pr.run_id))).scalars().all()
    plan_json = plan.plan_json if plan is not None else {}
    changed_files = _string_list(plan_json.get("files_to_modify")) + _string_list(plan_json.get("tests_to_add"))
    return {
        "pr_id": str(pr.id),
        "run_id": str(pr.run_id),
        "pr_number": pr.pr_number,
        "url": pr.url,
        "status": pr.status,
        "ci_status": pr.ci_status,
        "risk_score": pr.risk_score,
        "created_at": pr.created_at,
        "issue": {
            "id": str(issue.id),
            "number": issue.number,
            "title": issue.title,
            "status": issue.status,
        }
        if issue
        else None,
        "repository": {
            "id": str(repository.id),
            "owner": repository.owner,
            "name": repository.name,
            "default_branch": repository.default_branch,
        }
        if repository
        else None,
        "plan": {
            "id": str(plan.id),
            "approval_status": plan.approval_status,
            "summary": plan_json.get("summary"),
            "rollback_plan": plan_json.get("rollback_plan"),
            "files_to_modify": _string_list(plan_json.get("files_to_modify")),
            "tests_to_add": _string_list(plan_json.get("tests_to_add")),
            "risk_notes": _string_list(plan_json.get("risk_notes")),
        }
        if plan
        else None,
        "changed_files": changed_files,
        "validation_results": [
            {
                "command": validation.command,
                "status": validation.status,
                "duration_ms": validation.duration_ms,
                "parsed_summary": validation.parsed_summary,
                "log_uri": validation.log_uri,
                "evidence_hash": validation.evidence_hash,
            }
            for validation in validations
        ],
        "security_findings": [
            {
                "tool": finding.tool,
                "severity": finding.severity,
                "file_path": finding.file_path,
                "description": finding.description,
                "status": finding.status,
                "status_reason": finding.status_reason,
            }
            for finding in findings
        ],
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@router.post("/{pr_id}/ci", response_model=CIAnalysisResult)
async def analyze_pr_ci(
    pr_id: UUID,
    request: CIAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        result = await CIAnalyzer().analyze_pr(db, pr_id=pr_id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/{pr_id}/revision-plan", status_code=202)
async def create_revision_plan(
    pr_id: UUID,
    request: RevisionPlanRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await require_pr_access(db, pr_id=pr_id, current_user=current_user, action="write")
    try:
        plan = await RevisionPlanner().create_revision_plan(
            db,
            pr_id=pr_id,
            instructions=request.instructions,
            actor_id=current_user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "status": "revision_plan_created",
        "plan_id": str(plan.id),
        "approval_status": plan.approval_status,
        "version": plan.version,
        "plan": plan.plan_json,
    }
