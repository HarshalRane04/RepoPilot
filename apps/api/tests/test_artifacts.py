from __future__ import annotations

import hashlib
from uuid import uuid4

from app.db.models import ArtifactRecord
from app.services.artifacts import ArtifactStore, maybe_externalize_json


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
