from __future__ import annotations

import json

from graphview_api.json_compat import json_value
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, select, update

from graphview_api import db


DEFAULT_PROJECT_ID = "project-default"
SENSITIVE_PAYLOAD_KEYS = {"token", "secret", "password", "api_key", "apikey", "authorization", "credential", "credentials"}


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


class ActionRepositoryMixin:
    def get_action_proposal(self, action_proposal_id: str, *, project_id: str | None = None) -> dict | None:
        conditions = [db.action_proposals.c.id == action_proposal_id]
        if project_id is not None:
            conditions.append(db.action_proposals.c.project_id == project_id)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.action_proposals).where(and_(*conditions))
            ).mappings().first()
        return self._action_proposal_from_row(row) if row else None

    def action_proposal_execution_bundle(self, action_proposal_id: str, *, project_id: str | None = None) -> tuple[dict, dict] | None:
        conditions = [db.action_proposals.c.id == action_proposal_id]
        if project_id is not None:
            conditions.append(db.action_proposals.c.project_id == project_id)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.action_proposals).where(and_(*conditions))
            ).mappings().first()
        if row is None:
            return None
        return self._action_proposal_from_row(row), json.loads(json_value(row, "payload_json"))

    def record_external_action_run(
        self,
        action_proposal_id: str,
        *,
        actor_id: str,
        external_id: str,
        adapter_metadata: dict,
    ) -> dict:
        timestamp = _now()
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(db.action_runs)
                .where(and_(db.action_runs.c.action_proposal_id == action_proposal_id, db.action_runs.c.status == "succeeded"))
                .order_by(db.action_runs.c.started_at.desc())
            ).mappings().first()
            if existing is not None:
                return self._action_run_from_row(existing)
            proposal = conn.execute(select(db.action_proposals).where(db.action_proposals.c.id == action_proposal_id)).mappings().first()
            if proposal is None:
                raise KeyError(action_proposal_id)
            if proposal["status"] != "approved":
                raise ValueError("Action proposal must be approved before execution.")
            if proposal["action_type"] not in self.safe_action_types:
                raise ValueError("Action type is not in the configured safe execution allowlist.")
            if proposal["action_type"] not in {"create_external_ticket", "create_notification", "trigger_workflow"}:
                raise ValueError("Action type is not an external adapter action.")
            payload = json.loads(json_value(proposal, "payload_json"))
            row = {
                "id": _new_id("run"),
                "project_id": proposal["project_id"],
                "action_proposal_id": proposal["id"],
                "action_type": proposal["action_type"],
                "status": "succeeded",
                "executor_id": actor_id,
                "target": str(payload.get("target") or payload.get("to") or payload.get("destination") or payload.get("repository") or ""),
                "payload_json": json.dumps(payload, sort_keys=True),
                "redacted_payload_json": json_value(proposal, "redacted_payload_json"),
                "external_id": external_id,
                "trace_id": _new_id("trace"),
                "error_code": None,
                "error": None,
                "started_at": timestamp,
                "finished_at": timestamp,
            }
            conn.execute(insert(db.action_runs).values(**row))
            conn.execute(update(db.action_proposals).where(db.action_proposals.c.id == proposal["id"]).values(status="succeeded", updated_at=timestamp))
            if proposal["attention_item_id"]:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == proposal["attention_item_id"])
                    .values(action_run_id=row["id"], status="waiting_for_outcome", updated_at=timestamp)
                )
            self._record_activity_event(
                conn,
                project_id=proposal["project_id"],
                event_type="action.run.succeeded",
                actor_id=actor_id,
                summary=f"External action succeeded for {proposal['title']}.",
                object_refs=[
                    self._activity_ref("action_proposal", proposal["id"], proposal["title"]),
                    self._activity_ref("action_run", row["id"], proposal["action_type"]),
                ],
                payload={
                    "action_run_id": row["id"],
                    "action_proposal_id": proposal["id"],
                    "status": "succeeded",
                    "adapter": self._redact_payload(adapter_metadata),
                },
                lenses=[],
                timestamp=timestamp,
            )
        return self._action_run_from_row(row)

    def list_action_runs(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        stmt = select(db.action_runs).where(db.action_runs.c.project_id == DEFAULT_PROJECT_ID)
        if status:
            stmt = stmt.where(db.action_runs.c.status == status)
        stmt = stmt.order_by(db.action_runs.c.started_at.desc(), db.action_runs.c.id.desc()).limit(min(100, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._action_run_from_row(row) for row in conn.execute(stmt).mappings()]

    def _default_action_safety(self, action_type: str, approval_required: bool) -> dict:
        external = action_type in {"create_external_ticket", "create_notification", "trigger_workflow"}
        graph_mutation = action_type in {"mark_source_stale", "mark_source_refreshed", "create_graph_proposal", "connector_sync"}
        return {
            "safety_level": "external_side_effect" if external else ("graph_mutation" if graph_mutation else "internal_safe"),
            "mutates_graphview": graph_mutation,
            "calls_external_system": external,
            "transfers_private_content": external,
            "approval_required": approval_required or external or graph_mutation,
        }

    def _redact_payload(self, value):
        if isinstance(value, dict):
            return {
                key: "[redacted]" if key.lower() in SENSITIVE_PAYLOAD_KEYS else self._redact_payload(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_payload(item) for item in value]
        if isinstance(value, str):
            return self._redact_context_text(value)
        return value
