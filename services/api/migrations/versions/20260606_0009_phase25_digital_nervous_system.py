"""Add Phase 25 digital nervous system tables.

Revision ID: 20260606_0009
Revises: 20260605_0008
Create Date: 2026-06-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260606_0009"
down_revision: str | None = "20260605_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.UniqueConstraint("project_id", "checksum", name="uq_signals_project_checksum"),
    )
    op.create_index("ix_signals_project_received", "signals", ["project_id", "received_at"])
    op.create_index("ix_signals_project_id", "signals", ["project_id"])
    op.create_index("ix_signals_source_id", "signals", ["source_id"])

    op.create_table(
        "observations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("object_refs_json", sa.Text(), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("node_ids_json", sa.Text(), nullable=False),
        sa.Column("edge_ids_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
    )
    op.create_index("ix_observations_project_created", "observations", ["project_id", "created_at"])
    op.create_index("ix_observations_project_id", "observations", ["project_id"])
    op.create_index("ix_observations_signal_id", "observations", ["signal_id"])

    op.create_table(
        "owners",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("owner_type", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("contact", sa.String(length=240), nullable=True),
        sa.Column("scope_kind", sa.String(length=80), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=True),
        sa.Column("escalation_contact", sa.String(length=240), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
    )
    op.create_index("ix_owners_project_scope", "owners", ["project_id", "scope_kind", "scope_id"])
    op.create_index("ix_owners_project_id", "owners", ["project_id"])

    op.create_table(
        "routing_policies",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("match_json", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("sla_seconds", sa.Integer(), nullable=True),
        sa.Column("suggested_actions_json", sa.Text(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
    )
    op.create_index("ix_routing_policies_project_enabled", "routing_policies", ["project_id", "enabled"])
    op.create_index("ix_routing_policies_project_id", "routing_policies", ["project_id"])
    op.create_index("ix_routing_policies_owner_id", "routing_policies", ["owner_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=64), nullable=True),
        sa.Column("observation_id", sa.String(length=64), nullable=True),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("policy_id", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("object_refs_json", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["routing_policies.id"]),
    )
    op.create_index("ix_alerts_project_status_severity", "alerts", ["project_id", "status", "severity"])
    op.create_index("ix_alerts_project_id", "alerts", ["project_id"])
    op.create_index("ix_alerts_signal_id", "alerts", ["signal_id"])
    op.create_index("ix_alerts_observation_id", "alerts", ["observation_id"])
    op.create_index("ix_alerts_owner_id", "alerts", ["owner_id"])
    op.create_index("ix_alerts_policy_id", "alerts", ["policy_id"])

    op.create_table(
        "attention_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("sla_status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("assignee_id", sa.String(length=128), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("signal_id", sa.String(length=64), nullable=True),
        sa.Column("observation_id", sa.String(length=64), nullable=True),
        sa.Column("alert_id", sa.String(length=64), nullable=True),
        sa.Column("proposal_id", sa.String(length=64), nullable=True),
        sa.Column("decision_record_id", sa.String(length=64), nullable=True),
        sa.Column("action_proposal_id", sa.String(length=64), nullable=True),
        sa.Column("action_run_id", sa.String(length=64), nullable=True),
        sa.Column("outcome_id", sa.String(length=64), nullable=True),
        sa.Column("feedback_event_id", sa.String(length=64), nullable=True),
        sa.Column("object_refs_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("suggested_actions_json", sa.Text(), nullable=False),
        sa.Column("blockers_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"]),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["extraction_proposals.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
    )
    op.create_index("ix_attention_items_project_status_severity", "attention_items", ["project_id", "status", "severity"])
    op.create_index("ix_attention_items_project_id", "attention_items", ["project_id"])
    op.create_index("ix_attention_items_owner_id", "attention_items", ["owner_id"])
    op.create_index("ix_attention_items_source_id", "attention_items", ["source_id"])
    op.create_index("ix_attention_items_signal_id", "attention_items", ["signal_id"])
    op.create_index("ix_attention_items_observation_id", "attention_items", ["observation_id"])
    op.create_index("ix_attention_items_alert_id", "attention_items", ["alert_id"])
    op.create_index("ix_attention_items_proposal_id", "attention_items", ["proposal_id"])

    op.create_table(
        "decision_records",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("alert_id", sa.String(length=64), nullable=True),
        sa.Column("attention_item_id", sa.String(length=64), nullable=True),
        sa.Column("proposal_id", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("object_refs_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["attention_item_id"], ["attention_items.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["extraction_proposals.id"]),
    )
    op.create_index("ix_decision_records_project_id", "decision_records", ["project_id"])
    op.create_index("ix_decision_records_alert_id", "decision_records", ["alert_id"])
    op.create_index("ix_decision_records_attention_item_id", "decision_records", ["attention_item_id"])
    op.create_index("ix_decision_records_proposal_id", "decision_records", ["proposal_id"])

    op.create_table(
        "action_proposals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("decision_record_id", sa.String(length=64), nullable=True),
        sa.Column("alert_id", sa.String(length=64), nullable=True),
        sa.Column("attention_item_id", sa.String(length=64), nullable=True),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("redacted_payload_json", sa.Text(), nullable=False),
        sa.Column("safety_json", sa.Text(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("rejected_by", sa.String(length=128), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["decision_record_id"], ["decision_records.id"]),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["attention_item_id"], ["attention_items.id"]),
    )
    op.create_index("ix_action_proposals_project_status", "action_proposals", ["project_id", "status"])
    op.create_index("ix_action_proposals_project_id", "action_proposals", ["project_id"])
    op.create_index("ix_action_proposals_decision_record_id", "action_proposals", ["decision_record_id"])
    op.create_index("ix_action_proposals_alert_id", "action_proposals", ["alert_id"])
    op.create_index("ix_action_proposals_attention_item_id", "action_proposals", ["attention_item_id"])

    op.create_table(
        "action_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_proposal_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("executor_id", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=240), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("redacted_payload_json", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["action_proposal_id"], ["action_proposals.id"]),
    )
    op.create_index("ix_action_runs_project_status", "action_runs", ["project_id", "status"])
    op.create_index("ix_action_runs_project_id", "action_runs", ["project_id"])
    op.create_index("ix_action_runs_action_proposal_id", "action_runs", ["action_proposal_id"])

    op.create_table(
        "outcomes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_run_id", sa.String(length=64), nullable=True),
        sa.Column("attention_item_id", sa.String(length=64), nullable=True),
        sa.Column("alert_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["action_run_id"], ["action_runs.id"]),
        sa.ForeignKeyConstraint(["attention_item_id"], ["attention_items.id"]),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
    )
    op.create_index("ix_outcomes_project_created", "outcomes", ["project_id", "created_at"])
    op.create_index("ix_outcomes_project_id", "outcomes", ["project_id"])
    op.create_index("ix_outcomes_action_run_id", "outcomes", ["action_run_id"])
    op.create_index("ix_outcomes_attention_item_id", "outcomes", ["attention_item_id"])
    op.create_index("ix_outcomes_alert_id", "outcomes", ["alert_id"])

    op.create_table(
        "feedback_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("outcome_id", sa.String(length=64), nullable=True),
        sa.Column("action_run_id", sa.String(length=64), nullable=True),
        sa.Column("attention_item_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("effect_json", sa.Text(), nullable=False),
        sa.Column("proposed_value_json", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["graph_projects.id"]),
        sa.ForeignKeyConstraint(["outcome_id"], ["outcomes.id"]),
        sa.ForeignKeyConstraint(["action_run_id"], ["action_runs.id"]),
        sa.ForeignKeyConstraint(["attention_item_id"], ["attention_items.id"]),
    )
    op.create_index("ix_feedback_events_project_created", "feedback_events", ["project_id", "created_at"])
    op.create_index("ix_feedback_events_project_id", "feedback_events", ["project_id"])
    op.create_index("ix_feedback_events_outcome_id", "feedback_events", ["outcome_id"])
    op.create_index("ix_feedback_events_action_run_id", "feedback_events", ["action_run_id"])
    op.create_index("ix_feedback_events_attention_item_id", "feedback_events", ["attention_item_id"])


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_feedback_events_attention_item_id", "feedback_events"),
        ("ix_feedback_events_action_run_id", "feedback_events"),
        ("ix_feedback_events_outcome_id", "feedback_events"),
        ("ix_feedback_events_project_id", "feedback_events"),
        ("ix_feedback_events_project_created", "feedback_events"),
        ("ix_outcomes_alert_id", "outcomes"),
        ("ix_outcomes_attention_item_id", "outcomes"),
        ("ix_outcomes_action_run_id", "outcomes"),
        ("ix_outcomes_project_id", "outcomes"),
        ("ix_outcomes_project_created", "outcomes"),
        ("ix_action_runs_action_proposal_id", "action_runs"),
        ("ix_action_runs_project_id", "action_runs"),
        ("ix_action_runs_project_status", "action_runs"),
        ("ix_action_proposals_attention_item_id", "action_proposals"),
        ("ix_action_proposals_alert_id", "action_proposals"),
        ("ix_action_proposals_decision_record_id", "action_proposals"),
        ("ix_action_proposals_project_id", "action_proposals"),
        ("ix_action_proposals_project_status", "action_proposals"),
        ("ix_decision_records_proposal_id", "decision_records"),
        ("ix_decision_records_attention_item_id", "decision_records"),
        ("ix_decision_records_alert_id", "decision_records"),
        ("ix_decision_records_project_id", "decision_records"),
        ("ix_attention_items_proposal_id", "attention_items"),
        ("ix_attention_items_alert_id", "attention_items"),
        ("ix_attention_items_observation_id", "attention_items"),
        ("ix_attention_items_signal_id", "attention_items"),
        ("ix_attention_items_source_id", "attention_items"),
        ("ix_attention_items_owner_id", "attention_items"),
        ("ix_attention_items_project_id", "attention_items"),
        ("ix_attention_items_project_status_severity", "attention_items"),
        ("ix_alerts_policy_id", "alerts"),
        ("ix_alerts_owner_id", "alerts"),
        ("ix_alerts_observation_id", "alerts"),
        ("ix_alerts_signal_id", "alerts"),
        ("ix_alerts_project_id", "alerts"),
        ("ix_alerts_project_status_severity", "alerts"),
        ("ix_routing_policies_owner_id", "routing_policies"),
        ("ix_routing_policies_project_id", "routing_policies"),
        ("ix_routing_policies_project_enabled", "routing_policies"),
        ("ix_owners_project_id", "owners"),
        ("ix_owners_project_scope", "owners"),
        ("ix_observations_signal_id", "observations"),
        ("ix_observations_project_id", "observations"),
        ("ix_observations_project_created", "observations"),
        ("ix_signals_source_id", "signals"),
        ("ix_signals_project_id", "signals"),
        ("ix_signals_project_received", "signals"),
    ]:
        op.drop_index(index_name, table_name=table_name)
    for table_name in [
        "feedback_events",
        "outcomes",
        "action_runs",
        "action_proposals",
        "decision_records",
        "attention_items",
        "alerts",
        "routing_policies",
        "owners",
        "observations",
        "signals",
    ]:
        op.drop_table(table_name)
