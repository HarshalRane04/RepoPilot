from __future__ import annotations

from pathlib import Path

import pytest

from app.db import migration_verifier


def test_build_target_uses_psycopg_temp_database_and_admin_database() -> None:
    target = migration_verifier.build_target(
        "postgresql+asyncpg://repopilot:secret@postgres:5432/repopilot",
        database_name="repopilot_migration_verify_test",
        admin_database="postgres",
    )

    assert target.database_name == "repopilot_migration_verify_test"
    assert target.admin_url == "postgresql+psycopg://repopilot:secret@postgres:5432/postgres"
    assert target.migration_url == "postgresql+psycopg://repopilot:secret@postgres:5432/repopilot_migration_verify_test"


def test_build_target_rejects_non_postgres_url() -> None:
    with pytest.raises(ValueError, match="requires PostgreSQL"):
        migration_verifier.build_target("sqlite:///tmp/repopilot.db")


def test_build_target_rejects_unsafe_database_name() -> None:
    with pytest.raises(ValueError, match="Temporary database name"):
        migration_verifier.build_target(
            "postgresql+psycopg://repopilot:secret@postgres:5432/repopilot",
            database_name='bad-name";DROP DATABASE repopilot;--',
        )


def test_verify_migrations_runs_upgrade_downgrade_upgrade_and_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []
    target = migration_verifier.MigrationVerificationTarget(
        admin_url="postgresql+psycopg://repopilot:secret@postgres:5432/postgres",
        migration_url="postgresql+psycopg://repopilot:secret@postgres:5432/repopilot_migration_verify_test",
        database_name="repopilot_migration_verify_test",
    )

    monkeypatch.setattr(migration_verifier, "create_database", lambda passed_target: calls.append(("create", passed_target.database_name)))
    monkeypatch.setattr(migration_verifier, "drop_database", lambda passed_target: calls.append(("drop", passed_target.database_name)))

    def fake_run_alembic(api_dir: Path, migration_url: str, command: str, revision: str) -> None:
        assert api_dir == Path("/tmp/api")
        assert migration_url == target.migration_url
        calls.append((command, revision))

    monkeypatch.setattr(migration_verifier, "run_alembic", fake_run_alembic)

    migration_verifier.verify_migrations(target, api_dir=Path("/tmp/api"))

    assert calls == [
        ("create", "repopilot_migration_verify_test"),
        ("upgrade", "head"),
        ("downgrade", "base"),
        ("upgrade", "head"),
        ("drop", "repopilot_migration_verify_test"),
    ]


def test_verify_migrations_can_keep_database(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    target = migration_verifier.MigrationVerificationTarget(
        admin_url="postgresql+psycopg://repopilot:secret@postgres:5432/postgres",
        migration_url="postgresql+psycopg://repopilot:secret@postgres:5432/repopilot_migration_verify_test",
        database_name="repopilot_migration_verify_test",
    )

    monkeypatch.setattr(migration_verifier, "create_database", lambda passed_target: calls.append("create"))
    monkeypatch.setattr(migration_verifier, "drop_database", lambda passed_target: calls.append("drop"))
    monkeypatch.setattr(migration_verifier, "run_alembic", lambda *args, **kwargs: calls.append("alembic"))

    migration_verifier.verify_migrations(target, api_dir=Path("/tmp/api"), keep_database=True)

    assert calls == ["create", "alembic", "alembic", "alembic"]
