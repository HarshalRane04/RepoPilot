from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, EvalRun, PullRequest, Repository, SecurityFinding, ValidationResult
from app.db.session import get_db
from app.services.ci_metrics import CIMetricsService

router = APIRouter()


@router.get("/overview")
async def metrics_overview(db: AsyncSession = Depends(get_db)) -> dict[str, int | float]:
    repo_count = await db.scalar(select(func.count()).select_from(Repository))
    run_count = await db.scalar(select(func.count()).select_from(AgentRun))
    open_pr_count = await db.scalar(
        select(func.count()).select_from(PullRequest).where(PullRequest.status.in_(["draft", "ready_for_review"]))
    )
    security_finding_count = await db.scalar(select(func.count()).select_from(SecurityFinding))
    blocking_finding_count = await db.scalar(
        select(func.count())
        .select_from(SecurityFinding)
        .where(SecurityFinding.status == "open", SecurityFinding.severity.in_(["high", "critical"]))
    )
    passed_validation_count = await db.scalar(
        select(func.count()).select_from(ValidationResult).where(ValidationResult.status == "passed")
    )
    ready_pr_count = await db.scalar(select(func.count()).select_from(PullRequest).where(PullRequest.status == "ready_for_review"))
    eval_count = await db.scalar(select(func.count()).select_from(EvalRun))
    ci_metrics = await CIMetricsService().overview(db)
    return {
        "repositories": repo_count or 0,
        "agent_runs": run_count or 0,
        "open_pull_requests": open_pr_count or 0,
        "security_findings": security_finding_count or 0,
        "blocking_security_findings": blocking_finding_count or 0,
        "passed_validations": passed_validation_count or 0,
        "ready_for_review_prs": ready_pr_count or 0,
        "eval_runs": eval_count or 0,
        **ci_metrics.as_dict(),
    }
