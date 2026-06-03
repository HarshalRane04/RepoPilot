from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import GitHubEvent
from app.db.session import get_db
from app.services.github_ingestion import DuplicateDelivery, store_webhook_event
from app.services.github_webhooks import GitHubSignatureVerifier, WebhookSignatureError
from app.services.runtime_secrets import effective_settings
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
        return {
            "status": "duplicate",
            "event_id": str(duplicate.event.id),
            "delivery_id": x_github_delivery,
            "queued": False,
        }

    queued = _dispatch_event(event.id)
    if queued:
        event.status = "queued"
        await db.commit()
    elif settings.enable_queue_dispatch:
        event.status = "enqueue_failed"
        await db.commit()

    return {
        "status": "accepted",
        "event_id": str(event.id),
        "delivery_id": x_github_delivery,
        "queued": queued,
    }


def _dispatch_event(event_id: UUID) -> bool:
    if not settings.enable_queue_dispatch:
        return False

    try:
        process_github_event_task.delay(str(event_id))
        return True
    except Exception:
        logger.exception("Failed to enqueue GitHub event", extra={"event_id": str(event_id)})
        return False


@router.get("/events")
async def list_webhook_events(db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    result = await db.execute(select(GitHubEvent).order_by(GitHubEvent.received_at.desc()).limit(50))
    events = result.scalars().all()
    return [
        {
            "id": str(event.id),
            "delivery_id": event.delivery_id,
            "event_type": event.event_type,
            "status": event.status,
            "received_at": event.received_at,
            "processed_at": event.processed_at,
        }
        for event in events
    ]
