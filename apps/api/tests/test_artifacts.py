from __future__ import annotations

import hashlib
import os
import stat
import time
from uuid import uuid4

from app.db.models import ArtifactRecord
from app.services.artifacts import ArtifactStore, maybe_externalize_json
from app.worker.tasks import cleanup_artifacts_retention_task


class FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)


def test_artifact_store_writes_file_and_database_pointer(tmp_path) -> None:
    db = FakeDb()
    run_id = uuid4()

    artifact = ArtifactStore(root=tmp_path).write_text(
        db,
        run_id=run_id,
        artifact_type="validation.log",
        text="redacted log",
        content_type="text/plain",
        metadata={"command": "pytest"},
    )

    stored_path = tmp_path / artifact.storage_key
    assert stored_path.read_text(encoding="utf-8") == "redacted log"
    assert artifact.uri.startswith(f"local://artifacts/{run_id}/")
    assert artifact.sha256 == hashlib.sha256(b"redacted log").hexdigest()
    assert artifact.byte_size == len(b"redacted log")
    assert len(db.added) == 1
    record = db.added[0]
    assert isinstance(record, ArtifactRecord)
    assert record.run_id == run_id
    assert record.uri == artifact.uri
    assert record.metadata_json == {"command": "pytest"}
    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600


def test_maybe_externalize_json_keeps_small_payload_inline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.artifacts.settings.artifact_store_root", str(tmp_path))
    db = FakeDb()

    payload = {"summary": "small"}
    result = maybe_externalize_json(db, run_id=uuid4(), artifact_type="tool.output", payload=payload, inline_max_bytes=1000)

    assert result == payload
    assert db.added == []


def test_maybe_externalize_json_replaces_large_payload_with_artifact_pointer(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.artifacts.settings.artifact_store_root", str(tmp_path))
    db = FakeDb()
    run_id = uuid4()

    result = maybe_externalize_json(
        db,
        run_id=run_id,
        artifact_type="tool.output",
        payload={"stdout": "x" * 200},
        inline_max_bytes=20,
    )

    assert result["externalized"] is True
    assert result["artifact_uri"].startswith(f"local://artifacts/{run_id}/")
    assert result["artifact_byte_size"] > 20
    assert len(db.added) == 1


def test_artifact_retention_dry_run_reports_expired_files_without_deleting(tmp_path) -> None:
    old_file = tmp_path / "run-1" / "old.txt"
    old_file.parent.mkdir()
    old_file.write_text("old artifact", encoding="utf-8")
    old_time = time.time() - 3600
    os.utime(old_file, (old_time, old_time))
    fresh_file = tmp_path / "run-1" / "fresh.txt"
    fresh_file.write_text("fresh artifact", encoding="utf-8")

    result = ArtifactStore(root=tmp_path).plan_retention(max_age_seconds=60, dry_run=True)

    assert result.dry_run is True
    assert result.removed_count == 0
    assert result.removed_bytes == 0
    assert result.retained_count == 2
    assert result.storage_keys == ["run-1/old.txt"]
    assert old_file.exists()
    assert fresh_file.exists()


def test_artifact_retention_deletes_only_expired_local_files(tmp_path) -> None:
    old_file = tmp_path / "run-1" / "old.txt"
    old_file.parent.mkdir()
    old_file.write_text("old artifact", encoding="utf-8")
    old_time = time.time() - 3600
    os.utime(old_file, (old_time, old_time))
    fresh_file = tmp_path / "run-1" / "fresh.txt"
    fresh_file.write_text("fresh artifact", encoding="utf-8")

    result = ArtifactStore(root=tmp_path).plan_retention(max_age_seconds=60, dry_run=False)

    assert result.dry_run is False
    assert result.removed_count == 1
    assert result.removed_bytes == len("old artifact")
    assert result.retained_count == 1
    assert result.storage_keys == ["run-1/old.txt"]
    assert not old_file.exists()
    assert fresh_file.exists()


def test_artifact_retention_does_not_follow_symlinks_outside_root(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-secret.txt"
    outside.write_text("do not delete", encoding="utf-8")
    old_time = time.time() - 3600
    os.utime(outside, (old_time, old_time))
    link = tmp_path / "run-1" / "outside-link.txt"
    link.parent.mkdir()
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        outside.unlink(missing_ok=True)
        return

    try:
        result = ArtifactStore(root=tmp_path).plan_retention(max_age_seconds=60, dry_run=False)

        assert result.removed_count == 0
        assert result.storage_keys == []
        assert outside.exists()
        assert link.exists()
    finally:
        link.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)


def test_artifact_retention_celery_task_returns_reviewable_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.artifacts.settings.artifact_store_root", str(tmp_path))
    monkeypatch.setattr("app.services.artifacts.settings.artifact_retention_max_age_seconds", 60)
    monkeypatch.setattr("app.services.artifacts.settings.artifact_retention_dry_run", True)
    old_file = tmp_path / "run-1" / "old.txt"
    old_file.parent.mkdir()
    old_file.write_text("old artifact", encoding="utf-8")
    old_time = time.time() - 3600
    os.utime(old_file, (old_time, old_time))

    result = cleanup_artifacts_retention_task()

    assert result["dry_run"] is True
    assert result["removed_count"] == 0
    assert result["retained_count"] == 1
    assert result["storage_keys"] == ["run-1/old.txt"]
    assert old_file.exists()
