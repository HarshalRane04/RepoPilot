"""llm trace metadata

Revision ID: 0006_llm_trace_metadata
Revises: 0005_repository_index_metadata
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_llm_trace_metadata"
down_revision = "0005_repository_index_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_traces", sa.Column("response_hash", sa.String(length=128), nullable=True))
    op.add_column("llm_traces", sa.Column("provider", sa.String(length=64), nullable=False, server_default="unknown"))
    op.add_column("llm_traces", sa.Column("mode", sa.String(length=64), nullable=False, server_default="unknown"))
    op.add_column("llm_traces", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_index("ix_llm_traces_provider_mode_created", "llm_traces", ["provider", "mode", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_traces_provider_mode_created", table_name="llm_traces")
    op.drop_column("llm_traces", "metadata_json")
    op.drop_column("llm_traces", "mode")
    op.drop_column("llm_traces", "provider")
    op.drop_column("llm_traces", "response_hash")
