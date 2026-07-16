import json
from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator
from sqlalchemy.pool import StaticPool
from pgvector.sqlalchemy import Vector

metadata = MetaData()


class JsonDocument(TypeDecorator):
    """JSONB in PostgreSQL while retaining serialized-text compatibility for SQLite and legacy code."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(JSONB()) if dialect.name == "postgresql" else dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql" and isinstance(value, str):
            return json.loads(value)
        return value

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql" and value is not None and not isinstance(value, str):
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        return value


JSON_DOCUMENT = JsonDocument()


def ensure_sqlite_json_shadow_columns(connection) -> None:
    for table in metadata.tables.values():
        existing = {row._mapping["name"] for row in connection.exec_driver_sql(f"PRAGMA table_info({table.name})")}
        for column in table.columns:
            if not column.name.endswith("__jsonb") or column.name in existing:
                continue
            connection.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" TEXT')
            legacy_name = column.name.removesuffix("__jsonb")
            if legacy_name in existing:
                connection.exec_driver_sql(
                    f'UPDATE "{table.name}" SET "{column.name}" = "{legacy_name}" WHERE "{column.name}" IS NULL'
                )

graph_projects = Table(
    "graph_projects",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(240), nullable=False),
    Column("description", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

topics = Table(
    "topics",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("name", String(240), nullable=False),
    Column("description", Text, nullable=True),
    Column("parent_topic_id", String(64), ForeignKey("topics.id"), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

graph_settings = Table(
    "graph_settings",
    metadata,
    Column("project_id", String(64), ForeignKey("graph_projects.id"), primary_key=True),
    Column("llm_enabled", Boolean(), nullable=False),
    Column("llm_provider", String(80), nullable=True),
    Column("llm_model", String(160), nullable=True),
    Column("auto_commit_threshold", Float(), nullable=False),
    Column("settings_json__jsonb", JSON_DOCUMENT, key="settings_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

connector_accounts = Table(
    "connector_accounts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("display_name", String(240), nullable=False),
    Column("status", String(40), nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("encrypted_token_json", Text(), nullable=True),
    Column("scopes_json__jsonb", JSON_DOCUMENT, key="scopes_json", nullable=False),
    Column("settings_json__jsonb", JSON_DOCUMENT, key="settings_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

connector_targets = Table(
    "connector_targets",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("account_id", String(64), ForeignKey("connector_accounts.id"), nullable=False, index=True),
    Column("connector_kind", String(40), nullable=False),
    Column("target_type", String(80), nullable=False),
    Column("remote_id", Text(), nullable=False),
    Column("title", String(240), nullable=False),
    Column("parent_remote_id", Text(), nullable=True),
    Column("sync_settings_json__jsonb", JSON_DOCUMENT, key="sync_settings_json", nullable=False),
    Column("last_synced_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

sources = Table(
    "sources",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("uri", Text, nullable=True),
    Column("object_key", Text, nullable=True),
    Column("checksum", String(128), nullable=True),
    Column("connector_kind", String(40), nullable=True),
    Column("remote_id", Text, nullable=True),
    Column("remote_parent_id", Text, nullable=True),
    Column("remote_modified_at", DateTime(timezone=True), nullable=True),
    Column("remote_url", Text, nullable=True),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=True),
    Column("stale_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("project_id", "connector_kind", "remote_id", name="uq_sources_project_connector_remote"),
)

connector_sync_runs = Table(
    "connector_sync_runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("target_id", String(64), ForeignKey("connector_targets.id"), nullable=False, index=True),
    Column("status", String(40), nullable=False),
    Column("stage", String(80), nullable=False),
    Column("source_count", Integer(), nullable=False),
    Column("chunk_count", Integer(), nullable=False),
    Column("proposal_count", Integer(), nullable=False),
    Column("auto_committed_count", Integer(), nullable=False),
    Column("error", Text(), nullable=True),
    Column("trace_id", String(128), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

connector_cursors = Table(
    "connector_cursors",
    metadata,
    Column("target_id", String(64), ForeignKey("connector_targets.id"), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("cursor", Text(), nullable=True),
    Column("lease_owner", String(160), nullable=True),
    Column("leased_until", DateTime(timezone=True), nullable=True),
    Column("health_status", String(40), nullable=False),
    Column("retry_attempt", Integer(), nullable=False),
    Column("imported_count", Integer(), nullable=False),
    Column("deleted_count", Integer(), nullable=False),
    Column("last_success_at", DateTime(timezone=True), nullable=True),
    Column("next_scheduled_at", DateTime(timezone=True), nullable=True),
    Column("actionable_failure", Text(), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

upload_sessions = Table(
    "upload_sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("object_key", Text(), nullable=False),
    Column("storage_upload_id", Text(), nullable=False),
    Column("filename", String(240), nullable=False),
    Column("content_type", String(160), nullable=False),
    Column("title", String(240), nullable=False),
    Column("graph_id", String(160), nullable=True),
    Column("expected_bytes", Integer(), nullable=False),
    Column("received_bytes", Integer(), nullable=False),
    Column("status", String(40), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

upload_parts = Table(
    "upload_parts",
    metadata,
    Column("session_id", String(64), ForeignKey("upload_sessions.id"), primary_key=True),
    Column("part_number", Integer(), primary_key=True),
    Column("offset_bytes", Integer(), nullable=False),
    Column("size_bytes", Integer(), nullable=False),
    Column("etag", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

source_chunks = Table(
    "source_chunks",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("source_id", String(64), ForeignKey("sources.id"), nullable=False, index=True),
    Column("parent_chunk_id", String(64), ForeignKey("source_chunks.id"), nullable=True),
    Column("heading_path_json__jsonb", JSON_DOCUMENT, key="heading_path_json", nullable=False),
    Column("block_type", String(80), nullable=False),
    Column("ordinal", Integer(), nullable=False),
    Column("text", Text(), nullable=False),
    Column("links_json__jsonb", JSON_DOCUMENT, key="links_json", nullable=False),
    Column("mentions_json__jsonb", JSON_DOCUMENT, key="mentions_json", nullable=False),
    Column("checksum", String(128), nullable=False),
    Column("locator", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("source_id", "ordinal", name="uq_source_chunks_source_ordinal"),
)

content_nodes = Table(
    "content_nodes",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("label", String(240), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("summary", Text, nullable=True),
    Column("topic_ids_json__jsonb", JSON_DOCUMENT, key="topic_ids_json", nullable=False),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=True),
    Column("provenance_json__jsonb", JSON_DOCUMENT, key="provenance_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

semantic_edges = Table(
    "semantic_edges",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("source_node_id", String(64), ForeignKey("content_nodes.id"), nullable=False),
    Column("target_node_id", String(64), ForeignKey("content_nodes.id"), nullable=False),
    Column("relation", String(40), nullable=False),
    Column("weight", Float, nullable=True),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=True),
    Column("provenance_json__jsonb", JSON_DOCUMENT, key="provenance_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("project_id", "source_node_id", "target_node_id", "relation", name="uq_semantic_edges_project_triplet"),
)
Index("ix_semantic_edges_source_adjacency", semantic_edges.c.project_id, semantic_edges.c.source_node_id)
Index("ix_semantic_edges_target_adjacency", semantic_edges.c.project_id, semantic_edges.c.target_node_id)

ingestion_runs = Table(
    "ingestion_runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("source_id", String(64), ForeignKey("sources.id"), nullable=False),
    Column("status", String(40), nullable=False),
    Column("stage", String(40), nullable=False),
    Column("trace_id", String(128), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error_code", String(80), nullable=True),
)

extraction_proposals = Table(
    "extraction_proposals",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("ingestion_run_id", String(64), ForeignKey("ingestion_runs.id"), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("proposed_value_json__jsonb", JSON_DOCUMENT, key="proposed_value_json", nullable=False),
    Column("confidence", Float, nullable=True),
    Column("provenance_json__jsonb", JSON_DOCUMENT, key="provenance_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

content_embeddings = Table(
    "content_embeddings",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("proposal_id", String(64), ForeignKey("extraction_proposals.id"), nullable=True, index=True),
    Column("content_node_id", String(64), ForeignKey("content_nodes.id"), nullable=True, index=True),
    Column("embedding_model", String(120), nullable=False),
    Column("vector_json__jsonb", JSON_DOCUMENT, key="vector_json", nullable=False),
    Column("vector_native", Vector(16).with_variant(Text(), "sqlite"), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("proposal_id", "embedding_model", name="uq_content_embeddings_proposal_model"),
)

review_decisions = Table(
    "review_decisions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("proposal_id", String(64), ForeignKey("extraction_proposals.id"), nullable=False),
    Column("reviewer_id", String(128), nullable=False),
    Column("decision", String(40), nullable=False),
    Column("edited_value_json__jsonb", JSON_DOCUMENT, key="edited_value_json", nullable=True),
    Column("rationale", Text, nullable=True),
    Column("decided_at", DateTime(timezone=True), nullable=False),
)

planning_sessions = Table(
    "planning_sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("graph_id", String(128), nullable=True),
    Column("lens", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("goal", Text(), nullable=False),
    Column("status", String(40), nullable=False),
    Column("provider", String(80), nullable=True),
    Column("model", String(160), nullable=True),
    Column("created_by", String(128), nullable=False),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

planning_messages = Table(
    "planning_messages",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("session_id", String(64), ForeignKey("planning_sessions.id"), nullable=False, index=True),
    Column("agent_run_id", String(64), nullable=True, index=True),
    Column("role", String(40), nullable=False),
    Column("content", Text(), nullable=False),
    Column("provider", String(80), nullable=True),
    Column("model", String(160), nullable=True),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

graph_build_specs = Table(
    "graph_build_specs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("session_id", String(64), ForeignKey("planning_sessions.id"), nullable=False, index=True),
    Column("version", Integer(), nullable=False),
    Column("title", String(240), nullable=False),
    Column("objective", Text(), nullable=False),
    Column("status", String(40), nullable=False),
    Column("spec_json__jsonb", JSON_DOCUMENT, key="spec_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("session_id", "version", name="uq_graph_build_specs_session_version"),
)

agent_runs = Table(
    "agent_runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("planning_session_id", String(64), ForeignKey("planning_sessions.id"), nullable=True, index=True),
    Column("kind", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("provider", String(80), nullable=False),
    Column("model", String(160), nullable=False),
    Column("input_json__jsonb", JSON_DOCUMENT, key="input_json", nullable=False),
    Column("output_json__jsonb", JSON_DOCUMENT, key="output_json", nullable=False),
    Column("trace_id", String(128), nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error", Text(), nullable=True),
)

agent_steps = Table(
    "agent_steps",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("agent_run_id", String(64), ForeignKey("agent_runs.id"), nullable=False, index=True),
    Column("name", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("input_summary", Text(), nullable=True),
    Column("output_summary", Text(), nullable=True),
    Column("error", Text(), nullable=True),
    Column("trace_id", String(128), nullable=False),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

research_tasks = Table(
    "research_tasks",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("agent_run_id", String(64), ForeignKey("agent_runs.id"), nullable=True, index=True),
    Column("planning_session_id", String(64), ForeignKey("planning_sessions.id"), nullable=True, index=True),
    Column("query", Text(), nullable=False),
    Column("status", String(40), nullable=False),
    Column("provider", String(80), nullable=False),
    Column("model", String(160), nullable=False),
    Column("source_policy", String(80), nullable=False),
    Column("idempotency_key", String(160), nullable=False, index=True),
    Column("result_json__jsonb", JSON_DOCUMENT, key="result_json", nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("project_id", "idempotency_key", name="uq_research_tasks_project_idempotency_key"),
)

agent_action_proposals = Table(
    "agent_action_proposals",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("agent_run_id", String(64), ForeignKey("agent_runs.id"), nullable=False, index=True),
    Column("action_type", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("citations_json__jsonb", JSON_DOCUMENT, key="citations_json", nullable=False),
    Column("confidence", Float(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=True),
)

signals = Table(
    "signals",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("graph_id", String(128), nullable=True),
    Column("kind", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("severity", String(40), nullable=False),
    Column("source_kind", String(40), nullable=False),
    Column("source_id", String(64), ForeignKey("sources.id"), nullable=True, index=True),
    Column("title", String(240), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("checksum", String(128), nullable=False),
    Column("trace_id", String(128), nullable=False),
    Column("actor_id", String(128), nullable=True),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("project_id", "checksum", name="uq_signals_project_checksum"),
)
Index("ix_signals_project_received", signals.c.project_id, signals.c.received_at)

observations = Table(
    "observations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("signal_id", String(64), ForeignKey("signals.id"), nullable=True, index=True),
    Column("kind", String(80), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("confidence", Float(), nullable=True),
    Column("evidence_json__jsonb", JSON_DOCUMENT, key="evidence_json", nullable=False),
    Column("object_refs_json__jsonb", JSON_DOCUMENT, key="object_refs_json", nullable=False),
    Column("source_ids_json__jsonb", JSON_DOCUMENT, key="source_ids_json", nullable=False),
    Column("node_ids_json__jsonb", JSON_DOCUMENT, key="node_ids_json", nullable=False),
    Column("edge_ids_json__jsonb", JSON_DOCUMENT, key="edge_ids_json", nullable=False),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_observations_project_created", observations.c.project_id, observations.c.created_at)

owners = Table(
    "owners",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("owner_type", String(40), nullable=False),
    Column("display_name", String(240), nullable=False),
    Column("contact", String(240), nullable=True),
    Column("scope_kind", String(80), nullable=False),
    Column("scope_id", String(128), nullable=True),
    Column("escalation_contact", String(240), nullable=True),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("ix_owners_project_scope", owners.c.project_id, owners.c.scope_kind, owners.c.scope_id)

routing_policies = Table(
    "routing_policies",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("name", String(240), nullable=False),
    Column("description", Text(), nullable=True),
    Column("enabled", Boolean(), nullable=False),
    Column("match_json__jsonb", JSON_DOCUMENT, key="match_json", nullable=False),
    Column("severity", String(40), nullable=False),
    Column("owner_id", String(64), ForeignKey("owners.id"), nullable=True, index=True),
    Column("sla_seconds", Integer(), nullable=True),
    Column("suggested_actions_json__jsonb", JSON_DOCUMENT, key="suggested_actions_json", nullable=False),
    Column("approval_required", Boolean(), nullable=False),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("ix_routing_policies_project_enabled", routing_policies.c.project_id, routing_policies.c.enabled)

alerts = Table(
    "alerts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("signal_id", String(64), ForeignKey("signals.id"), nullable=True, index=True),
    Column("observation_id", String(64), ForeignKey("observations.id"), nullable=True, index=True),
    Column("owner_id", String(64), ForeignKey("owners.id"), nullable=True, index=True),
    Column("policy_id", String(64), ForeignKey("routing_policies.id"), nullable=True, index=True),
    Column("severity", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("reason", Text(), nullable=False),
    Column("object_refs_json__jsonb", JSON_DOCUMENT, key="object_refs_json", nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("ix_alerts_project_status_severity", alerts.c.project_id, alerts.c.status, alerts.c.severity)

attention_items = Table(
    "attention_items",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("kind", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("severity", String(40), nullable=False),
    Column("sla_status", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("owner_id", String(64), ForeignKey("owners.id"), nullable=True, index=True),
    Column("assignee_id", String(128), nullable=True),
    Column("due_at", DateTime(timezone=True), nullable=True),
    Column("source_id", String(64), ForeignKey("sources.id"), nullable=True, index=True),
    Column("signal_id", String(64), ForeignKey("signals.id"), nullable=True, index=True),
    Column("observation_id", String(64), ForeignKey("observations.id"), nullable=True, index=True),
    Column("alert_id", String(64), ForeignKey("alerts.id"), nullable=True, index=True),
    Column("proposal_id", String(64), ForeignKey("extraction_proposals.id"), nullable=True, index=True),
    Column("decision_record_id", String(64), nullable=True),
    Column("action_proposal_id", String(64), nullable=True),
    Column("action_run_id", String(64), nullable=True),
    Column("outcome_id", String(64), nullable=True),
    Column("feedback_event_id", String(64), nullable=True),
    Column("object_refs_json__jsonb", JSON_DOCUMENT, key="object_refs_json", nullable=False),
    Column("evidence_json__jsonb", JSON_DOCUMENT, key="evidence_json", nullable=False),
    Column("suggested_actions_json__jsonb", JSON_DOCUMENT, key="suggested_actions_json", nullable=False),
    Column("blockers_json__jsonb", JSON_DOCUMENT, key="blockers_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
)
Index("ix_attention_items_project_status_severity", attention_items.c.project_id, attention_items.c.status, attention_items.c.severity)

decision_records = Table(
    "decision_records",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("alert_id", String(64), ForeignKey("alerts.id"), nullable=True, index=True),
    Column("attention_item_id", String(64), ForeignKey("attention_items.id"), nullable=True, index=True),
    Column("proposal_id", String(64), ForeignKey("extraction_proposals.id"), nullable=True, index=True),
    Column("decision", String(40), nullable=False),
    Column("rationale", Text(), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("evidence_json__jsonb", JSON_DOCUMENT, key="evidence_json", nullable=False),
    Column("object_refs_json__jsonb", JSON_DOCUMENT, key="object_refs_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

action_proposals = Table(
    "action_proposals",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("decision_record_id", String(64), ForeignKey("decision_records.id"), nullable=True, index=True),
    Column("alert_id", String(64), ForeignKey("alerts.id"), nullable=True, index=True),
    Column("attention_item_id", String(64), ForeignKey("attention_items.id"), nullable=True, index=True),
    Column("action_type", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("redacted_payload_json__jsonb", JSON_DOCUMENT, key="redacted_payload_json", nullable=False),
    Column("safety_json__jsonb", JSON_DOCUMENT, key="safety_json", nullable=False),
    Column("approval_required", Boolean(), nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("approved_by", String(128), nullable=True),
    Column("rejected_by", String(128), nullable=True),
    Column("rationale", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=True),
)
Index("ix_action_proposals_project_status", action_proposals.c.project_id, action_proposals.c.status)

action_runs = Table(
    "action_runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("action_proposal_id", String(64), ForeignKey("action_proposals.id"), nullable=False, index=True),
    Column("action_type", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("executor_id", String(128), nullable=False),
    Column("target", String(240), nullable=True),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("redacted_payload_json__jsonb", JSON_DOCUMENT, key="redacted_payload_json", nullable=False),
    Column("external_id", String(240), nullable=True),
    Column("trace_id", String(128), nullable=False),
    Column("error_code", String(80), nullable=True),
    Column("error", Text(), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)
Index("ix_action_runs_project_status", action_runs.c.project_id, action_runs.c.status)

outcomes = Table(
    "outcomes",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("action_run_id", String(64), ForeignKey("action_runs.id"), nullable=True, index=True),
    Column("attention_item_id", String(64), ForeignKey("attention_items.id"), nullable=True, index=True),
    Column("alert_id", String(64), ForeignKey("alerts.id"), nullable=True, index=True),
    Column("status", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("result_json__jsonb", JSON_DOCUMENT, key="result_json", nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_outcomes_project_created", outcomes.c.project_id, outcomes.c.created_at)

feedback_events = Table(
    "feedback_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("outcome_id", String(64), ForeignKey("outcomes.id"), nullable=True, index=True),
    Column("action_run_id", String(64), ForeignKey("action_runs.id"), nullable=True, index=True),
    Column("attention_item_id", String(64), ForeignKey("attention_items.id"), nullable=True, index=True),
    Column("kind", String(80), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("effect_json__jsonb", JSON_DOCUMENT, key="effect_json", nullable=False),
    Column("proposed_value_json__jsonb", JSON_DOCUMENT, key="proposed_value_json", nullable=True),
    Column("actor_id", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_feedback_events_project_created", feedback_events.c.project_id, feedback_events.c.created_at)

agent_context_clients = Table(
    "agent_context_clients",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("display_name", String(240), nullable=False),
    Column("runtime_kind", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("token_hash", String(128), nullable=False),
    Column("scopes_json__jsonb", JSON_DOCUMENT, key="scopes_json", nullable=False),
    Column("settings_json__jsonb", JSON_DOCUMENT, key="settings_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)
Index("ix_agent_context_clients_project_runtime", agent_context_clients.c.project_id, agent_context_clients.c.runtime_kind)

agent_context_sessions = Table(
    "agent_context_sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("client_id", String(64), ForeignKey("agent_context_clients.id"), nullable=False, index=True),
    Column("runtime_kind", String(80), nullable=False),
    Column("authority", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("workspace_root", Text(), nullable=True),
    Column("repository_uri", Text(), nullable=True),
    Column("branch", String(240), nullable=True),
    Column("commit_sha", String(80), nullable=True),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("ix_agent_context_sessions_project_updated", agent_context_sessions.c.project_id, agent_context_sessions.c.updated_at)
Index("ix_agent_context_sessions_client_started", agent_context_sessions.c.client_id, agent_context_sessions.c.started_at)

agent_context_artifacts = Table(
    "agent_context_artifacts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("session_id", String(64), ForeignKey("agent_context_sessions.id"), nullable=False, index=True),
    Column("kind", String(80), nullable=False),
    Column("uri", Text(), nullable=True),
    Column("path", Text(), nullable=True),
    Column("title", String(240), nullable=False),
    Column("content_type", String(80), nullable=False),
    Column("checksum", String(128), nullable=True),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("ix_agent_context_artifacts_session_kind", agent_context_artifacts.c.session_id, agent_context_artifacts.c.kind)

agent_context_blobs = Table(
    "agent_context_blobs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("session_id", String(64), ForeignKey("agent_context_sessions.id"), nullable=False, index=True),
    Column("artifact_id", String(64), ForeignKey("agent_context_artifacts.id"), nullable=True, index=True),
    Column("content_kind", String(40), nullable=False),
    Column("media_type", String(120), nullable=False),
    Column("redaction_status", String(40), nullable=False),
    Column("encryption_status", String(40), nullable=False),
    Column("checksum", String(128), nullable=False),
    Column("byte_count", Integer(), nullable=False),
    Column("token_count", Integer(), nullable=True),
    Column("encrypted_content", Text(), nullable=True),
    Column("object_key", Text(), nullable=True),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)
Index("ix_agent_context_blobs_project_expires", agent_context_blobs.c.project_id, agent_context_blobs.c.expires_at)

agent_context_events = Table(
    "agent_context_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("session_id", String(64), ForeignKey("agent_context_sessions.id"), nullable=False, index=True),
    Column("client_event_id", String(160), nullable=False),
    Column("sequence", Integer(), nullable=False),
    Column("event_kind", String(80), nullable=False),
    Column("authority", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("checksum", String(128), nullable=False),
    Column("artifact_id", String(64), ForeignKey("agent_context_artifacts.id"), nullable=True, index=True),
    Column("blob_id", String(64), ForeignKey("agent_context_blobs.id"), nullable=True, index=True),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("object_refs_json__jsonb", JSON_DOCUMENT, key="object_refs_json", nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("session_id", "client_event_id", name="uq_agent_context_events_session_client_event"),
    UniqueConstraint("session_id", "sequence", name="uq_agent_context_events_session_sequence"),
)
Index("ix_agent_context_events_session_sequence", agent_context_events.c.session_id, agent_context_events.c.sequence)
Index("ix_agent_context_events_project_received", agent_context_events.c.project_id, agent_context_events.c.received_at)

graph_activity_events = Table(
    "graph_activity_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("actor_id", String(128), nullable=True),
    Column("summary", Text(), nullable=False),
    Column("object_refs_json__jsonb", JSON_DOCUMENT, key="object_refs_json", nullable=False),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("lenses_json__jsonb", JSON_DOCUMENT, key="lenses_json", nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_graph_activity_events_project_created", graph_activity_events.c.project_id, graph_activity_events.c.created_at)
Index("ix_graph_activity_events_project_event_type", graph_activity_events.c.project_id, graph_activity_events.c.event_type)

graph_versions = Table(
    "graph_versions",
    metadata,
    Column("project_id", String(64), ForeignKey("graph_projects.id"), primary_key=True),
    Column("version", Integer(), nullable=False),
    Column("node_count", Integer(), nullable=False),
    Column("edge_count", Integer(), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

graph_layouts = Table(
    "graph_layouts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("name", String(160), nullable=False),
    Column("algorithm", String(80), nullable=False),
    Column("graph_version", Integer(), nullable=False),
    Column("settings_json__jsonb", JSON_DOCUMENT, key="settings_json", nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("project_id", "name", name="uq_graph_layouts_project_name"),
)

graph_layout_positions = Table(
    "graph_layout_positions",
    metadata,
    Column("layout_id", String(64), ForeignKey("graph_layouts.id"), primary_key=True),
    Column("node_id", String(64), ForeignKey("content_nodes.id"), primary_key=True),
    Column("x", Float(), nullable=False),
    Column("y", Float(), nullable=False),
    Column("z", Float(), nullable=True),
    Column("cluster_key", String(160), nullable=True),
)
Index("ix_graph_layout_positions_xy", graph_layout_positions.c.layout_id, graph_layout_positions.c.x, graph_layout_positions.c.y)
Index("ix_graph_layout_positions_node", graph_layout_positions.c.node_id, graph_layout_positions.c.layout_id)

durable_jobs = Table(
    "durable_jobs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("queue", String(80), nullable=False),
    Column("kind", String(120), nullable=False),
    Column("status", String(40), nullable=False),
    Column("idempotency_key", String(240), nullable=False),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("result_json__jsonb", JSON_DOCUMENT, key="result_json", nullable=False),
    Column("attempt", Integer(), nullable=False),
    Column("max_attempts", Integer(), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("leased_until", DateTime(timezone=True), nullable=True),
    Column("worker_id", String(160), nullable=True),
    Column("error_code", String(120), nullable=True),
    Column("error", Text(), nullable=True),
    Column("trace_id", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("project_id", "idempotency_key", name="uq_durable_jobs_project_idempotency"),
)
Index("ix_durable_jobs_dispatch", durable_jobs.c.queue, durable_jobs.c.status, durable_jobs.c.available_at)

event_outbox = Table(
    "event_outbox",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("topic", String(160), nullable=False),
    Column("event_type", String(120), nullable=False),
    Column("aggregate_type", String(80), nullable=False),
    Column("aggregate_id", String(128), nullable=False),
    Column("schema_version", Integer(), nullable=False),
    Column("payload_json__jsonb", JSON_DOCUMENT, key="payload_json", nullable=False),
    Column("trace_id", String(128), nullable=False),
    Column("status", String(40), nullable=False),
    Column("attempt", Integer(), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_event_outbox_dispatch", event_outbox.c.status, event_outbox.c.available_at)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("actor_id", String(128), nullable=True),
    Column("action", String(160), nullable=False),
    Column("resource_type", String(80), nullable=False),
    Column("resource_id", String(128), nullable=True),
    Column("outcome", String(40), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("metadata_json__jsonb", JSON_DOCUMENT, key="metadata_json", nullable=False),
    Column("trace_id", String(128), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)
Index("ix_audit_events_project_occurred", audit_events.c.project_id, audit_events.c.occurred_at)


def create_app_engine(database_url: str):
    if database_url.startswith("sqlite:///"):
        sqlite_path = database_url.removeprefix("sqlite:///")
        if sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            return create_engine(database_url, connect_args={"check_same_thread": False})
        return create_engine(database_url, connect_args={"check_same_thread": False})
    if database_url == "sqlite://":
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if database_url.startswith("postgresql+psycopg"):
        # Psycopg's automatic prepared-statement threshold can replace selective
        # viewport plans with a generic plan after a few requests. Keep planning
        # parameter-aware for bounded LOD queries whose bounds and limits vary.
        return create_engine(database_url, connect_args={"prepare_threshold": None}, pool_pre_ping=True)
    return create_engine(database_url, pool_pre_ping=True)
