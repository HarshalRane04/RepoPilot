"""repository index metadata

Revision ID: 0005_repository_index_metadata
Revises: 0004_artifact_records
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_repository_index_metadata"
down_revision = "0004_artifact_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repository_indexes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("files_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False, server_default="mock"),
        sa.Column("embedding_model", sa.String(length=255), nullable=False, server_default="mock-embedding"),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False, server_default="1536"),
        sa.Column("chunker_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="ready"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_repository_indexes_repo_created", "repository_indexes", ["repository_id", "created_at"])
    op.create_index("ix_repository_indexes_repo_commit", "repository_indexes", ["repository_id", "commit_sha"])


def downgrade() -> None:
    op.drop_index("ix_repository_indexes_repo_commit", table_name="repository_indexes")
    op.drop_index("ix_repository_indexes_repo_created", table_name="repository_indexes")
    op.drop_table("repository_indexes")
