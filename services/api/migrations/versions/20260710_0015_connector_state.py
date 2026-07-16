"""add durable connector cursor, lease, and health state

Revision ID: 20260710_0015
Revises: 20260710_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0015"
down_revision: str | None = "20260710_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connector_cursors",
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_status", sa.String(length=40), nullable=False),
        sa.Column("retry_attempt", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("deleted_count", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actionable_failure", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["target_id"], ["connector_targets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.PrimaryKeyConstraint("target_id"),
    )
    op.create_index("ix_connector_cursors_project_id", "connector_cursors", ["project_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_semantic_edges_source_adjacency ON semantic_edges(project_id, source_node_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_semantic_edges_target_adjacency ON semantic_edges(project_id, target_node_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_graph_layout_positions_node ON graph_layout_positions(node_id, layout_id)")


def downgrade() -> None:
    op.drop_index("ix_connector_cursors_project_id", table_name="connector_cursors")
    op.drop_table("connector_cursors")
