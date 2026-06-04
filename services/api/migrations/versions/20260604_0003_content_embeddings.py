"""Content embedding records.

Revision ID: 20260604_0003
Revises: 20260604_0002
Create Date: 2026-06-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260604_0003"
down_revision: str | None = "20260604_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_embeddings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=True),
        sa.Column("content_node_id", sa.String(length=64), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("vector_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_node_id"], ["content_nodes.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["extraction_proposals.id"]),
    )
    op.create_index("ix_content_embeddings_content_node_id", "content_embeddings", ["content_node_id"])
    op.create_index("ix_content_embeddings_project_id", "content_embeddings", ["project_id"])
    op.create_index("ix_content_embeddings_proposal_id", "content_embeddings", ["proposal_id"])


def downgrade() -> None:
    op.drop_index("ix_content_embeddings_proposal_id", table_name="content_embeddings")
    op.drop_index("ix_content_embeddings_project_id", table_name="content_embeddings")
    op.drop_index("ix_content_embeddings_content_node_id", table_name="content_embeddings")
    op.drop_table("content_embeddings")
