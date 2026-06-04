"""Core graph workflow tables.

Revision ID: 20260604_0002
Revises: 20260604_0001
Create Date: 2026-06-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260604_0002"
down_revision: str | None = "20260604_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_nodes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("topic_ids_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_content_nodes_project_id", "content_nodes", ["project_id"])

    op.create_table(
        "semantic_edges",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_node_id", sa.String(length=64), nullable=False),
        sa.Column("target_node_id", sa.String(length=64), nullable=False),
        sa.Column("relation", sa.String(length=40), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["source_node_id"], ["content_nodes.id"]),
        sa.ForeignKeyConstraint(["target_node_id"], ["content_nodes.id"]),
    )
    op.create_index("ix_semantic_edges_project_id", "semantic_edges", ["project_id"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
    )
    op.create_index("ix_ingestion_runs_project_id", "ingestion_runs", ["project_id"])

    op.create_table(
        "extraction_proposals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("proposed_value_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["ingestion_runs.id"]),
    )
    op.create_index("ix_extraction_proposals_project_id", "extraction_proposals", ["project_id"])

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("reviewer_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("edited_value_json", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["extraction_proposals.id"]),
    )
    op.create_index("ix_review_decisions_project_id", "review_decisions", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_review_decisions_project_id", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index("ix_extraction_proposals_project_id", table_name="extraction_proposals")
    op.drop_table("extraction_proposals")
    op.drop_index("ix_ingestion_runs_project_id", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index("ix_semantic_edges_project_id", table_name="semantic_edges")
    op.drop_table("semantic_edges")
    op.drop_index("ix_content_nodes_project_id", table_name="content_nodes")
    op.drop_table("content_nodes")
