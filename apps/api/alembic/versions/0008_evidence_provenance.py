"""bind workflow evidence to repositories and patch generations

Revision ID: 0008_evidence_provenance
Revises: 0007_issue_body_text
Create Date: 2026-07-11 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0008_evidence_provenance"
down_revision = "0007_issue_body_text"
branch_labels = None
depends_on = None

__all__ = ["branch_labels", "depends_on", "downgrade", "down_revision", "revision", "upgrade"]


def upgrade() -> None:
    op.add_column("pull_requests", sa.Column("repository_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_pull_requests_repository_id_repositories",
        "pull_requests",
        "repositories",
        ["repository_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        sa.text(
            """
            UPDATE pull_requests AS pr
            SET repository_id = issues.repository_id
            FROM agent_runs AS runs, issues
            WHERE pr.run_id = runs.id
              AND runs.issue_id = issues.id
              AND pr.repository_id IS NULL
            """
        )
    )
    op.create_unique_constraint(
        "uq_pull_requests_repository_number",
        "pull_requests",
        ["repository_id", "pr_number"],
    )
    op.add_column("validation_results", sa.Column("patch_hash", sa.String(length=64), nullable=True))
    op.add_column("validation_results", sa.Column("sandbox_backend", sa.String(length=64), nullable=True))
    op.add_column(
        "validation_results",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "security_findings",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("security_findings", sa.Column("patch_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_validation_results_run_patch_status",
        "validation_results",
        ["run_id", "patch_hash", "status"],
    )
    op.create_index(
        "ix_security_findings_run_patch_status",
        "security_findings",
        ["run_id", "patch_hash", "status"],
    )
    op.create_index("ix_agent_runs_issue_started", "agent_runs", ["issue_id", "started_at"])
    op.create_index("ix_agent_steps_run_created", "agent_steps", ["run_id", "created_at"])
    op.create_index("ix_audit_logs_entity_created", "audit_logs", ["entity_id", "created_at"])
    op.create_index("ix_github_events_status_received", "github_events", ["status", "received_at"])


def downgrade() -> None:
    op.drop_index("ix_github_events_status_received", table_name="github_events")
    op.drop_index("ix_audit_logs_entity_created", table_name="audit_logs")
    op.drop_index("ix_agent_steps_run_created", table_name="agent_steps")
    op.drop_index("ix_agent_runs_issue_started", table_name="agent_runs")
    op.drop_index("ix_security_findings_run_patch_status", table_name="security_findings")
    op.drop_index("ix_validation_results_run_patch_status", table_name="validation_results")
    op.drop_column("security_findings", "patch_hash")
    op.drop_column("security_findings", "created_at")
    op.drop_column("validation_results", "created_at")
    op.drop_column("validation_results", "sandbox_backend")
    op.drop_column("validation_results", "patch_hash")
    op.drop_constraint("uq_pull_requests_repository_number", "pull_requests", type_="unique")
    op.drop_constraint("fk_pull_requests_repository_id_repositories", "pull_requests", type_="foreignkey")
    op.drop_column("pull_requests", "repository_id")
