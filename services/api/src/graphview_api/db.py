from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine
from sqlalchemy.pool import StaticPool

metadata = MetaData()

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
    Column("settings_json", Text(), nullable=False),
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
    Column("scopes_json", Text(), nullable=False),
    Column("settings_json", Text(), nullable=False),
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
    Column("sync_settings_json", Text(), nullable=False),
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
    Column("metadata_json", Text, nullable=True),
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

source_chunks = Table(
    "source_chunks",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("source_id", String(64), ForeignKey("sources.id"), nullable=False, index=True),
    Column("parent_chunk_id", String(64), ForeignKey("source_chunks.id"), nullable=True),
    Column("heading_path_json", Text(), nullable=False),
    Column("block_type", String(80), nullable=False),
    Column("ordinal", Integer(), nullable=False),
    Column("text", Text(), nullable=False),
    Column("links_json", Text(), nullable=False),
    Column("mentions_json", Text(), nullable=False),
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
    Column("topic_ids_json", Text, nullable=False),
    Column("metadata_json", Text, nullable=True),
    Column("provenance_json", Text, nullable=False),
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
    Column("metadata_json", Text, nullable=True),
    Column("provenance_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("project_id", "source_node_id", "target_node_id", "relation", name="uq_semantic_edges_project_triplet"),
)

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
    Column("proposed_value_json", Text, nullable=False),
    Column("confidence", Float, nullable=True),
    Column("provenance_json", Text, nullable=False),
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
    Column("vector_json", Text, nullable=False),
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
    Column("edited_value_json", Text, nullable=True),
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
    Column("metadata_json", Text(), nullable=False),
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
    Column("metadata_json", Text(), nullable=False),
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
    Column("spec_json", Text(), nullable=False),
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
    Column("input_json", Text(), nullable=False),
    Column("output_json", Text(), nullable=False),
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
    Column("metadata_json", Text(), nullable=False),
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
    Column("result_json", Text(), nullable=False),
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
    Column("payload_json", Text(), nullable=False),
    Column("citations_json", Text(), nullable=False),
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
    Column("payload_json", Text(), nullable=False),
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
    Column("evidence_json", Text(), nullable=False),
    Column("object_refs_json", Text(), nullable=False),
    Column("source_ids_json", Text(), nullable=False),
    Column("node_ids_json", Text(), nullable=False),
    Column("edge_ids_json", Text(), nullable=False),
    Column("metadata_json", Text(), nullable=False),
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
    Column("metadata_json", Text(), nullable=False),
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
    Column("match_json", Text(), nullable=False),
    Column("severity", String(40), nullable=False),
    Column("owner_id", String(64), ForeignKey("owners.id"), nullable=True, index=True),
    Column("sla_seconds", Integer(), nullable=True),
    Column("suggested_actions_json", Text(), nullable=False),
    Column("approval_required", Boolean(), nullable=False),
    Column("metadata_json", Text(), nullable=False),
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
    Column("object_refs_json", Text(), nullable=False),
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
    Column("object_refs_json", Text(), nullable=False),
    Column("evidence_json", Text(), nullable=False),
    Column("suggested_actions_json", Text(), nullable=False),
    Column("blockers_json", Text(), nullable=False),
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
    Column("evidence_json", Text(), nullable=False),
    Column("object_refs_json", Text(), nullable=False),
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
    Column("payload_json", Text(), nullable=False),
    Column("redacted_payload_json", Text(), nullable=False),
    Column("safety_json", Text(), nullable=False),
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
    Column("payload_json", Text(), nullable=False),
    Column("redacted_payload_json", Text(), nullable=False),
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
    Column("result_json", Text(), nullable=False),
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
    Column("effect_json", Text(), nullable=False),
    Column("proposed_value_json", Text(), nullable=True),
    Column("actor_id", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_feedback_events_project_created", feedback_events.c.project_id, feedback_events.c.created_at)

graph_activity_events = Table(
    "graph_activity_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("actor_id", String(128), nullable=True),
    Column("summary", Text(), nullable=False),
    Column("object_refs_json", Text(), nullable=False),
    Column("payload_json", Text(), nullable=False),
    Column("lenses_json", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_graph_activity_events_project_created", graph_activity_events.c.project_id, graph_activity_events.c.created_at)
Index("ix_graph_activity_events_project_event_type", graph_activity_events.c.project_id, graph_activity_events.c.event_type)


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
    return create_engine(database_url)
