from fastapi import APIRouter, Depends

from app.api.routes import activity, auth, evals, health, installations, issues, metrics, plans, prompts, prs, repos, runs, security, settings, tools, webhooks
from app.services.auth import get_current_user

api_router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(get_current_user)])

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

protected_router.include_router(activity.router, prefix="/activity", tags=["activity"])
protected_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
protected_router.include_router(installations.router, prefix="/installations", tags=["installations"])
protected_router.include_router(repos.router, prefix="/repos", tags=["repositories"])
protected_router.include_router(issues.router, prefix="/issues", tags=["issues"])
protected_router.include_router(plans.router, prefix="/plans", tags=["plans"])
protected_router.include_router(runs.router, prefix="/runs", tags=["runs"])
protected_router.include_router(tools.router, prefix="/tools", tags=["tools"])
protected_router.include_router(prs.router, prefix="/prs", tags=["pull requests"])
protected_router.include_router(security.router, prefix="/security", tags=["security"])
protected_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
protected_router.include_router(evals.router, prefix="/evals", tags=["evaluations"])
protected_router.include_router(settings.router, prefix="/settings", tags=["settings"])

api_router.include_router(protected_router)
