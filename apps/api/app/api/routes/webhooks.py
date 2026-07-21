from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import GitHubEvent, utc_now
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_role
from app.services.github_ingestion import DuplicateDelivery, store_webhook_event
from app.services.github_webhooks import GitHubSignatureVerifier, WebhookSignatureError
from app.services.runtime_secrets import effective_settings
from app.services.security_envelope import redact_text
from app.worker.tasks import process_github_event_task

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def receive_github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    if not x_github_event or not x_github_delivery:
        raise HTTPException(status_code=400, detail="Missing GitHub event or delivery headers")

    body = await request.body()
    verifier = GitHubSignatureVerifier(effective_settings(settings).github_webhook_secret)
    try:
        verifier.verify(body=body, signature_header=x_hub_signature_256)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON payload") from exc

    try:
        event = await store_webhook_event(
            db,
            delivery_id=x_github_delivery,
            event_type=x_github_event,
            payload=payload,
        )
        await db.commit()
    except DuplicateDelivery as duplicate:
        queued = False
        if settings.enable_queue_dispatch and duplicate.event.status in {"received", "enqueue_failed"}:
            attempt = _dispatch_event(duplicate.event.id)
            _apply_dispatch_attempt(duplicate.event, attempt)
            await db.commit()
            queued = attempt.queued
        return {
            "status": "duplicate_requeued" if queued else "duplicate",
            "event_id": str(duplicate.event.id),
            "delivery_id": x_github_delivery,
            "queued": queued,
        }

    attempt = _dispatch_event(event.id)
    if settings.enable_queue_dispatch:
        _apply_dispatch_attempt(event, attempt)
        await db.commit()

    return {
        "status": "accepted",
        "event_id": str(event.id),
        "delivery_id": x_github_delivery,
        "queued": attempt.queued,
    }


@dataclass(frozen=True)
class DispatchAttempt:
    queued: bool
    error: str | None = None


def _dispatch_event(event_id: UUID) -> DispatchAttempt:
    if not settings.enable_queue_dispatch:
        return DispatchAttempt(queued=False)

    try:
        process_github_event_task.delay(str(event_id))
        return DispatchAttempt(queued=True)
    except Exception as exc:
        logger.exception("Failed to enqueue GitHub event", extra={"event_id": str(event_id)})
        return DispatchAttempt(queued=False, error=redact_text(f"{type(exc).__name__}: {str(exc)[:400]}"))


def _apply_dispatch_attempt(event: GitHubEvent, attempt: DispatchAttempt) -> None:
    if attempt.queued:
        event.status = "queued"
        event.enqueued_at = utc_now()
        event.next_retry_at = None
        event.last_error = None
        return
    event.retry_count += 1
    event.last_error = redact_text(attempt.error or "Queue dispatch did not accept the event.")
    if event.retry_count >= settings.webhook_dispatch_max_retries:
        event.status = "failed"
        event.next_retry_at = None
    else:
        event.status = "enqueue_failed"
        event.next_retry_at = utc_now() + timedelta(seconds=settings.webhook_dispatch_retry_interval_seconds)


@router.get("/events")
async def list_webhook_events(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    require_role(current_user, "viewer")
    result = await db.execute(select(GitHubEvent).order_by(GitHubEvent.received_at.desc()).limit(50))
    events = result.scalars().all()
    return [
        {
            "id": str(event.id),
            "delivery_id": event.delivery_id,
            "event_type": event.event_type,
            "status": event.status,
            "retry_count": event.retry_count,
            "next_retry_at": event.next_retry_at,
            "last_error": event.last_error,
            "received_at": event.received_at,
            "processed_at": event.processed_at,
        }
        for event in events
    ]
