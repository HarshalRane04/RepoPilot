from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from repopilot_contracts import CIAnalysisRequest, CIAnalysisResult, PullRequestSummaryResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStep, Issue, Plan, PullRequest, Repository, SecurityFinding, ValidationResult
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_pr_access, require_role
from app.services.ci_analyzer import CIAnalyzer
from app.services.evidence_state import security_scan_evidence_summary, validation_evidence_summary
from app.services.revision_planner import RevisionPlanner

router = APIRouter()


class RevisionPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(default="", max_length=4000)


@router.get("", response_model=list[PullRequestSummaryResponse])
async def list_pull_requests(
    limit: int = Query(default=100, ge=1, le=300),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    require_role(current_user, "viewer")
    result = await db.execute(select(PullRequest).order_by(PullRequest.created_at.desc()).limit(limit))
    prs = result.scalars().all()
    return await _pr_summaries(prs, db)


@router.get("/{pr_id}/summary", response_model=PullRequestSummaryResponse)
async def get_pr_summary(
    pr_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    pr = await require_pr_access(db, pr_id=pr_id, current_user=current_user, action="read")
    return await _pr_summary(pr, db)


async def _pr_summary(pr: PullRequest, db: AsyncSession) -> dict[str, object]:
    summaries = await _pr_summaries([pr], db)
    return summaries[0]


async def _pr_summaries(prs: list[PullRequest], db: AsyncSession) -> list[dict[str, object]]:
    if not prs:
        return []
    run_ids = {pr.run_id for pr in prs}
    runs = (await db.execute(select(AgentRun).where(AgentRun.id.in_(run_ids)))).scalars().all()
    runs_by_id = {run.id: run for run in runs}
    issue_ids = {run.issue_id for run in runs if run.issue_id is not None}
    issues = (await db.execute(select(Issue).where(Issue.id.in_(issue_ids)))).scalars().all() if issue_ids else []
    issues_by_id = {issue.id: issue for issue in issues}
    repository_ids = {
        repository_id
        for repository_id in [*(pr.repository_id for pr in prs), *(issue.repository_id for issue in issues)]
        if repository_id is not None
    }
    repositories = (
        (await db.execute(select(Repository).where(Repository.id.in_(repository_ids)))).scalars().all()
        if repository_ids
        else []
    )
    repositories_by_id = {repository.id: repository for repository in repositories}
    plan_ids = {run.plan_id for run in runs if run.plan_id is not None}
    plans = (await db.execute(select(Plan).where(Plan.id.in_(plan_ids)))).scalars().all() if plan_ids else []
    plans_by_id = {plan.id: plan for plan in plans}
    validations = (
        await db.execute(select(ValidationResult).where(ValidationResult.run_id.in_(run_ids)))
    ).scalars().all()
    validations_by_run: dict[UUID, list[ValidationResult]] = {}
    for validation in validations:
        validations_by_run.setdefault(validation.run_id, []).append(validation)
    findings = (
        await db.execute(select(SecurityFinding).where(SecurityFinding.run_id.in_(run_ids)))
    ).scalars().all()
    findings_by_run: dict[UUID, list[SecurityFinding]] = {}
    for finding in findings:
        findings_by_run.setdefault(finding.run_id, []).append(finding)
    step_rows = await db.execute(
        select(AgentStep)
        .where(
            AgentStep.run_id.in_(run_ids),
            AgentStep.step_name.in_(["OPEN_DRAFT_PR", "IMPLEMENT_PATCH", "RUN_SECURITY_CHECKS", "CODEQL_INGEST"]),
        )
        .order_by(AgentStep.run_id, AgentStep.step_name, AgentStep.created_at.desc())
    )
    latest_steps: dict[tuple[UUID, str], AgentStep] = {}
    security_steps_by_run: dict[UUID, list[AgentStep]] = {}
    for step in step_rows.scalars().all():
        latest_steps.setdefault((step.run_id, step.step_name), step)
        if step.step_name in {"RUN_SECURITY_CHECKS", "CODEQL_INGEST"}:
            security_steps_by_run.setdefault(step.run_id, []).append(step)

    summaries: list[dict[str, object]] = []
    for pr in prs:
        run = runs_by_id.get(pr.run_id)
        issue = issues_by_id.get(run.issue_id) if run and run.issue_id else None
        repository_id = pr.repository_id or (issue.repository_id if issue else None)
        repository = repositories_by_id.get(repository_id) if repository_id else None
        plan = plans_by_id.get(run.plan_id) if run and run.plan_id else None
        plan_json = plan.plan_json if plan is not None else {}
        patch_step = latest_steps.get((pr.run_id, "IMPLEMENT_PATCH"))
        current_patch_hash = _patch_hash_from_step(patch_step)
        run_validations = validations_by_run.get(pr.run_id, [])
        run_findings = findings_by_run.get(pr.run_id, [])
        if current_patch_hash:
            run_validations = [item for item in run_validations if item.patch_hash == current_patch_hash]
            run_findings = [item for item in run_findings if item.patch_hash == current_patch_hash]
        summaries.append(
            _pr_summary_payload(
                pr=pr,
                issue=issue,
                repository=repository,
                plan=plan,
                plan_json=plan_json,
                validations=run_validations,
                findings=run_findings,
                security_steps=security_steps_by_run.get(pr.run_id, []),
                pr_mode=_pr_mode_from_step(pr, latest_steps.get((pr.run_id, "OPEN_DRAFT_PR"))),
                current_patch_hash=current_patch_hash,
                changed_files=_patch_files_from_step(patch_step),
            )
        )
    return summaries


def _pr_summary_payload(
    *,
    pr: PullRequest,
    issue: Issue | None,
    repository: Repository | None,
    plan: Plan | None,
    plan_json: dict[str, object],
    validations: list[ValidationResult],
    findings: list[SecurityFinding],
    security_steps: list[AgentStep],
    pr_mode: str,
    current_patch_hash: str | None,
    changed_files: list[str],
) -> dict[str, object]:
    github_url = pr.url if pr_mode == "real_github" and pr.url.startswith(("https://", "http://")) else None
    planned_files = _string_list(plan_json.get("files_to_modify")) + _string_list(plan_json.get("tests_to_add"))
    return {
        "pr_id": str(pr.id), "run_id": str(pr.run_id), "pr_number": pr.pr_number, "url": pr.url,
        "pr_mode": pr_mode, "is_local_record": pr_mode == "local_record", "github_url": github_url,
        "status": pr.status, "ci_status": pr.ci_status, "risk_score": pr.risk_score, "created_at": pr.created_at,
        "issue": {"id": str(issue.id), "number": issue.number, "title": issue.title, "status": issue.status} if issue else None,
        "repository": {
            "id": str(repository.id), "owner": repository.owner, "name": repository.name,
            "default_branch": repository.default_branch,
        } if repository else None,
        "plan": {
            "id": str(plan.id), "approval_status": plan.approval_status, "summary": plan_json.get("summary"),
            "rollback_plan": plan_json.get("rollback_plan"),
            "files_to_modify": _string_list(plan_json.get("files_to_modify")),
            "tests_to_add": _string_list(plan_json.get("tests_to_add")),
            "risk_notes": _string_list(plan_json.get("risk_notes")),
        } if plan else None,
        "current_patch_hash": current_patch_hash,
        "changed_files": changed_files,
        "planned_files": planned_files,
        "validation_results": [
            {
                "command": item.command, "status": item.status, "duration_ms": item.duration_ms,
                "parsed_summary": item.parsed_summary, "log_uri": item.log_uri, "evidence_hash": item.evidence_hash,
                "patch_hash": item.patch_hash, "sandbox_backend": item.sandbox_backend,
            }
            for item in validations
        ],
        "security_findings": [
            {
                "tool": item.tool, "severity": item.severity, "file_path": item.file_path,
                "description": item.description, "status": item.status, "status_reason": item.status_reason,
                "patch_hash": item.patch_hash,
            }
            for item in findings
        ],
        "validation_evidence": validation_evidence_summary(validations, patch_hash=current_patch_hash),
        "security_scan": security_scan_evidence_summary(
            security_steps,
            patch_hash=current_patch_hash,
            findings=findings,
        ),
    }


def _patch_files_from_step(step: AgentStep | None) -> list[str]:
    if not step or not isinstance(step.output_json, dict):
        return []
    changed_files = step.output_json.get("changed_files")
    if not isinstance(changed_files, list):
        return []
    return [str(item["path"]) for item in changed_files if isinstance(item, dict) and isinstance(item.get("path"), str)]


def _patch_hash_from_step(step: AgentStep | None) -> str | None:
    if not step or not isinstance(step.output_json, dict):
        return None
    value = step.output_json.get("patch_hash")
    return str(value) if value else None


def _pr_mode_from_step(pr: PullRequest, step: AgentStep | None) -> str:
    mode = step.output_json.get("mode") if step and isinstance(step.output_json, dict) else None
    if mode == "real_github_write":
        return "real_github"
    if mode == "local_record" or pr.url.startswith("local://"):
        return "local_record"
    return "real_github" if pr.url.startswith(("https://", "http://")) else "local_record"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


async def _pr_mode(pr: PullRequest, db: AsyncSession) -> str:
    result = await db.execute(
        select(AgentStep)
        .where(AgentStep.run_id == pr.run_id, AgentStep.step_name == "OPEN_DRAFT_PR")
        .order_by(AgentStep.created_at.desc())
        .limit(1)
    )
    step = result.scalar_one_or_none()
    mode = step.output_json.get("mode") if step and isinstance(step.output_json, dict) else None
    if mode == "real_github_write":
        return "real_github"
    if mode == "local_record":
        return "local_record"
    if pr.url.startswith("local://"):
        return "local_record"
    if pr.url.startswith(("https://", "http://")):
        return "real_github"
    return "local_record"


@router.post("/{pr_id}/ci", response_model=CIAnalysisResult)
async def analyze_pr_ci(
    pr_id: UUID,
    request: CIAnalysisRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    require_role(current_user, "admin")
    await require_pr_access(db, pr_id=pr_id, current_user=current_user, action="write")
    try:
        result = await CIAnalyzer().analyze_pr(
            db,
            pr_id=pr_id,
            request=request,
            trusted_evidence=False,
            actor_id=current_user.username,
        )
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
