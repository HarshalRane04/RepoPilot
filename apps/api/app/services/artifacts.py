from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ArtifactRecord


SAFE_EXTENSION_PATTERN = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9._-]{0,16}$")


@dataclass(frozen=True)
class StoredArtifact:
    id: UUID
    uri: str
    artifact_type: str
    storage_backend: str
    storage_key: str
    sha256: str
    byte_size: int
    content_type: str
    metadata: dict[str, Any]

    def reference(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "uri": self.uri,
            "artifact_type": self.artifact_type,
            "storage_backend": self.storage_backend,
            "storage_key": self.storage_key,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "content_type": self.content_type,
            "metadata": self.metadata,
        }


class ArtifactStore:
    def __init__(self, *, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.artifact_store_root).expanduser()

    def write_text(
        self,
        db: AsyncSession,
        *,
        run_id: UUID | None,
        artifact_type: str,
        text: str,
        content_type: str = "text/plain; charset=utf-8",
        metadata: dict[str, Any] | None = None,
        extension: str = ".txt",
    ) -> StoredArtifact:
        return self.write_bytes(
            db,
            run_id=run_id,
            artifact_type=artifact_type,
            data=text.encode("utf-8"),
            content_type=content_type,
            metadata=metadata,
            extension=extension,
        )

    def write_json(
        self,
        db: AsyncSession,
        *,
        run_id: UUID | None,
        artifact_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> StoredArtifact:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return self.write_text(
            db,
            run_id=run_id,
            artifact_type=artifact_type,
            text=text,
            content_type="application/json",
            metadata=metadata,
            extension=".json",
        )

    def write_bytes(
        self,
        db: AsyncSession,
        *,
        run_id: UUID | None,
        artifact_type: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
        extension: str = ".bin",
    ) -> StoredArtifact:
        artifact_id = uuid.uuid4()
        safe_extension = self._safe_extension(extension)
        run_segment = str(run_id) if run_id else "global"
        storage_key = f"{run_segment}/{artifact_id}{safe_extension}"
        target = self.root / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        digest = hashlib.sha256(data).hexdigest()
        uri = f"local://artifacts/{storage_key}"
        metadata_json = dict(metadata or {})
        record = ArtifactRecord(
            id=artifact_id,
            run_id=run_id,
            artifact_type=artifact_type,
            uri=uri,
            storage_backend="local",
            storage_key=storage_key,
            sha256=digest,
            byte_size=len(data),
            content_type=content_type,
            metadata_json=metadata_json,
        )
        db.add(record)
        return StoredArtifact(
            id=artifact_id,
            uri=uri,
            artifact_type=artifact_type,
            storage_backend="local",
            storage_key=storage_key,
            sha256=digest,
            byte_size=len(data),
            content_type=content_type,
            metadata=metadata_json,
        )

    def _safe_extension(self, extension: str) -> str:
        if not extension.startswith("."):
            extension = f".{extension}"
        if not SAFE_EXTENSION_PATTERN.fullmatch(extension):
            return ".bin"
        return extension


def maybe_externalize_json(
    db: AsyncSession,
    *,
    run_id: UUID | None,
    artifact_type: str,
    payload: dict[str, Any],
    inline_max_bytes: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    if len(encoded) <= (inline_max_bytes if inline_max_bytes is not None else settings.artifact_inline_max_bytes):
        return payload
    artifact = ArtifactStore().write_bytes(
        db,
        run_id=run_id,
        artifact_type=artifact_type,
        data=encoded,
        content_type="application/json",
        metadata=metadata,
        extension=".json",
    )
    return {
        "artifact_uri": artifact.uri,
        "artifact_sha256": artifact.sha256,
        "artifact_byte_size": artifact.byte_size,
        "artifact_type": artifact.artifact_type,
        "externalized": True,
    }
