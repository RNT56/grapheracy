"""add active agent context connector tables

Revision ID: 20260614_0010
Revises: 20260606_0009
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260614_0010"
down_revision: str | None = "20260606_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_context_clients",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("runtime_kind", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("scopes_json", sa.Text(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index(
        "ix_agent_context_clients_project_runtime",
        "agent_context_clients",
        ["project_id", "runtime_kind"],
    )
    op.create_index(op.f("ix_agent_context_clients_project_id"), "agent_context_clients", ["project_id"])

    op.create_table(
        "agent_context_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("runtime_kind", sa.String(length=80), nullable=False),
        sa.Column("authority", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("workspace_root", sa.Text(), nullable=True),
        sa.Column("repository_uri", sa.Text(), nullable=True),
        sa.Column("branch", sa.String(length=240), nullable=True),
        sa.Column("commit_sha", sa.String(length=80), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["agent_context_clients.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_agent_context_sessions_client_started", "agent_context_sessions", ["client_id", "started_at"])
    op.create_index("ix_agent_context_sessions_project_updated", "agent_context_sessions", ["project_id", "updated_at"])
    op.create_index(op.f("ix_agent_context_sessions_client_id"), "agent_context_sessions", ["client_id"])
    op.create_index(op.f("ix_agent_context_sessions_project_id"), "agent_context_sessions", ["project_id"])

    op.create_table(
        "agent_context_artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["agent_context_sessions.id"]),
    )
    op.create_index("ix_agent_context_artifacts_session_kind", "agent_context_artifacts", ["session_id", "kind"])
    op.create_index(op.f("ix_agent_context_artifacts_project_id"), "agent_context_artifacts", ["project_id"])
    op.create_index(op.f("ix_agent_context_artifacts_session_id"), "agent_context_artifacts", ["session_id"])

    op.create_table(
        "agent_context_blobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.String(length=64), nullable=True),
        sa.Column("content_kind", sa.String(length=40), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("redaction_status", sa.String(length=40), nullable=False),
        sa.Column("encryption_status", sa.String(length=40), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("encrypted_content", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["agent_context_artifacts.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["agent_context_sessions.id"]),
    )
    op.create_index("ix_agent_context_blobs_project_expires", "agent_context_blobs", ["project_id", "expires_at"])
    op.create_index(op.f("ix_agent_context_blobs_artifact_id"), "agent_context_blobs", ["artifact_id"])
    op.create_index(op.f("ix_agent_context_blobs_project_id"), "agent_context_blobs", ["project_id"])
    op.create_index(op.f("ix_agent_context_blobs_session_id"), "agent_context_blobs", ["session_id"])

    op.create_table(
        "agent_context_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("client_event_id", sa.String(length=160), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(length=80), nullable=False),
        sa.Column("authority", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("artifact_id", sa.String(length=64), nullable=True),
        sa.Column("blob_id", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("object_refs_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["agent_context_artifacts.id"]),
        sa.ForeignKeyConstraint(["blob_id"], ["agent_context_blobs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["agent_context_sessions.id"]),
        sa.UniqueConstraint("session_id", "client_event_id", name="uq_agent_context_events_session_client_event"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_context_events_session_sequence"),
    )
    op.create_index("ix_agent_context_events_project_received", "agent_context_events", ["project_id", "received_at"])
    op.create_index("ix_agent_context_events_session_sequence", "agent_context_events", ["session_id", "sequence"])
    op.create_index(op.f("ix_agent_context_events_artifact_id"), "agent_context_events", ["artifact_id"])
    op.create_index(op.f("ix_agent_context_events_blob_id"), "agent_context_events", ["blob_id"])
    op.create_index(op.f("ix_agent_context_events_project_id"), "agent_context_events", ["project_id"])
    op.create_index(op.f("ix_agent_context_events_session_id"), "agent_context_events", ["session_id"])


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_agent_context_events_session_id", "agent_context_events"),
        ("ix_agent_context_events_project_id", "agent_context_events"),
        ("ix_agent_context_events_blob_id", "agent_context_events"),
        ("ix_agent_context_events_artifact_id", "agent_context_events"),
        ("ix_agent_context_events_session_sequence", "agent_context_events"),
        ("ix_agent_context_events_project_received", "agent_context_events"),
        ("ix_agent_context_blobs_session_id", "agent_context_blobs"),
        ("ix_agent_context_blobs_project_id", "agent_context_blobs"),
        ("ix_agent_context_blobs_artifact_id", "agent_context_blobs"),
        ("ix_agent_context_blobs_project_expires", "agent_context_blobs"),
        ("ix_agent_context_artifacts_session_id", "agent_context_artifacts"),
        ("ix_agent_context_artifacts_project_id", "agent_context_artifacts"),
        ("ix_agent_context_artifacts_session_kind", "agent_context_artifacts"),
        ("ix_agent_context_sessions_project_id", "agent_context_sessions"),
        ("ix_agent_context_sessions_client_id", "agent_context_sessions"),
        ("ix_agent_context_sessions_project_updated", "agent_context_sessions"),
        ("ix_agent_context_sessions_client_started", "agent_context_sessions"),
        ("ix_agent_context_clients_project_id", "agent_context_clients"),
        ("ix_agent_context_clients_project_runtime", "agent_context_clients"),
    ]:
        op.drop_index(index_name, table_name=table_name)
    for table_name in [
        "agent_context_events",
        "agent_context_blobs",
        "agent_context_artifacts",
        "agent_context_sessions",
        "agent_context_clients",
    ]:
        op.drop_table(table_name)
