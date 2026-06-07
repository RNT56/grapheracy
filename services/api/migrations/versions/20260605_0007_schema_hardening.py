"""Harden schema idempotency constraints and agent runtime indexes.

Revision ID: 20260605_0007
Revises: 20260605_0006
Create Date: 2026-06-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260605_0007"
down_revision: str | None = "20260605_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_sources_project_connector_remote",
        "sources",
        ["project_id", "connector_kind", "remote_id"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_source_chunks_source_ordinal",
        "source_chunks",
        ["source_id", "ordinal"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_semantic_edges_project_triplet",
        "semantic_edges",
        ["project_id", "source_node_id", "target_node_id", "relation"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_content_embeddings_proposal_model",
        "content_embeddings",
        ["proposal_id", "embedding_model"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_graph_build_specs_session_version",
        "graph_build_specs",
        ["session_id", "version"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_research_tasks_project_idempotency_key",
        "research_tasks",
        ["project_id", "idempotency_key"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    for index_name, table_name in [
        ("uq_research_tasks_project_idempotency_key", "research_tasks"),
        ("uq_graph_build_specs_session_version", "graph_build_specs"),
        ("uq_content_embeddings_proposal_model", "content_embeddings"),
        ("uq_semantic_edges_project_triplet", "semantic_edges"),
        ("uq_source_chunks_source_ordinal", "source_chunks"),
        ("uq_sources_project_connector_remote", "sources"),
    ]:
        op.drop_index(index_name, table_name=table_name, if_exists=True)
