"""add lens metadata to reviewed graph items

Revision ID: 20260605_0005
Revises: 20260605_0004
Create Date: 2026-06-05 00:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260605_0005"
down_revision = "20260605_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_nodes", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column("semantic_edges", sa.Column("metadata_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("semantic_edges", "metadata_json")
    op.drop_column("content_nodes", "metadata_json")
