from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.services.security_envelope import redact_data


async def record_audit(
    db: AsyncSession,
    *,
    actor_type: str,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    audit = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=redact_data(metadata or {}),
    )
    db.add(audit)
    return audit
