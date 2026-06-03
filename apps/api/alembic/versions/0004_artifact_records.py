"""artifact storage records

Revision ID: 0004_artifact_records
Revises: 0003_plan_run_link
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_artifact_records"
down_revision = "0003_plan_run_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("artifact_type", sa.String(length=128), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("storage_backend", sa.String(length=64), nullable=False, server_default="local"),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False, server_default="application/octet-stream"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_artifact_records_run_type", "artifact_records", ["run_id", "artifact_type"])
    op.create_index("ix_artifact_records_sha256", "artifact_records", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_artifact_records_sha256", table_name="artifact_records")
    op.drop_index("ix_artifact_records_run_type", table_name="artifact_records")
    op.drop_table("artifact_records")
