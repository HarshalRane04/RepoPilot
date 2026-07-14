"""add durable webhook retry metadata

Revision ID: 0009_durable_webhook_delivery
Revises: 0008_evidence_provenance
Create Date: 2026-07-11 00:30:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0009_durable_webhook_delivery"
down_revision = "0008_evidence_provenance"
branch_labels = None
depends_on = None

__all__ = ["branch_labels", "depends_on", "downgrade", "down_revision", "revision", "upgrade"]


def upgrade() -> None:
    op.add_column(
        "github_events",
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("github_events", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("github_events", sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("github_events", sa.Column("last_error", sa.Text(), nullable=True))
    op.drop_index("ix_github_events_status_received", table_name="github_events")
    op.create_index(
        "ix_github_events_status_retry",
        "github_events",
        ["status", "next_retry_at", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_github_events_status_retry", table_name="github_events")
    op.create_index("ix_github_events_status_received", "github_events", ["status", "received_at"])
    op.drop_column("github_events", "last_error")
    op.drop_column("github_events", "enqueued_at")
    op.drop_column("github_events", "next_retry_at")
    op.drop_column("github_events", "retry_count")
