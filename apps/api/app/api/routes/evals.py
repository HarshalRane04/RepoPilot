from fastapi import APIRouter, Depends
from repopilot_contracts import EvalReportsResponse, EvalRunRequest, EvalRunResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvalRun
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_role
from app.services.eval_runner import EvalRunner

router = APIRouter()


@router.post("/run", status_code=202, response_model=EvalRunResult)
async def run_evaluation(
    request: EvalRunRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    require_role(current_user, "admin")
    result = await EvalRunner().run(db, request=request)
    return result.model_dump(mode="json")


@router.get("/reports", response_model=EvalReportsResponse)
async def evaluation_reports(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    result = await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()))
    reports = result.scalars().all()
    return {
        "reports": [
            {
                "id": str(report.id),
                "benchmark_version": report.benchmark_version,
                "metrics": report.metrics_json,
                "report_uri": report.report_uri,
                "created_at": report.created_at,
            }
            for report in reports
        ],
    }
