"""add resumable upload sessions and object-store part state

Revision ID: 20260710_0016
Revises: 20260710_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0016"
down_revision: str | None = "20260710_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("storage_upload_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=240), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("graph_id", sa.String(length=160), nullable=True),
        sa.Column("expected_bytes", sa.Integer(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_upload_sessions_project_id", "upload_sessions", ["project_id"])
    op.create_table(
        "upload_parts",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column("offset_bytes", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["upload_sessions.id"]),
        sa.PrimaryKeyConstraint("session_id", "part_number"),
    )


def downgrade() -> None:
    op.drop_table("upload_parts")
    op.drop_index("ix_upload_sessions_project_id", table_name="upload_sessions")
    op.drop_table("upload_sessions")
