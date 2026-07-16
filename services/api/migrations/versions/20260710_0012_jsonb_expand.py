"""expand legacy JSON text fields with dual-written PostgreSQL JSONB columns

Revision ID: 20260710_0012
Revises: 20260710_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260710_0012"
down_revision: str | None = "20260710_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_COLUMNS = {
    "graph_settings": ("settings_json",),
    "connector_accounts": ("encrypted_token_json", "scopes_json", "settings_json"),
    "connector_targets": ("sync_settings_json",),
    "sources": ("metadata_json",),
    "source_chunks": ("heading_path_json", "links_json", "mentions_json"),
    "content_nodes": ("topic_ids_json", "metadata_json", "provenance_json"),
    "semantic_edges": ("metadata_json", "provenance_json"),
    "extraction_proposals": ("proposed_value_json", "provenance_json"),
    "content_embeddings": ("vector_json",),
    "review_decisions": ("edited_value_json",),
    "planning_sessions": ("metadata_json",),
    "planning_messages": ("metadata_json",),
    "graph_build_specs": ("spec_json",),
    "agent_runs": ("input_json", "output_json"),
    "agent_steps": ("metadata_json",),
    "research_tasks": ("result_json",),
    "agent_action_proposals": ("payload_json", "citations_json"),
    "signals": ("payload_json",),
    "observations": ("evidence_json", "object_refs_json", "source_ids_json", "node_ids_json", "edge_ids_json", "metadata_json"),
    "owners": ("metadata_json",),
    "routing_policies": ("match_json", "suggested_actions_json", "metadata_json"),
    "alerts": ("object_refs_json",),
    "attention_items": ("object_refs_json", "evidence_json", "suggested_actions_json", "blockers_json"),
    "decision_records": ("evidence_json", "object_refs_json"),
    "action_proposals": ("payload_json", "redacted_payload_json", "safety_json"),
    "action_runs": ("payload_json", "redacted_payload_json"),
    "outcomes": ("result_json",),
    "feedback_events": ("effect_json", "proposed_value_json"),
    "agent_context_clients": ("scopes_json", "settings_json"),
    "agent_context_sessions": ("metadata_json",),
    "agent_context_artifacts": ("metadata_json",),
    "agent_context_blobs": ("metadata_json",),
    "agent_context_events": ("payload_json", "object_refs_json"),
    "graph_activity_events": ("object_refs_json", "payload_json", "lenses_json"),
    "graph_layouts": ("settings_json",),
    "durable_jobs": ("payload_json", "result_json"),
    "event_outbox": ("payload_json",),
    "audit_events": ("metadata_json",),
}


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    json_type = postgresql.JSONB(astext_type=sa.Text()) if postgres else sa.Text()
    for table, columns in JSON_COLUMNS.items():
        for column in columns:
            op.add_column(table, sa.Column(f"{column}__jsonb", json_type, nullable=True))
        if postgres:
            assignments = []
            for column in columns:
                shadow = f"{column}__jsonb"
                assignments.append(f"""
                  IF TG_OP = 'INSERT' THEN
                    IF NEW.{shadow} IS NULL AND NEW.{column} IS NOT NULL THEN NEW.{shadow} := NEW.{column}::jsonb;
                    ELSE NEW.{column} := CASE WHEN NEW.{shadow} IS NULL THEN NULL ELSE NEW.{shadow}::text END; END IF;
                  ELSIF NEW.{shadow} IS DISTINCT FROM OLD.{shadow} THEN
                    NEW.{column} := CASE WHEN NEW.{shadow} IS NULL THEN NULL ELSE NEW.{shadow}::text END;
                  ELSIF NEW.{column} IS DISTINCT FROM OLD.{column} THEN
                    NEW.{shadow} := CASE WHEN NEW.{column} IS NULL THEN NULL ELSE NEW.{column}::jsonb END;
                  END IF;
                """)
            op.execute(f"""
              CREATE FUNCTION graphview_sync_{table}_jsonb() RETURNS trigger AS $$ BEGIN
                {''.join(assignments)}
                RETURN NEW;
              END $$ LANGUAGE plpgsql
            """)
            op.execute(
                f"CREATE TRIGGER graphview_sync_{table}_jsonb BEFORE INSERT OR UPDATE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION graphview_sync_{table}_jsonb()"
            )


def downgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    for table, columns in reversed(tuple(JSON_COLUMNS.items())):
        if postgres:
            op.execute(f"DROP TRIGGER IF EXISTS graphview_sync_{table}_jsonb ON {table}")
            op.execute(f"DROP FUNCTION IF EXISTS graphview_sync_{table}_jsonb")
        for column in reversed(columns):
            op.drop_column(table, f"{column}__jsonb")
