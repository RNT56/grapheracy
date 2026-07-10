from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, select, update

from graphview_api import db
from graphview_api.json_compat import json_value
from graphview_api.redaction import redact_sensitive_text


DEFAULT_PROJECT_ID = "project-default"
EXTERNAL_ACTION_TYPES = {"create_external_ticket", "create_notification", "trigger_workflow"}
SENSITIVE_PAYLOAD_KEYS = {
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
}


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
            row = conn.execute(select(db.action_proposals).where(and_(*conditions))).mappings().first()
        return self._action_proposal_from_row(row) if row else None

    def action_proposal_execution_bundle(
        self,
        action_proposal_id: str,
        *,
        project_id: str | None = None,
    ) -> tuple[dict, dict] | None:
        conditions = [db.action_proposals.c.id == action_proposal_id]
        if project_id is not None:
            conditions.append(db.action_proposals.c.project_id == project_id)
        with self.engine.begin() as conn:
            row = conn.execute(select(db.action_proposals).where(and_(*conditions))).mappings().first()
        if row is None:
            return None
        return self._action_proposal_from_row(row), json.loads(json_value(row, "payload_json"))

    def get_action_run(self, action_run_id: str, *, project_id: str | None = None) -> dict | None:
        conditions = [db.action_runs.c.id == action_run_id]
        if project_id is not None:
            conditions.append(db.action_runs.c.project_id == project_id)
        with self.engine.begin() as conn:
            row = conn.execute(select(db.action_runs).where(and_(*conditions))).mappings().first()
        return self._action_run_from_row(row) if row else None

    def begin_external_action_run(
        self,
        action_proposal_id: str,
        *,
        actor_id: str,
        trace_id: str | None = None,
    ) -> dict:
        timestamp = _now()
        with self.engine.begin() as conn:
            proposal = (
                conn.execute(
                    select(db.action_proposals)
                    .where(db.action_proposals.c.id == action_proposal_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if proposal is None:
                raise KeyError(action_proposal_id)
            if proposal["action_type"] not in self.safe_action_types:
                raise ValueError("Action type is not in the configured safe execution allowlist.")
            if proposal["action_type"] not in EXTERNAL_ACTION_TYPES:
                raise ValueError("Action type is not an external adapter action.")
            existing = (
                conn.execute(
                    select(db.action_runs)
                    .where(db.action_runs.c.action_proposal_id == action_proposal_id)
                    .order_by(db.action_runs.c.started_at.desc())
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if existing is not None and existing["status"] == "succeeded":
                return self._action_run_from_row(existing)
            if proposal["status"] not in {"approved", "queued", "running", "failed", "cancelled"}:
                raise ValueError("Action proposal must be approved before execution.")

            payload = json.loads(json_value(proposal, "payload_json"))
            if existing is None:
                row = {
                    "id": _new_id("run"),
                    "project_id": proposal["project_id"],
                    "action_proposal_id": proposal["id"],
                    "action_type": proposal["action_type"],
                    "status": "running",
                    "executor_id": actor_id,
                    "target": str(
                        payload.get("target")
                        or payload.get("to")
                        or payload.get("destination")
                        or payload.get("repository")
                        or ""
                    ),
                    "payload_json": json.dumps(payload, sort_keys=True),
                    "redacted_payload_json": json_value(proposal, "redacted_payload_json"),
                    "external_id": None,
                    "trace_id": trace_id or _new_id("trace"),
                    "error_code": None,
                    "error": None,
                    "started_at": timestamp,
                    "finished_at": None,
                }
                conn.execute(insert(db.action_runs).values(**row))
                event_type = "action.run.started"
                summary = f"External action started for {proposal['title']}."
            else:
                conn.execute(
                    update(db.action_runs)
                    .where(db.action_runs.c.id == existing["id"])
                    .values(
                        status="running",
                        executor_id=actor_id,
                        error_code=None,
                        error=None,
                        finished_at=None,
                    )
                )
                row = (
                    conn.execute(select(db.action_runs).where(db.action_runs.c.id == existing["id"]))
                    .mappings()
                    .one()
                )
                event_type = "action.run.resumed"
                summary = f"External action resumed for {proposal['title']}."

            conn.execute(
                update(db.action_proposals)
                .where(db.action_proposals.c.id == proposal["id"])
                .values(status="running", updated_at=timestamp)
            )
            if proposal["attention_item_id"]:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == proposal["attention_item_id"])
                    .values(action_run_id=row["id"], status="waiting_for_action", updated_at=timestamp)
                )
            self._record_external_action_activity(
                conn,
                proposal=proposal,
                action_run_id=row["id"],
                event_type=event_type,
                actor_id=actor_id,
                summary=summary,
                status="running",
                timestamp=timestamp,
            )
        return self._action_run_from_row(row)

    def complete_external_action_run(
        self,
        action_run_id: str,
        *,
        actor_id: str,
        external_id: str,
        adapter_metadata: dict,
    ) -> dict:
        timestamp = _now()
        with self.engine.begin() as conn:
            run = (
                conn.execute(
                    select(db.action_runs).where(db.action_runs.c.id == action_run_id).with_for_update()
                )
                .mappings()
                .first()
            )
            if run is None:
                raise KeyError(action_run_id)
            if run["status"] == "succeeded":
                return self._action_run_from_row(run)
            proposal = (
                conn.execute(
                    select(db.action_proposals).where(
                        db.action_proposals.c.id == run["action_proposal_id"]
                    )
                )
                .mappings()
                .one()
            )
            conn.execute(
                update(db.action_runs)
                .where(db.action_runs.c.id == action_run_id)
                .values(
                    status="succeeded",
                    external_id=external_id,
                    error_code=None,
                    error=None,
                    finished_at=timestamp,
                )
            )
            conn.execute(
                update(db.action_proposals)
                .where(db.action_proposals.c.id == proposal["id"])
                .values(status="succeeded", updated_at=timestamp)
            )
            if proposal["attention_item_id"]:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == proposal["attention_item_id"])
                    .values(action_run_id=action_run_id, status="waiting_for_outcome", updated_at=timestamp)
                )
            self._record_external_action_activity(
                conn,
                proposal=proposal,
                action_run_id=action_run_id,
                event_type="action.run.succeeded",
                actor_id=actor_id,
                summary=f"External action succeeded for {proposal['title']}.",
                status="succeeded",
                timestamp=timestamp,
                extra_payload={"adapter": self._redact_payload(adapter_metadata)},
            )
            updated = (
                conn.execute(select(db.action_runs).where(db.action_runs.c.id == action_run_id))
                .mappings()
                .one()
            )
        return self._action_run_from_row(updated)

    def transition_external_action_run(
        self,
        action_proposal_id: str,
        *,
        status: str,
        actor_id: str,
        error_code: str,
        error: str,
    ) -> dict | None:
        if status not in {"queued", "failed", "cancelled"}:
            raise ValueError("External action transition must be queued, failed, or cancelled")
        timestamp = _now()
        with self.engine.begin() as conn:
            proposal = (
                conn.execute(
                    select(db.action_proposals).where(db.action_proposals.c.id == action_proposal_id)
                )
                .mappings()
                .first()
            )
            run = (
                conn.execute(
                    select(db.action_runs)
                    .where(db.action_runs.c.action_proposal_id == action_proposal_id)
                    .order_by(db.action_runs.c.started_at.desc())
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if proposal is None or run is None:
                return None
            if run["status"] == "succeeded":
                return self._action_run_from_row(run)
            redacted_error = redact_sensitive_text(error)[:2000]
            conn.execute(
                update(db.action_runs)
                .where(db.action_runs.c.id == run["id"])
                .values(
                    status=status,
                    error_code=error_code[:80],
                    error=redacted_error,
                    finished_at=timestamp if status in {"failed", "cancelled"} else None,
                )
            )
            conn.execute(
                update(db.action_proposals)
                .where(db.action_proposals.c.id == action_proposal_id)
                .values(status=status, updated_at=timestamp)
            )
            if proposal["attention_item_id"]:
                conn.execute(
                    update(db.attention_items)
                    .where(db.attention_items.c.id == proposal["attention_item_id"])
                    .values(
                        action_run_id=run["id"],
                        status="waiting_for_action" if status == "queued" else "blocked",
                        updated_at=timestamp,
                    )
                )
            event_suffix = "retry_scheduled" if status == "queued" else status
            self._record_external_action_activity(
                conn,
                proposal=proposal,
                action_run_id=run["id"],
                event_type=f"action.run.{event_suffix}",
                actor_id=actor_id,
                summary=f"External action {event_suffix.replace('_', ' ')} for {proposal['title']}.",
                status=status,
                timestamp=timestamp,
                extra_payload={"error_code": error_code[:80]},
            )
            updated = (
                conn.execute(select(db.action_runs).where(db.action_runs.c.id == run["id"]))
                .mappings()
                .one()
            )
        return self._action_run_from_row(updated)

    def list_action_runs(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> list[dict]:
        stmt = select(db.action_runs).where(db.action_runs.c.project_id == project_id)
        if status:
            stmt = stmt.where(db.action_runs.c.status == status)
        stmt = stmt.order_by(db.action_runs.c.started_at.desc(), db.action_runs.c.id.desc()).limit(
            min(100, max(1, limit))
        )
        with self.engine.begin() as conn:
            return [self._action_run_from_row(row) for row in conn.execute(stmt).mappings()]

    def _record_external_action_activity(
        self,
        conn,
        *,
        proposal,
        action_run_id: str,
        event_type: str,
        actor_id: str,
        summary: str,
        status: str,
        timestamp: datetime,
        extra_payload: dict | None = None,
    ) -> None:
        self._record_activity_event(
            conn,
            project_id=proposal["project_id"],
            event_type=event_type,
            actor_id=actor_id,
            summary=summary,
            object_refs=[
                self._activity_ref("action_proposal", proposal["id"], proposal["title"]),
                self._activity_ref("action_run", action_run_id, proposal["action_type"]),
            ],
            payload={
                "action_run_id": action_run_id,
                "action_proposal_id": proposal["id"],
                "status": status,
                **(extra_payload or {}),
            },
            lenses=[],
            timestamp=timestamp,
        )

    def _default_action_safety(self, action_type: str, approval_required: bool) -> dict:
        external = action_type in EXTERNAL_ACTION_TYPES
        graph_mutation = action_type in {
            "mark_source_stale",
            "mark_source_refreshed",
            "create_graph_proposal",
            "connector_sync",
        }
        return {
            "safety_level": (
                "external_side_effect" if external else ("graph_mutation" if graph_mutation else "internal_safe")
            ),
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
