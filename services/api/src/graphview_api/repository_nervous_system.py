from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, select, update

from graphview_api import db
from graphview_api.json_compat import json_value
from graphview_api.schemas import (
    ActionProposalCreate,
    ActionProposalDecision,
    ActionRunCreate,
    AlertAssign,
    AttentionTransition,
    DecisionRecordCreate,
    FeedbackEventCreate,
    ObservationCreate,
    OutcomeCreate,
    OwnerCreate,
    OwnerUpdate,
    RoutingPolicyCreate,
    RoutingPolicyUpdate,
    SignalCreate,
)

DEFAULT_PROJECT_ID = "project-default"
SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


def now() -> datetime:
    return datetime.now(tz=UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


def dump_json(value: object) -> str:
    return json.dumps(_jsonable(value), sort_keys=True)


def _jsonable(value: object):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def load_json(value: object | None, fallback: object):
    if value is None:
        return fallback
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


class NervousSystemRepositoryMixin:
    """Signals, Attention, decisions, actions, outcomes, and feedback persistence."""

    def create_owner(self, payload: OwnerCreate) -> dict:
        timestamp = now()
        row = {
            "id": new_id("owner"),
            "project_id": DEFAULT_PROJECT_ID,
            "owner_type": payload.owner_type,
            "display_name": payload.display_name,
            "contact": payload.contact,
            "scope_kind": payload.scope_kind,
            "scope_id": payload.scope_id,
            "escalation_contact": payload.escalation_contact,
            "metadata_json": dump_json(payload.metadata),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.owners).values(**row))
        return self._owner_from_row(row)

    def update_owner(self, owner_id: str, payload: OwnerUpdate) -> dict | None:
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return self.get_owner(owner_id)
        if "metadata" in values:
            values["metadata_json"] = dump_json(values.pop("metadata") or {})
        values["updated_at"] = now()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(db.owners)
                .where(db.owners.c.id == owner_id)
                .values(**values)
            )
            if result.rowcount == 0:
                return None
            row = conn.execute(select(db.owners).where(db.owners.c.id == owner_id)).mappings().first()
        return self._owner_from_row(row) if row else None

    def get_owner(self, owner_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(db.owners).where(db.owners.c.id == owner_id)).mappings().first()
        return self._owner_from_row(row) if row else None

    def list_owners(self, *, scope_kind: str | None = None, limit: int = 100) -> list[dict]:
        stmt = select(db.owners).where(db.owners.c.project_id == DEFAULT_PROJECT_ID)
        if scope_kind:
            stmt = stmt.where(db.owners.c.scope_kind == scope_kind)
        stmt = stmt.order_by(db.owners.c.updated_at.desc(), db.owners.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._owner_from_row(row) for row in conn.execute(stmt).mappings()]

    def create_routing_policy(self, payload: RoutingPolicyCreate) -> dict:
        timestamp = now()
        row = {
            "id": new_id("policy"),
            "project_id": DEFAULT_PROJECT_ID,
            "name": payload.name,
            "description": payload.description,
            "enabled": payload.enabled,
            "match_json": dump_json(payload.match),
            "severity": payload.severity,
            "owner_id": payload.owner_id,
            "sla_seconds": payload.sla_seconds,
            "suggested_actions_json": dump_json(payload.suggested_actions),
            "approval_required": payload.approval_required,
            "metadata_json": dump_json(payload.metadata),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.routing_policies).values(**row))
        return self._routing_policy_from_row(row)

    def update_routing_policy(self, policy_id: str, payload: RoutingPolicyUpdate) -> dict | None:
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return self.get_routing_policy(policy_id)
        if "match" in values:
            values["match_json"] = dump_json(values.pop("match") or {})
        if "suggested_actions" in values:
            values["suggested_actions_json"] = dump_json(values.pop("suggested_actions") or [])
        if "metadata" in values:
            values["metadata_json"] = dump_json(values.pop("metadata") or {})
        values["updated_at"] = now()
        with self.engine.begin() as conn:
            result = conn.execute(update(db.routing_policies).where(db.routing_policies.c.id == policy_id).values(**values))
            if result.rowcount == 0:
                return None
            row = conn.execute(select(db.routing_policies).where(db.routing_policies.c.id == policy_id)).mappings().first()
        return self._routing_policy_from_row(row) if row else None

    def get_routing_policy(self, policy_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(db.routing_policies).where(db.routing_policies.c.id == policy_id)).mappings().first()
        return self._routing_policy_from_row(row) if row else None

    def list_routing_policies(self, *, enabled: bool | None = None, limit: int = 100) -> list[dict]:
        stmt = select(db.routing_policies).where(db.routing_policies.c.project_id == DEFAULT_PROJECT_ID)
        if enabled is not None:
            stmt = stmt.where(db.routing_policies.c.enabled == enabled)
        stmt = stmt.order_by(db.routing_policies.c.updated_at.desc(), db.routing_policies.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._routing_policy_from_row(row) for row in conn.execute(stmt).mappings()]

    def create_signal(self, payload: SignalCreate, actor_id: str) -> dict:
        timestamp = payload.received_at or now()
        project_id = self._graph_view_spec(payload.graph_id).project_id if payload.graph_id else DEFAULT_PROJECT_ID
        checksum = self._signal_checksum(payload)
        trace_id = payload.trace_id or new_id("trace")
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(db.signals).where(
                    and_(db.signals.c.project_id == project_id, db.signals.c.checksum == checksum)
                )
            ).mappings().first()
            if existing is not None:
                return self._signal_from_row(existing)
            row = {
                "id": new_id("signal"),
                "project_id": project_id,
                "graph_id": payload.graph_id,
                "kind": payload.kind,
                "status": "new",
                "severity": payload.severity,
                "source_kind": payload.source_kind,
                "source_id": payload.source_id,
                "title": payload.title,
                "summary": payload.summary,
                "payload_json": dump_json(payload.payload),
                "checksum": checksum,
                "trace_id": trace_id,
                "actor_id": actor_id,
                "received_at": timestamp,
                "created_at": timestamp,
            }
            conn.execute(insert(db.signals).values(**row))
            signal = self._signal_from_row(row)
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type="signal.created",
                actor_id=actor_id,
                summary=f"Sensed {payload.kind.replace('_', ' ')}: {payload.title}.",
                object_refs=self._phase25_object_refs(signal),
                payload={"signal_id": row["id"], "kind": payload.kind, "severity": payload.severity, "source_id": payload.source_id},
                lenses=self._phase25_lenses(payload.graph_id),
                timestamp=timestamp,
            )
            if payload.route:
                self._route_signal(conn, signal, actor_id, timestamp)
                signal["status"] = "routed"
        return signal

    def list_signals(self, *, kind: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        stmt = select(db.signals).where(db.signals.c.project_id == DEFAULT_PROJECT_ID)
        if kind:
            stmt = stmt.where(db.signals.c.kind == kind)
        if status:
            stmt = stmt.where(db.signals.c.status == status)
        stmt = stmt.order_by(db.signals.c.received_at.desc(), db.signals.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._signal_from_row(row) for row in conn.execute(stmt).mappings()]

    def get_signal(self, signal_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(db.signals).where(db.signals.c.id == signal_id)).mappings().first()
        return self._signal_from_row(row) if row else None

    def create_observation(self, payload: ObservationCreate, actor_id: str) -> dict:
        timestamp = now()
        signal = self.get_signal(payload.signal_id) if payload.signal_id else None
        project_id = signal["project_id"] if signal else DEFAULT_PROJECT_ID
        row = {
            "id": new_id("observation"),
            "project_id": project_id,
            "signal_id": payload.signal_id,
            "kind": payload.kind,
            "summary": payload.summary,
            "confidence": payload.confidence,
            "evidence_json": dump_json(payload.evidence),
            "object_refs_json": dump_json([ref.model_dump() for ref in payload.object_refs]),
            "source_ids_json": dump_json(payload.source_ids),
            "node_ids_json": dump_json(payload.node_ids),
            "edge_ids_json": dump_json(payload.edge_ids),
            "metadata_json": dump_json(payload.metadata),
            "created_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.observations).values(**row))
            if payload.signal_id:
                conn.execute(update(db.signals).where(db.signals.c.id == payload.signal_id).values(status="linked"))
            observation = self._observation_from_row(row)
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type="observation.created",
                actor_id=actor_id,
                summary=f"Recorded observation: {payload.summary}",
                object_refs=self._phase25_object_refs(observation),
                payload={"observation_id": row["id"], "signal_id": payload.signal_id},
                lenses=[],
                timestamp=timestamp,
            )
        return observation

    def list_observations(self, *, signal_id: str | None = None, limit: int = 50) -> list[dict]:
        stmt = select(db.observations).where(db.observations.c.project_id == DEFAULT_PROJECT_ID)
        if signal_id:
            stmt = stmt.where(db.observations.c.signal_id == signal_id)
        stmt = stmt.order_by(db.observations.c.created_at.desc(), db.observations.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._observation_from_row(row) for row in conn.execute(stmt).mappings()]

    def list_alerts(self, *, status: str | None = None, severity: str | None = None, limit: int = 50) -> list[dict]:
        stmt = select(db.alerts).where(db.alerts.c.project_id == DEFAULT_PROJECT_ID)
        if status:
            stmt = stmt.where(db.alerts.c.status == status)
        if severity:
            stmt = stmt.where(db.alerts.c.severity == severity)
        stmt = stmt.order_by(db.alerts.c.updated_at.desc(), db.alerts.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._alert_from_row(row) for row in conn.execute(stmt).mappings()]

    def assign_alert(self, alert_id: str, payload: AlertAssign, actor_id: str) -> dict | None:
        timestamp = now()
        with self.engine.begin() as conn:
            row = conn.execute(select(db.alerts).where(db.alerts.c.id == alert_id)).mappings().first()
            if row is None:
                return None
            conn.execute(
                update(db.alerts)
                .where(db.alerts.c.id == alert_id)
                .values(owner_id=payload.owner_id, status=payload.status, updated_at=timestamp)
            )
            conn.execute(
                update(db.attention_items)
                .where(db.attention_items.c.alert_id == alert_id)
                .values(owner_id=payload.owner_id, assignee_id=payload.assignee_id, status="assigned", updated_at=timestamp)
            )
            updated = conn.execute(select(db.alerts).where(db.alerts.c.id == alert_id)).mappings().first()
            self._record_activity_event(
                conn,
                project_id=row["project_id"],
                event_type="alert.assigned",
                actor_id=actor_id,
                summary=f"Assigned alert {row['title']}.",
                object_refs=[self._activity_ref("alert", alert_id, row["title"])],
                payload={"alert_id": alert_id, "owner_id": payload.owner_id, "assignee_id": payload.assignee_id},
                lenses=[],
                timestamp=timestamp,
            )
        return self._alert_from_row(updated) if updated else None

    def list_attention(self, *, status: str | None = None, severity: str | None = None, owner_id: str | None = None, limit: int = 50) -> dict:
        stmt = select(db.attention_items).where(db.attention_items.c.project_id == DEFAULT_PROJECT_ID)
        if status:
            stmt = stmt.where(db.attention_items.c.status == status)
        if severity:
            stmt = stmt.where(db.attention_items.c.severity == severity)
        if owner_id:
            stmt = stmt.where(db.attention_items.c.owner_id == owner_id)
        with self.engine.begin() as conn:
            rows = [self._attention_item_from_row(row) for row in conn.execute(stmt).mappings()]
        rows.sort(key=lambda item: (-SEVERITY_RANK.get(item["severity"], 0), item["due_at"] or item["updated_at"], item["id"]))
        items = rows[: min(100, max(1, limit))]
        return {"generated_at": now(), "returned_count": len(items), "items": items}

    def transition_attention(self, attention_item_id: str, payload: AttentionTransition, actor_id: str) -> dict | None:
        timestamp = now()
        with self.engine.begin() as conn:
            row = conn.execute(select(db.attention_items).where(db.attention_items.c.id == attention_item_id)).mappings().first()
            if row is None:
                return None
            resolved_at = timestamp if payload.status in {"resolved", "dismissed"} else None
            values = {
                "status": payload.status,
                "assignee_id": payload.assignee_id if payload.assignee_id is not None else row["assignee_id"],
                "blockers_json": dump_json(payload.blockers) if payload.blockers is not None else json_value(row, "blockers_json"),
                "updated_at": timestamp,
                "resolved_at": resolved_at,
            }
            conn.execute(update(db.attention_items).where(db.attention_items.c.id == attention_item_id).values(**values))
            updated = conn.execute(select(db.attention_items).where(db.attention_items.c.id == attention_item_id)).mappings().first()
            self._record_activity_event(
                conn,
                project_id=row["project_id"],
                event_type="attention.transitioned",
                actor_id=actor_id,
                summary=f"Moved attention item {row['title']} to {payload.status.replace('_', ' ')}.",
                object_refs=[self._activity_ref("attention", attention_item_id, row["title"])],
                payload={"attention_item_id": attention_item_id, "status": payload.status, "rationale": payload.rationale},
                lenses=[],
                timestamp=timestamp,
            )
        return self._attention_item_from_row(updated) if updated else None

    def create_decision_record(self, payload: DecisionRecordCreate, actor_id: str) -> dict:
        timestamp = now()
        project_id = DEFAULT_PROJECT_ID
        row = {
            "id": new_id("decision"),
            "project_id": project_id,
            "alert_id": payload.alert_id,
            "attention_item_id": payload.attention_item_id,
            "proposal_id": payload.proposal_id,
            "decision": payload.decision,
            "rationale": payload.rationale,
            "actor_id": actor_id,
            "evidence_json": dump_json(payload.evidence),
            "object_refs_json": dump_json([ref.model_dump() for ref in payload.object_refs]),
            "created_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.decision_records).values(**row))
            if payload.attention_item_id:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == payload.attention_item_id)
                    .values(decision_record_id=row["id"], status="waiting_for_action", updated_at=timestamp)
                )
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type="decision.recorded",
                actor_id=actor_id,
                summary=f"Recorded {payload.decision} decision.",
                object_refs=self._phase25_object_refs(self._decision_record_from_row(row)),
                payload={"decision_record_id": row["id"], "decision": payload.decision, "attention_item_id": payload.attention_item_id},
                lenses=[],
                timestamp=timestamp,
            )
        return self._decision_record_from_row(row)

    def list_decision_records(self, *, limit: int = 50) -> list[dict]:
        stmt = (
            select(db.decision_records)
            .where(db.decision_records.c.project_id == DEFAULT_PROJECT_ID)
            .order_by(db.decision_records.c.created_at.desc(), db.decision_records.c.id.desc())
            .limit(min(100, max(1, limit)))
        )
        with self.engine.begin() as conn:
            return [self._decision_record_from_row(row) for row in conn.execute(stmt).mappings()]

    def create_action_proposal(self, payload: ActionProposalCreate, actor_id: str) -> dict:
        timestamp = now()
        safety = payload.safety.model_dump() if payload.safety else self._default_action_safety(payload.action_type, payload.approval_required)
        approval_required = bool(safety.get("approval_required", payload.approval_required))
        row = {
            "id": new_id("action"),
            "project_id": DEFAULT_PROJECT_ID,
            "decision_record_id": payload.decision_record_id,
            "alert_id": payload.alert_id,
            "attention_item_id": payload.attention_item_id,
            "action_type": payload.action_type,
            "status": "pending_review" if approval_required else "approved",
            "title": payload.title,
            "summary": payload.summary,
            "payload_json": dump_json(payload.payload),
            "redacted_payload_json": dump_json(self._redact_payload(payload.payload)),
            "safety_json": dump_json(safety),
            "approval_required": approval_required,
            "created_by": actor_id,
            "approved_by": actor_id if not approval_required else None,
            "rejected_by": None,
            "rationale": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "decided_at": timestamp if not approval_required else None,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.action_proposals).values(**row))
            if payload.attention_item_id:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == payload.attention_item_id)
                    .values(action_proposal_id=row["id"], status="waiting_for_review" if approval_required else "waiting_for_action", updated_at=timestamp)
                )
            self._record_activity_event(
                conn,
                project_id=DEFAULT_PROJECT_ID,
                event_type="action.proposed",
                actor_id=actor_id,
                summary=f"Proposed action {payload.title}.",
                object_refs=self._phase25_object_refs(self._action_proposal_from_row(row)),
                payload={"action_proposal_id": row["id"], "action_type": payload.action_type, "attention_item_id": payload.attention_item_id},
                lenses=[],
                timestamp=timestamp,
            )
        return self._action_proposal_from_row(row)

    def list_action_proposals(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        stmt = select(db.action_proposals).where(db.action_proposals.c.project_id == DEFAULT_PROJECT_ID)
        if status:
            stmt = stmt.where(db.action_proposals.c.status == status)
        stmt = stmt.order_by(db.action_proposals.c.updated_at.desc(), db.action_proposals.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._action_proposal_from_row(row) for row in conn.execute(stmt).mappings()]

    def decide_action_proposal(self, action_proposal_id: str, decision: str, payload: ActionProposalDecision, actor_id: str) -> dict | None:
        timestamp = now()
        if decision not in {"approved", "rejected"}:
            raise ValueError("Action proposal decision must be approved or rejected.")
        with self.engine.begin() as conn:
            row = conn.execute(select(db.action_proposals).where(db.action_proposals.c.id == action_proposal_id)).mappings().first()
            if row is None:
                return None
            if row["status"] not in {"pending_review", "proposed"}:
                raise ValueError(f"Action proposal is already {row['status']}.")
            values = {
                "status": decision,
                "approved_by": actor_id if decision == "approved" else None,
                "rejected_by": actor_id if decision == "rejected" else None,
                "rationale": payload.rationale,
                "updated_at": timestamp,
                "decided_at": timestamp,
            }
            conn.execute(update(db.action_proposals).where(db.action_proposals.c.id == action_proposal_id).values(**values))
            if row["attention_item_id"]:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == row["attention_item_id"])
                    .values(status="waiting_for_action" if decision == "approved" else "blocked", updated_at=timestamp)
                )
            updated = conn.execute(select(db.action_proposals).where(db.action_proposals.c.id == action_proposal_id)).mappings().first()
            self._record_activity_event(
                conn,
                project_id=row["project_id"],
                event_type=f"action.{decision}",
                actor_id=actor_id,
                summary=f"{decision.title()} action {row['title']}.",
                object_refs=[self._activity_ref("action_proposal", action_proposal_id, row["title"])],
                payload={"action_proposal_id": action_proposal_id, "decision": decision},
                lenses=[],
                timestamp=timestamp,
            )
        return self._action_proposal_from_row(updated) if updated else None

    def create_action_run(self, payload: ActionRunCreate, actor_id: str) -> dict:
        timestamp = now()
        with self.engine.begin() as conn:
            proposal_row = conn.execute(
                select(db.action_proposals).where(db.action_proposals.c.id == payload.action_proposal_id)
            ).mappings().first()
            if proposal_row is None:
                raise KeyError(payload.action_proposal_id)
            if proposal_row["status"] != "approved":
                raise ValueError("Action proposal must be approved before execution.")
            if proposal_row["action_type"] not in self.safe_action_types:
                raise ValueError("Action type is not in the configured safe execution allowlist.")
            action_payload = load_json(json_value(proposal_row, "payload_json"), {})
            redacted_payload = load_json(json_value(proposal_row, "redacted_payload_json"), {})
            status_value, external_id, error_code, error = self._execute_safe_action(conn, proposal_row, action_payload, timestamp)
            row = {
                "id": new_id("run"),
                "project_id": proposal_row["project_id"],
                "action_proposal_id": proposal_row["id"],
                "action_type": proposal_row["action_type"],
                "status": status_value,
                "executor_id": actor_id,
                "target": str(action_payload.get("target") or action_payload.get("source_id") or action_payload.get("connector_target_id") or ""),
                "payload_json": dump_json(action_payload),
                "redacted_payload_json": dump_json(redacted_payload),
                "external_id": external_id,
                "trace_id": new_id("trace"),
                "error_code": error_code,
                "error": error,
                "started_at": timestamp,
                "finished_at": timestamp,
            }
            conn.execute(insert(db.action_runs).values(**row))
            conn.execute(
                update(db.action_proposals)
                .where(db.action_proposals.c.id == proposal_row["id"])
                .values(status="succeeded" if status_value == "succeeded" else "failed", updated_at=timestamp)
            )
            if proposal_row["attention_item_id"]:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == proposal_row["attention_item_id"])
                    .values(action_run_id=row["id"], status="waiting_for_outcome" if status_value == "succeeded" else "blocked", updated_at=timestamp)
                )
            self._record_activity_event(
                conn,
                project_id=proposal_row["project_id"],
                event_type=f"action.run.{status_value}",
                actor_id=actor_id,
                summary=f"Action run {status_value.replace('_', ' ')} for {proposal_row['title']}.",
                object_refs=[
                    self._activity_ref("action_proposal", proposal_row["id"], proposal_row["title"]),
                    self._activity_ref("action_run", row["id"], proposal_row["action_type"]),
                ],
                payload={"action_run_id": row["id"], "action_proposal_id": proposal_row["id"], "status": status_value},
                lenses=[],
                timestamp=timestamp,
            )
        return self._action_run_from_row(row)

    def create_outcome(self, payload: OutcomeCreate, actor_id: str, *, action_run_id: str | None = None) -> dict:
        timestamp = now()
        occurred_at = payload.occurred_at or timestamp
        project_id = DEFAULT_PROJECT_ID
        with self.engine.begin() as conn:
            if action_run_id:
                run = conn.execute(select(db.action_runs).where(db.action_runs.c.id == action_run_id)).mappings().first()
                if run is None:
                    raise KeyError(action_run_id)
                project_id = run["project_id"]
            row = {
                "id": new_id("outcome"),
                "project_id": project_id,
                "action_run_id": action_run_id,
                "attention_item_id": payload.attention_item_id,
                "alert_id": payload.alert_id,
                "status": payload.status,
                "title": payload.title,
                "summary": payload.summary,
                "result_json": dump_json(payload.result),
                "actor_id": actor_id,
                "occurred_at": occurred_at,
                "created_at": timestamp,
            }
            conn.execute(insert(db.outcomes).values(**row))
            attention_id = payload.attention_item_id
            if action_run_id and not attention_id:
                proposal = conn.execute(
                    select(db.action_proposals)
                    .join(db.action_runs, db.action_runs.c.action_proposal_id == db.action_proposals.c.id)
                    .where(db.action_runs.c.id == action_run_id)
                ).mappings().first()
                attention_id = proposal["attention_item_id"] if proposal else None
            if attention_id:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == attention_id)
                    .values(outcome_id=row["id"], status=self._attention_status_for_outcome(payload.status), updated_at=timestamp, resolved_at=timestamp if payload.status in {"resolved", "succeeded"} else None)
                )
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type=f"outcome.{payload.status}",
                actor_id=actor_id,
                summary=f"Recorded outcome {payload.title}.",
                object_refs=self._phase25_object_refs(self._outcome_from_row(row)),
                payload={"outcome_id": row["id"], "action_run_id": action_run_id, "status": payload.status},
                lenses=[],
                timestamp=timestamp,
            )
        return self._outcome_from_row(row)

    def list_outcomes(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        stmt = select(db.outcomes).where(db.outcomes.c.project_id == DEFAULT_PROJECT_ID)
        if status:
            stmt = stmt.where(db.outcomes.c.status == status)
        stmt = stmt.order_by(db.outcomes.c.created_at.desc(), db.outcomes.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._outcome_from_row(row) for row in conn.execute(stmt).mappings()]

    def create_feedback_event(self, payload: FeedbackEventCreate, actor_id: str) -> dict:
        timestamp = now()
        row = {
            "id": new_id("feedback"),
            "project_id": DEFAULT_PROJECT_ID,
            "outcome_id": payload.outcome_id,
            "action_run_id": payload.action_run_id,
            "attention_item_id": payload.attention_item_id,
            "kind": payload.kind,
            "summary": payload.summary,
            "effect_json": dump_json(payload.effect),
            "proposed_value_json": dump_json(payload.proposed_value) if payload.proposed_value is not None else None,
            "actor_id": actor_id,
            "created_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.feedback_events).values(**row))
            if payload.attention_item_id:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == payload.attention_item_id)
                    .values(feedback_event_id=row["id"], updated_at=timestamp)
                )
            self._record_activity_event(
                conn,
                project_id=DEFAULT_PROJECT_ID,
                event_type="feedback.recorded",
                actor_id=actor_id,
                summary=f"Recorded feedback: {payload.summary}",
                object_refs=self._phase25_object_refs(self._feedback_event_from_row(row)),
                payload={"feedback_event_id": row["id"], "kind": payload.kind, "attention_item_id": payload.attention_item_id},
                lenses=[],
                timestamp=timestamp,
            )
        return self._feedback_event_from_row(row)

    def list_feedback_events(self, *, kind: str | None = None, limit: int = 50) -> list[dict]:
        stmt = select(db.feedback_events).where(db.feedback_events.c.project_id == DEFAULT_PROJECT_ID)
        if kind:
            stmt = stmt.where(db.feedback_events.c.kind == kind)
        stmt = stmt.order_by(db.feedback_events.c.created_at.desc(), db.feedback_events.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._feedback_event_from_row(row) for row in conn.execute(stmt).mappings()]
