from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
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
        try:
            target.chmod(0o600)
        except OSError:
            pass

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

    def plan_retention(
        self,
        *,
        max_age_seconds: int | None = None,
        dry_run: bool | None = None,
    ) -> RetentionResult:
        max_age = max_age_seconds if max_age_seconds is not None else settings.artifact_retention_max_age_seconds
        is_dry_run = dry_run if dry_run is not None else settings.artifact_retention_dry_run
        cutoff = time.time() - max_age
        resolved_root = self.root.resolve(strict=False)
        candidates: list[Path] = []
        total_bytes = 0

        if not resolved_root.is_dir():
            return RetentionResult(
                store_root=str(resolved_root),
                max_age_seconds=max_age,
                dry_run=is_dry_run,
                removed_count=0,
                removed_bytes=0,
                retained_count=0,
                retained_bytes=0,
                skipped_count=0,
                storage_keys=[],
            )

        for dirpath_str, dirnames, filenames in os.walk(resolved_root):
            dirpath = Path(dirpath_str).resolve()
            if not str(dirpath).startswith(str(resolved_root) + os.sep) and dirpath != resolved_root:
                continue
            for name in filenames:
                file_path = (dirpath / name).resolve()
                if file_path.is_symlink():
                    continue
                if not str(file_path).startswith(str(resolved_root) + os.sep) and file_path != resolved_root:
                    continue
                try:
                    stat = file_path.stat()
                except OSError:
                    continue
                if stat.st_mtime < cutoff:
                    candidates.append(file_path)
                    total_bytes += stat.st_size

        storage_keys = [str(c.relative_to(resolved_root)) for c in candidates]

        removed_count = 0
        removed_bytes = 0
        if not is_dry_run:
            for file_path in candidates:
                try:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    removed_count += 1
                    removed_bytes += file_size
                except OSError:
                    continue

        retained_count = 0
        retained_bytes = 0
        if resolved_root.is_dir():
            _retained, _rbytes = _count_files(resolved_root)
            retained_count = _retained
            retained_bytes = _rbytes

        if is_dry_run:
            return RetentionResult(
                store_root=str(resolved_root),
                max_age_seconds=max_age,
                dry_run=True,
                removed_count=0,
                removed_bytes=0,
                retained_count=retained_count,
                retained_bytes=retained_bytes,
                skipped_count=0,
                storage_keys=storage_keys,
            )

        return RetentionResult(
            store_root=str(resolved_root),
            max_age_seconds=max_age,
            dry_run=False,
            removed_count=removed_count,
            removed_bytes=removed_bytes,
            retained_count=retained_count,
            retained_bytes=retained_bytes,
            skipped_count=0,
            storage_keys=storage_keys,
        )


@dataclass(frozen=True)
class RetentionResult:
    store_root: str
    max_age_seconds: int
    dry_run: bool
    removed_count: int
    removed_bytes: int
    retained_count: int
    retained_bytes: int
    skipped_count: int
    storage_keys: list[str] = field(default_factory=list)


def _count_files(root: Path) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    for dirpath_str, _dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath_str).resolve()
        for name in filenames:
            file_path = (dirpath / name).resolve()
            if not str(file_path).startswith(str(root) + os.sep) and file_path != root:
                continue
            try:
                st = file_path.stat()
                count += 1
                total_bytes += st.st_size
            except OSError:
                continue
    return count, total_bytes


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
