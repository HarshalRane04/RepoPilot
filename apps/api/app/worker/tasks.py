from __future__ import annotations

import asyncio
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.db.models import AgentRun
from app.db.session import AsyncSessionLocal, engine
from app.services.artifacts import ArtifactStore
from app.services.github_ingestion import process_github_event
from app.services.state_machine import TERMINAL_STATES
from app.services.workspace_cleanup import WorkspaceCleanupService
from app.worker.celery_app import celery_app


@celery_app.task(name="repopilot.healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "repopilot-worker"}


@celery_app.task(name="repopilot.github.process_event")
def process_github_event_task(event_id: str) -> dict[str, str]:
    return asyncio.run(_process_github_event(event_id))


@celery_app.task(name="repopilot.workspace.cleanup")
def cleanup_stale_workspaces_task() -> dict[str, object]:
    return asyncio.run(_cleanup_stale_workspaces())


@celery_app.task(name="repopilot.artifacts.retention_cleanup")
def cleanup_artifacts_retention_task() -> dict[str, object]:
    return asdict(ArtifactStore().plan_retention())


async def _process_github_event(event_id: str) -> dict[str, str]:
    try:
        async with AsyncSessionLocal() as db:
            return await process_github_event(db, event_id=UUID(event_id))
    finally:
        await engine.dispose()


async def _cleanup_stale_workspaces() -> dict[str, object]:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AgentRun.id).where(AgentRun.state.notin_(list(TERMINAL_STATES))))
            active_run_ids = set(result.scalars().all())
        cleanup = WorkspaceCleanupService(
            max_age_seconds=settings.workspace_cleanup_max_age_seconds
        ).cleanup_stale_workspaces(active_run_ids=active_run_ids)
        cleanup["active_run_ids_count"] = len(active_run_ids)
        return cleanup
    finally:
        await engine.dispose()
