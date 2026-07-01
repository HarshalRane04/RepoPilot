"""store bounded issue body text

Revision ID: 0007_issue_body_text
Revises: 0006_llm_trace_metadata
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_issue_body_text"
down_revision: str | None = "0006_llm_trace_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("issues", sa.Column("body_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("issues", "body_text")
