"""Add persisted graph activity events.

Revision ID: 20260605_0008
Revises: 20260605_0007
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260605_0008"
down_revision: str | None = "20260605_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "graph_activity_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("object_refs_json", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("lenses_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index(
        "ix_graph_activity_events_project_created",
        "graph_activity_events",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_graph_activity_events_project_event_type",
        "graph_activity_events",
        ["project_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_graph_activity_events_project_event_type", table_name="graph_activity_events")
    op.drop_index("ix_graph_activity_events_project_created", table_name="graph_activity_events")
    op.drop_table("graph_activity_events")
