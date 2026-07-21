from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactRecord
from app.db.session import get_db
from app.services.artifacts import ArtifactIntegrityError, ArtifactStore, ArtifactUnavailable
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_run_access

router = APIRouter()


@router.get("/{run_id}/artifacts")
async def list_run_artifacts(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    await require_run_access(db, run_id=run_id, current_user=current_user, action="read")
    records = (
        await db.execute(
            select(ArtifactRecord)
            .where(ArtifactRecord.run_id == run_id)
            .order_by(ArtifactRecord.created_at.desc())
        )
    ).scalars().all()
    return [_artifact_response(record) for record in records]


@router.get("/{run_id}/artifacts/{artifact_id}", response_class=FileResponse)
async def download_run_artifact(
    run_id: UUID,
    artifact_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    await require_run_access(db, run_id=run_id, current_user=current_user, action="read")
    record = await db.get(ArtifactRecord, artifact_id)
    if record is None or record.run_id != run_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if record.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Artifact bytes were retired by the retention policy.")
    try:
        path = ArtifactStore().resolve_record(record)
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=record.content_type,
        filename=f"{record.artifact_type}-{record.id}{path.suffix}",
        headers={"ETag": f'"sha256:{record.sha256}"', "Cache-Control": "private, no-store"},
    )


def _artifact_response(record: ArtifactRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "run_id": str(record.run_id) if record.run_id else None,
        "artifact_type": record.artifact_type,
        "storage_backend": record.storage_backend,
        "sha256": record.sha256,
        "byte_size": record.byte_size,
        "content_type": record.content_type,
        "metadata": record.metadata_json,
        "created_at": record.created_at,
        "deleted_at": record.deleted_at,
        "available": record.deleted_at is None,
        "download_url": f"/runs/{record.run_id}/artifacts/{record.id}" if record.run_id else None,
    }
