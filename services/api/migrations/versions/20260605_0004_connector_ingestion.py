"""Connector ingestion records.

Revision ID: 20260605_0004
Revises: 20260604_0003
Create Date: 2026-06-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260605_0004"
down_revision: str | None = "20260604_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_topic_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_topics_project_id", "topics", ["project_id"])

    op.create_table(
        "graph_settings",
        sa.Column("project_id", sa.String(length=64), primary_key=True),
        sa.Column("llm_enabled", sa.Boolean(), nullable=False),
        sa.Column("llm_provider", sa.String(length=80), nullable=True),
        sa.Column("llm_model", sa.String(length=160), nullable=True),
        sa.Column("auto_commit_threshold", sa.Float(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )

    op.create_table(
        "connector_accounts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("encrypted_token_json", sa.Text(), nullable=True),
        sa.Column("scopes_json", sa.Text(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_connector_accounts_project_id", "connector_accounts", ["project_id"])

    op.create_table(
        "connector_targets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("connector_kind", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("remote_id", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("parent_remote_id", sa.Text(), nullable=True),
        sa.Column("sync_settings_json", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["connector_accounts.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_connector_targets_account_id", "connector_targets", ["account_id"])
    op.create_index("ix_connector_targets_project_id", "connector_targets", ["project_id"])

    op.add_column("sources", sa.Column("connector_kind", sa.String(length=40), nullable=True))
    op.add_column("sources", sa.Column("remote_id", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("remote_parent_id", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("remote_modified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("remote_url", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("stale_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "connector_sync_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("proposal_count", sa.Integer(), nullable=False),
        sa.Column("auto_committed_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["connector_targets.id"]),
    )
    op.create_index("ix_connector_sync_runs_project_id", "connector_sync_runs", ["project_id"])
    op.create_index("ix_connector_sync_runs_target_id", "connector_sync_runs", ["target_id"])

    op.create_table(
        "source_chunks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("parent_chunk_id", sa.String(length=64), nullable=True),
        sa.Column("heading_path_json", sa.Text(), nullable=False),
        sa.Column("block_type", sa.String(length=80), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("links_json", sa.Text(), nullable=False),
        sa.Column("mentions_json", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_chunk_id"], ["source_chunks.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
    )
    op.create_index("ix_source_chunks_project_id", "source_chunks", ["project_id"])
    op.create_index("ix_source_chunks_source_id", "source_chunks", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_source_chunks_source_id", table_name="source_chunks")
    op.drop_index("ix_source_chunks_project_id", table_name="source_chunks")
    op.drop_table("source_chunks")
    op.drop_index("ix_connector_sync_runs_target_id", table_name="connector_sync_runs")
    op.drop_index("ix_connector_sync_runs_project_id", table_name="connector_sync_runs")
    op.drop_table("connector_sync_runs")
    for column_name in [
        "stale_at",
        "metadata_json",
        "remote_url",
        "remote_modified_at",
        "remote_parent_id",
        "remote_id",
        "connector_kind",
    ]:
        op.drop_column("sources", column_name)
    op.drop_index("ix_connector_targets_project_id", table_name="connector_targets")
    op.drop_index("ix_connector_targets_account_id", table_name="connector_targets")
    op.drop_table("connector_targets")
    op.drop_index("ix_connector_accounts_project_id", table_name="connector_accounts")
    op.drop_table("connector_accounts")
    op.drop_table("graph_settings")
    op.drop_index("ix_topics_project_id", table_name="topics")
    op.drop_table("topics")
