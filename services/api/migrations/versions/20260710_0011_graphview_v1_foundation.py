"""add Graphview 1.0 projection, layout, job, outbox, and audit tables

Revision ID: 20260710_0011
Revises: 20260614_0010
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0011"
down_revision: str | None = "20260614_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_context_blobs", sa.Column("object_key", sa.Text(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.add_column("content_embeddings", sa.Column("vector_native", Vector(16), nullable=True))
        op.execute("UPDATE content_embeddings SET vector_native = vector_json::vector WHERE vector_json IS NOT NULL")
        op.execute("CREATE INDEX ix_content_embeddings_vector_hnsw ON content_embeddings USING hnsw (vector_native vector_cosine_ops)")
        op.execute("CREATE INDEX ix_content_nodes_search_gin ON content_nodes USING gin (to_tsvector('english', coalesce(label, '') || ' ' || coalesce(summary, '')))")
        op.execute("CREATE INDEX ix_sources_search_gin ON sources USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(uri, '')))")
        op.execute("""
            CREATE FUNCTION graphview_sync_vector_native() RETURNS trigger AS $$
            BEGIN NEW.vector_native := NEW.vector_json::vector; RETURN NEW; END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("CREATE TRIGGER graphview_content_embeddings_vector BEFORE INSERT OR UPDATE OF vector_json ON content_embeddings FOR EACH ROW EXECUTE FUNCTION graphview_sync_vector_native()")
    else:
        op.add_column("content_embeddings", sa.Column("vector_native", sa.Text(), nullable=True))
    op.create_table(
        "graph_versions",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.execute("""
        INSERT INTO graph_versions(project_id, version, node_count, edge_count, updated_at)
        SELECT p.id, 1,
          (SELECT count(*) FROM content_nodes n WHERE n.project_id = p.id),
          (SELECT count(*) FROM semantic_edges e WHERE e.project_id = p.id),
          CURRENT_TIMESTAMP
        FROM graph_projects p
    """)
    op.create_table(
        "graph_layouts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("algorithm", sa.String(length=80), nullable=False),
        sa.Column("graph_version", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.UniqueConstraint("project_id", "name", name="uq_graph_layouts_project_name"),
    )
    op.create_index("ix_graph_layouts_project_id", "graph_layouts", ["project_id"])
    op.create_table(
        "graph_layout_positions",
        sa.Column("layout_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("z", sa.Float(), nullable=True),
        sa.Column("cluster_key", sa.String(length=160), nullable=True),
        sa.ForeignKeyConstraint(["layout_id"], ["graph_layouts.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["content_nodes.id"]),
        sa.PrimaryKeyConstraint("layout_id", "node_id"),
    )
    op.create_index("ix_graph_layout_positions_xy", "graph_layout_positions", ["layout_id", "x", "y"])
    op.create_index("ix_graph_layout_positions_node", "graph_layout_positions", ["node_id", "layout_id"])
    op.create_table(
        "durable_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("queue", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=160), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_durable_jobs_project_idempotency"),
    )
    op.create_index("ix_durable_jobs_project_id", "durable_jobs", ["project_id"])
    op.create_index("ix_durable_jobs_dispatch", "durable_jobs", ["queue", "status", "available_at"])
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_event_outbox_project_id", "event_outbox", ["project_id"])
    op.create_index("ix_event_outbox_dispatch", "event_outbox", ["status", "available_at"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_audit_events_project_id", "audit_events", ["project_id"])
    op.create_index("ix_audit_events_project_occurred", "audit_events", ["project_id", "occurred_at"])
    op.create_index("ix_semantic_edges_source_adjacency", "semantic_edges", ["project_id", "source_node_id"])
    op.create_index("ix_semantic_edges_target_adjacency", "semantic_edges", ["project_id", "target_node_id"])
    if bind.dialect.name == "postgresql":
        op.execute("""
          CREATE FUNCTION graphview_nodes_inserted() RETURNS trigger AS $$ BEGIN
            INSERT INTO graph_versions(project_id,version,node_count,edge_count,updated_at)
            SELECT project_id,1,count(*),0,now() FROM new_nodes GROUP BY project_id
            ON CONFLICT(project_id) DO UPDATE SET version=graph_versions.version+1,node_count=graph_versions.node_count+excluded.node_count,updated_at=now();
            RETURN NULL; END $$ LANGUAGE plpgsql;
          CREATE TRIGGER graphview_nodes_insert AFTER INSERT ON content_nodes REFERENCING NEW TABLE AS new_nodes FOR EACH STATEMENT EXECUTE FUNCTION graphview_nodes_inserted();
          CREATE FUNCTION graphview_nodes_deleted() RETURNS trigger AS $$ BEGIN
            INSERT INTO graph_versions(project_id,version,node_count,edge_count,updated_at)
            SELECT project_id,1,0,0,now() FROM old_nodes GROUP BY project_id
            ON CONFLICT(project_id) DO UPDATE SET version=graph_versions.version+1,node_count=greatest(0,graph_versions.node_count-(SELECT count(*) FROM old_nodes WHERE project_id=excluded.project_id)),updated_at=now();
            RETURN NULL; END $$ LANGUAGE plpgsql;
          CREATE TRIGGER graphview_nodes_delete AFTER DELETE ON content_nodes REFERENCING OLD TABLE AS old_nodes FOR EACH STATEMENT EXECUTE FUNCTION graphview_nodes_deleted();
          CREATE FUNCTION graphview_edges_inserted() RETURNS trigger AS $$ BEGIN
            INSERT INTO graph_versions(project_id,version,node_count,edge_count,updated_at)
            SELECT project_id,1,0,count(*),now() FROM new_edges GROUP BY project_id
            ON CONFLICT(project_id) DO UPDATE SET version=graph_versions.version+1,edge_count=graph_versions.edge_count+excluded.edge_count,updated_at=now();
            RETURN NULL; END $$ LANGUAGE plpgsql;
          CREATE TRIGGER graphview_edges_insert AFTER INSERT ON semantic_edges REFERENCING NEW TABLE AS new_edges FOR EACH STATEMENT EXECUTE FUNCTION graphview_edges_inserted();
          CREATE FUNCTION graphview_edges_deleted() RETURNS trigger AS $$ BEGIN
            INSERT INTO graph_versions(project_id,version,node_count,edge_count,updated_at)
            SELECT project_id,1,0,0,now() FROM old_edges GROUP BY project_id
            ON CONFLICT(project_id) DO UPDATE SET version=graph_versions.version+1,edge_count=greatest(0,graph_versions.edge_count-(SELECT count(*) FROM old_edges WHERE project_id=excluded.project_id)),updated_at=now();
            RETURN NULL; END $$ LANGUAGE plpgsql;
          CREATE TRIGGER graphview_edges_delete AFTER DELETE ON semantic_edges REFERENCING OLD TABLE AS old_edges FOR EACH STATEMENT EXECUTE FUNCTION graphview_edges_deleted();
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS graphview_edges_delete ON semantic_edges; DROP FUNCTION IF EXISTS graphview_edges_deleted; DROP TRIGGER IF EXISTS graphview_edges_insert ON semantic_edges; DROP FUNCTION IF EXISTS graphview_edges_inserted; DROP TRIGGER IF EXISTS graphview_nodes_delete ON content_nodes; DROP FUNCTION IF EXISTS graphview_nodes_deleted; DROP TRIGGER IF EXISTS graphview_nodes_insert ON content_nodes; DROP FUNCTION IF EXISTS graphview_nodes_inserted")
        op.execute("DROP TRIGGER IF EXISTS graphview_content_embeddings_vector ON content_embeddings")
        op.execute("DROP FUNCTION IF EXISTS graphview_sync_vector_native")
        op.execute("DROP INDEX IF EXISTS ix_sources_search_gin")
        op.execute("DROP INDEX IF EXISTS ix_content_nodes_search_gin")
        op.execute("DROP INDEX IF EXISTS ix_content_embeddings_vector_hnsw")
    op.drop_column("content_embeddings", "vector_native")
    for index_name, table_name in [
        ("ix_audit_events_project_occurred", "audit_events"),
        ("ix_audit_events_project_id", "audit_events"),
        ("ix_event_outbox_dispatch", "event_outbox"),
        ("ix_event_outbox_project_id", "event_outbox"),
        ("ix_durable_jobs_dispatch", "durable_jobs"),
        ("ix_durable_jobs_project_id", "durable_jobs"),
        ("ix_graph_layout_positions_xy", "graph_layout_positions"),
        ("ix_graph_layout_positions_node", "graph_layout_positions"),
        ("ix_semantic_edges_source_adjacency", "semantic_edges"),
        ("ix_semantic_edges_target_adjacency", "semantic_edges"),
        ("ix_graph_layouts_project_id", "graph_layouts"),
    ]:
        op.drop_index(index_name, table_name=table_name)
    for table_name in [
        "audit_events",
        "event_outbox",
        "durable_jobs",
        "graph_layout_positions",
        "graph_layouts",
        "graph_versions",
    ]:
        op.drop_table(table_name)
    op.drop_column("agent_context_blobs", "object_key")
