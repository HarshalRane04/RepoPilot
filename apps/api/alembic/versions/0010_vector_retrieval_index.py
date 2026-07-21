"""add bounded vector retrieval index

Revision ID: 0010_vector_retrieval_index
Revises: 0009_durable_webhook_delivery
Create Date: 2026-07-11 01:00:00.000000
"""

from alembic import op


revision = "0010_vector_retrieval_index"
down_revision = "0009_durable_webhook_delivery"
branch_labels = None
depends_on = None

__all__ = ["branch_labels", "depends_on", "downgrade", "down_revision", "revision", "upgrade"]


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_code_chunks_embedding_hnsw "
        "ON code_chunks USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_code_chunks_embedding_hnsw")
