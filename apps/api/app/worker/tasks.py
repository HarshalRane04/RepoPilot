from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import timedelta
from uuid import UUID

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.models import AgentRun, AgentStep, ArtifactRecord, GitHubEvent, utc_now
from app.db.session import AsyncSessionLocal, engine
from app.services.artifacts import ArtifactStore, ArtifactUnavailable
from app.services.github_ingestion import process_github_event
from app.services.audit import record_audit
from app.services.run_orchestrator import RunOrchestrator
from app.services.security_envelope import redact_text
from app.services.state_machine import TERMINAL_STATES, next_states, transition_run
from app.services.workspace_cleanup import WorkspaceCleanupService
from app.worker.celery_app import celery_app


@celery_app.task(name="repopilot.healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "repopilot-worker"}


@celery_app.task(bind=True, name="repopilot.github.process_event", max_retries=5)
def process_github_event_task(self, event_id: str) -> dict[str, str]:
    try:
        return asyncio.run(_process_github_event(event_id))
    except Exception as exc:
        exhausted = self.request.retries >= self.max_retries
        asyncio.run(_record_processing_failure(event_id, exc=exc, exhausted=exhausted))
        if exhausted:
            raise
        countdown = min(300, settings.webhook_dispatch_retry_interval_seconds * (2 ** self.request.retries))
        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(name="repopilot.github.reconcile_dispatch")
def reconcile_github_event_dispatch_task() -> dict[str, int]:
    return asyncio.run(_reconcile_github_event_dispatch())


@celery_app.task(name="repopilot.run.execute")
def execute_agent_run_task(run_id: str, actor_id: str | None = None) -> dict[str, object]:
    try:
        return asyncio.run(_execute_agent_run(run_id, actor_id=actor_id))
    except Exception as exc:
        asyncio.run(_record_agent_run_execution_failure(run_id, exc=exc))
        raise


@celery_app.task(name="repopilot.run.reconcile_stale")
def reconcile_stale_agent_runs_task() -> dict[str, int]:
    return asyncio.run(_reconcile_stale_agent_runs())


@celery_app.task(name="repopilot.workspace.cleanup")
def cleanup_stale_workspaces_task() -> dict[str, object]:
    return asyncio.run(_cleanup_stale_workspaces())


@celery_app.task(name="repopilot.artifacts.retention_cleanup")
def cleanup_artifacts_retention_task() -> dict[str, object]:
    return asyncio.run(_cleanup_artifacts_retention())


async def _process_github_event(event_id: str) -> dict[str, str]:
    try:
        async with AsyncSessionLocal() as db:
            return await process_github_event(db, event_id=UUID(event_id))
    finally:
        await engine.dispose()


async def _execute_agent_run(run_id: str, *, actor_id: str | None) -> dict[str, object]:
    try:
        async with AsyncSessionLocal() as db:
            return await RunOrchestrator().execute(db, run_id=UUID(run_id), actor_id=actor_id)
    finally:
        await engine.dispose()


async def _record_agent_run_execution_failure(run_id: str, *, exc: Exception) -> None:
    try:
        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, UUID(run_id))
            if run is None:
                return
            error = redact_text(f"{type(exc).__name__}: {str(exc)[:500]}")
            db.add(
                AgentStep(
                    run_id=run.id,
                    step_name="ORCHESTRATE_RUN",
                    output_json={"phase": "failed", "error": error},
                    status="failed",
                    error=error,
                )
            )
            if run.state not in TERMINAL_STATES and "FAILED" in next_states(run.state):
                await transition_run(
                    db,
                    run=run,
                    next_state="FAILED",
                    actor_type="system",
                    reason="Run orchestration failed unexpectedly.",
                    metadata={"error": error},
                )
            await record_audit(
                db,
                actor_type="system",
                action="run.orchestration_failed",
                entity_type="agent_run",
                entity_id=str(run.id),
                metadata={"error": error},
            )
            await db.commit()
    finally:
        await engine.dispose()


async def _reconcile_stale_agent_runs() -> dict[str, int]:
    stale_before = utc_now() - timedelta(seconds=settings.run_orchestration_stale_seconds)
    try:
        async with AsyncSessionLocal() as db:
            return await RunOrchestrator().reconcile_stale_runs(db, stale_before=stale_before)
    finally:
        await engine.dispose()


async def _record_processing_failure(event_id: str, *, exc: Exception, exhausted: bool) -> None:
    try:
        async with AsyncSessionLocal() as db:
            event = await db.get(GitHubEvent, UUID(event_id))
            if event is None:
                return
            event.retry_count += 1
            event.status = "failed" if exhausted else "retrying"
            event.last_error = redact_text(f"{type(exc).__name__}: {str(exc)[:400]}")
            event.next_retry_at = (
                None
                if exhausted
                else utc_now() + timedelta(seconds=settings.webhook_dispatch_retry_interval_seconds)
            )
            await db.commit()
    finally:
        await engine.dispose()


async def _reconcile_github_event_dispatch() -> dict[str, int]:
    if not settings.enable_queue_dispatch:
        return {"queued": 0, "failed": 0}
    queued = 0
    failed = 0
    now = utc_now()
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(GitHubEvent)
                .where(
                    GitHubEvent.status.in_({"received", "enqueue_failed"}),
                    GitHubEvent.retry_count < settings.webhook_dispatch_max_retries,
                    or_(GitHubEvent.next_retry_at.is_(None), GitHubEvent.next_retry_at <= now),
                )
                .order_by(GitHubEvent.received_at.asc())
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            for event in rows.scalars().all():
                try:
                    process_github_event_task.delay(str(event.id))
                except Exception as exc:
                    failed += 1
                    event.retry_count += 1
                    event.last_error = redact_text(f"{type(exc).__name__}: {str(exc)[:400]}")
                    if event.retry_count >= settings.webhook_dispatch_max_retries:
                        event.status = "failed"
                        event.next_retry_at = None
                    else:
                        event.status = "enqueue_failed"
                        event.next_retry_at = now + timedelta(seconds=settings.webhook_dispatch_retry_interval_seconds)
                else:
                    queued += 1
                    event.status = "queued"
                    event.enqueued_at = now
                    event.next_retry_at = None
                    event.last_error = None
            await db.commit()
    finally:
        await engine.dispose()
    return {"queued": queued, "failed": failed}


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


async def _cleanup_artifacts_retention() -> dict[str, object]:
    store = ArtifactStore()
    retention = store.plan_retention()
    payload: dict[str, object] = asdict(retention)
    payload["database_records_marked_unavailable"] = 0
    if retention.dry_run or not retention.storage_keys:
        return payload
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(ArtifactRecord).where(
                    ArtifactRecord.storage_backend == "local",
                    ArtifactRecord.storage_key.in_(retention.storage_keys),
                )
            )
            marked = 0
            for record in rows.scalars().all():
                try:
                    store.resolve_record(record, verify_checksum=False)
                except ArtifactUnavailable:
                    if record.deleted_at is None:
                        record.deleted_at = utc_now()
                        marked += 1
            await db.commit()
            payload["database_records_marked_unavailable"] = marked
    finally:
        await engine.dispose()
    return payload
