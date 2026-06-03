"""canonical plan run link

Revision ID: 0003_plan_run_link
Revises: 0002_security_lifecycle
Create Date: 2026-05-31 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_plan_run_link"
down_revision = "0002_security_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("plans_agent_run_id_fkey", "plans", type_="foreignkey")
    op.drop_column("plans", "agent_run_id")
    op.create_index("ix_agent_runs_plan_id", "agent_runs", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_plan_id", table_name="agent_runs")
    op.add_column("plans", sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "plans_agent_run_id_fkey",
        "plans",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
