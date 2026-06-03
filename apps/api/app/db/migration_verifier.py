from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.config import settings


DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


@dataclass(frozen=True)
class MigrationVerificationTarget:
    admin_url: str
    migration_url: str
    database_name: str


def default_database_url() -> str:
    if settings.alembic_database_url:
        return settings.alembic_database_url
    return settings.database_url.replace("+asyncpg", "+psycopg")


def psycopg_url(url: URL) -> URL:
    if not url.drivername.startswith("postgresql"):
        msg = f"Migration verification requires PostgreSQL, got {url.drivername!r}"
        raise ValueError(msg)
    return url.set(drivername="postgresql+psycopg")


def validate_database_name(database_name: str) -> str:
    if not DATABASE_NAME_PATTERN.fullmatch(database_name):
        msg = (
            "Temporary database name must start with a letter or underscore and "
            "contain only letters, numbers, and underscores."
        )
        raise ValueError(msg)
    return database_name


def build_target(
    database_url: str,
    *,
    database_name: str | None = None,
    admin_database: str = "postgres",
) -> MigrationVerificationTarget:
    base_url = psycopg_url(make_url(database_url))
    temp_database = validate_database_name(database_name or f"repopilot_migration_verify_{uuid.uuid4().hex[:12]}")
    admin_url = base_url.set(database=admin_database)
    migration_url = base_url.set(database=temp_database)
    return MigrationVerificationTarget(
        admin_url=admin_url.render_as_string(hide_password=False),
        migration_url=migration_url.render_as_string(hide_password=False),
        database_name=temp_database,
    )


def quoted_database_name(database_name: str) -> str:
    validate_database_name(database_name)
    return f'"{database_name}"'


def create_database(target: MigrationVerificationTarget) -> None:
    engine = create_engine(target.admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {quoted_database_name(target.database_name)}"))
    finally:
        engine.dispose()


def drop_database(target: MigrationVerificationTarget) -> None:
    engine = create_engine(target.admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": target.database_name},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {quoted_database_name(target.database_name)}"))
    finally:
        engine.dispose()


def run_alembic(api_dir: Path, migration_url: str, command: str, revision: str) -> None:
    env = os.environ.copy()
    env["ALEMBIC_DATABASE_URL"] = migration_url
    subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=api_dir,
        env=env,
        check=True,
    )


def verify_migrations(
    target: MigrationVerificationTarget,
    *,
    api_dir: Path,
    keep_database: bool = False,
) -> None:
    created = False
    try:
        create_database(target)
        created = True
        run_alembic(api_dir, target.migration_url, "upgrade", "head")
        run_alembic(api_dir, target.migration_url, "downgrade", "base")
        run_alembic(api_dir, target.migration_url, "upgrade", "head")
    finally:
        if created and not keep_database:
            drop_database(target)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Alembic migrations against a fresh temporary PostgreSQL database.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("REPOPILOT_MIGRATION_VERIFY_DATABASE_URL") or default_database_url(),
        help="PostgreSQL URL used as the template for admin and temporary migration database URLs.",
    )
    parser.add_argument(
        "--database-name",
        help="Optional temporary database name. Defaults to a generated repopilot_migration_verify_<suffix> name.",
    )
    parser.add_argument(
        "--admin-database",
        default=os.getenv("REPOPILOT_MIGRATION_VERIFY_ADMIN_DATABASE", "postgres"),
        help="Existing database used to create/drop the temporary database.",
    )
    parser.add_argument(
        "--api-dir",
        default=str(Path(__file__).resolve().parents[2]),
        help="Path containing alembic.ini.",
    )
    parser.add_argument(
        "--keep-database",
        action="store_true",
        help="Keep the temporary database after verification for debugging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    target = build_target(args.database_url, database_name=args.database_name, admin_database=args.admin_database)
    api_dir = Path(args.api_dir).resolve()
    print(f"Creating temporary migration database {target.database_name}")
    try:
        verify_migrations(target, api_dir=api_dir, keep_database=args.keep_database)
    except Exception:
        print(f"Migration verification failed for {target.database_name}", file=sys.stderr)
        raise
    print("Migration verification passed: upgrade head -> downgrade base -> upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
