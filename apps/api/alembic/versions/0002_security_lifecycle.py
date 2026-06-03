"""phase 6 validation evidence and security lifecycle

Revision ID: 0002_security_lifecycle
Revises: 0001_core_schema
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_security_lifecycle"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("validation_results", sa.Column("evidence_hash", sa.String(length=128), nullable=True))
    op.add_column("security_findings", sa.Column("status_reason", sa.Text(), nullable=True))
    op.add_column("security_findings", sa.Column("status_actor", sa.String(length=255), nullable=True))
    op.add_column("security_findings", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_plans_issue_id", "plans", ["issue_id"])
    op.create_index("ix_pull_requests_pr_number", "pull_requests", ["pr_number"])
    op.create_index("ix_security_findings_run_severity", "security_findings", ["run_id", "severity"])
    op.create_index("ix_llm_traces_agent_run_id", "llm_traces", ["agent_run_id"])
    op.create_index("ix_eval_runs_created_at", "eval_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_eval_runs_created_at", table_name="eval_runs")
    op.drop_index("ix_llm_traces_agent_run_id", table_name="llm_traces")
    op.drop_index("ix_security_findings_run_severity", table_name="security_findings")
    op.drop_index("ix_pull_requests_pr_number", table_name="pull_requests")
    op.drop_index("ix_plans_issue_id", table_name="plans")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")

    op.drop_column("security_findings", "status_changed_at")
    op.drop_column("security_findings", "status_actor")
    op.drop_column("security_findings", "status_reason")
    op.drop_column("validation_results", "evidence_hash")
