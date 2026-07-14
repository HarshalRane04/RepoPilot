"""preserve artifact provenance after local retention

Revision ID: 0011_artifact_tombstones
Revises: 0010_vector_retrieval_index
Create Date: 2026-07-11 01:30:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0011_artifact_tombstones"
down_revision = "0010_vector_retrieval_index"
branch_labels = None
depends_on = None

__all__ = ["branch_labels", "depends_on", "downgrade", "down_revision", "revision", "upgrade"]


def upgrade() -> None:
    op.add_column("artifact_records", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_artifact_records_run_deleted", "artifact_records", ["run_id", "deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_artifact_records_run_deleted", table_name="artifact_records")
    op.drop_column("artifact_records", "deleted_at")
