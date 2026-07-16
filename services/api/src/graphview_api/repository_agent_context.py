from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, or_, select, update

from graphview_api import db
from graphview_api.json_compat import json_value
from graphview_api.schemas import (
    AgentContextClientCreate,
    AgentContextEventBatchCreate,
    AgentContextSessionCreate,
    AgentContextSessionUpdate,
)

DEFAULT_PROJECT_ID = "project-default"
AGENT_CONTEXT_CAPTURE_SCOPE = "context:capture"


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


class AgentContextRepositoryMixin:
    """Active-context clients, sessions, ordered events, retained content, replay, and purge."""

    def create_agent_context_client(self, payload: AgentContextClientCreate, *, actor_id: str) -> dict:
        timestamp = now()
        token = f"gvctx_{secrets.token_urlsafe(32)}"
        scopes = [AGENT_CONTEXT_CAPTURE_SCOPE]
        client_row = {
            "id": new_id("ctxclient"),
            "project_id": DEFAULT_PROJECT_ID,
            "display_name": payload.display_name,
            "runtime_kind": payload.runtime_kind,
            "status": "active",
            "created_by": actor_id,
            "token_hash": self._agent_context_token_hash(token),
            "scopes_json": dump_json(scopes),
            "settings_json": dump_json(payload.settings),
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_seen_at": None,
            "revoked_at": None,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_context_clients).values(**client_row))
            self._record_activity_event(
                conn,
                project_id=DEFAULT_PROJECT_ID,
                event_type="agent_context.client_created",
                actor_id=actor_id,
                summary=f"Created active context connector {payload.display_name}.",
                object_refs=[self._activity_ref("agent_context_client", client_row["id"], payload.display_name)],
                payload={"client_id": client_row["id"], "runtime_kind": payload.runtime_kind},
                lenses=[],
                timestamp=timestamp,
            )
        return {"client": self._agent_context_client_from_row(client_row), "token": token}

    def authenticate_agent_context_token(self, token: str) -> dict | None:
        if not token.startswith("gvctx_"):
            return None
        token_hash = self._agent_context_token_hash(token)
        timestamp = now()
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_context_clients).where(
                    and_(
                        db.agent_context_clients.c.token_hash == token_hash,
                        db.agent_context_clients.c.status == "active",
                        db.agent_context_clients.c.revoked_at.is_(None),
                    )
                )
            ).mappings().first()
            if row is None:
                return None
            conn.execute(
                update(db.agent_context_clients)
                .where(db.agent_context_clients.c.id == row["id"])
                .values(last_seen_at=timestamp, updated_at=timestamp)
            )
            client = self._agent_context_client_from_row(row)
            client["last_seen_at"] = timestamp
            return client

    def list_agent_context_clients(self) -> list[dict]:
        with self.engine.begin() as conn:
            return [
                self._agent_context_client_from_row(row)
                for row in conn.execute(
                    select(db.agent_context_clients)
                    .where(db.agent_context_clients.c.project_id == DEFAULT_PROJECT_ID)
                    .order_by(db.agent_context_clients.c.created_at.desc(), db.agent_context_clients.c.id.desc())
                ).mappings()
            ]

    def create_agent_context_session(self, payload: AgentContextSessionCreate, *, client: dict) -> dict:
        timestamp = now()
        started_at = payload.started_at or timestamp
        session_row = {
            "id": new_id("ctxsession"),
            "project_id": client["project_id"],
            "client_id": client["id"],
            "runtime_kind": payload.runtime_kind or client["runtime_kind"],
            "authority": payload.authority,
            "status": "running",
            "title": payload.title,
            "workspace_root": self._safe_context_path(payload.workspace_root),
            "repository_uri": payload.repository_uri,
            "branch": payload.branch,
            "commit_sha": payload.commit_sha,
            "metadata_json": dump_json(self._redact_payload(payload.metadata)),
            "started_at": started_at,
            "ended_at": None,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_context_sessions).values(**session_row))
            self._record_activity_event(
                conn,
                project_id=session_row["project_id"],
                event_type="agent_context.session_started",
                actor_id=client["id"],
                summary=f"Started active context session {payload.title}.",
                object_refs=[
                    self._activity_ref("agent_context_session", session_row["id"], payload.title),
                    self._activity_ref("agent_context_client", client["id"], client["display_name"]),
                ],
                payload={
                    "session_id": session_row["id"],
                    "client_id": client["id"],
                    "runtime_kind": session_row["runtime_kind"],
                    "authority": session_row["authority"],
                },
                lenses=[],
                timestamp=timestamp,
            )
        return self._agent_context_session_from_row(session_row)

    def update_agent_context_session(self, session_id: str, payload: AgentContextSessionUpdate, *, client: dict) -> dict:
        timestamp = now()
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_context_sessions).where(db.agent_context_sessions.c.id == session_id)
            ).mappings().first()
            if row is None or row["client_id"] != client["id"]:
                raise KeyError(session_id)
            values: dict[str, object] = {"updated_at": timestamp}
            if payload.status is not None:
                values["status"] = payload.status
            if payload.title is not None:
                values["title"] = payload.title
            if payload.branch is not None:
                values["branch"] = payload.branch
            if payload.commit_sha is not None:
                values["commit_sha"] = payload.commit_sha
            if payload.metadata is not None:
                current_metadata = load_json(json_value(row, "metadata_json"), {})
                current_metadata.update(self._redact_payload(payload.metadata))
                values["metadata_json"] = dump_json(current_metadata)
            if payload.ended_at is not None:
                values["ended_at"] = payload.ended_at
            if payload.status in {"completed", "failed", "cancelled"} and "ended_at" not in values:
                values["ended_at"] = timestamp
            conn.execute(update(db.agent_context_sessions).where(db.agent_context_sessions.c.id == session_id).values(**values))
            updated = conn.execute(
                select(db.agent_context_sessions).where(db.agent_context_sessions.c.id == session_id)
            ).mappings().one()
            if values.get("status") in {"completed", "failed", "cancelled"}:
                self._record_activity_event(
                    conn,
                    project_id=row["project_id"],
                    event_type=f"agent_context.session_{values['status']}",
                    actor_id=client["id"],
                    summary=f"Marked active context session {values['status']}.",
                    object_refs=[self._activity_ref("agent_context_session", session_id, values.get("title") or row["title"])],
                    payload={"session_id": session_id, "status": values["status"]},
                    lenses=[],
                    timestamp=timestamp,
                )
            return self._agent_context_session_from_row(updated)

    def list_agent_context_sessions(self, *, limit: int = 50) -> list[dict]:
        normalized_limit = min(100, max(1, limit))
        with self.engine.begin() as conn:
            return [
                self._agent_context_session_from_row(row)
                for row in conn.execute(
                    select(db.agent_context_sessions)
                    .where(db.agent_context_sessions.c.project_id == DEFAULT_PROJECT_ID)
                    .order_by(db.agent_context_sessions.c.updated_at.desc(), db.agent_context_sessions.c.id.desc())
                    .limit(normalized_limit)
                ).mappings()
            ]

    def get_agent_context_session(self, session_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_context_sessions).where(db.agent_context_sessions.c.id == session_id)
            ).mappings().first()
            return self._agent_context_session_from_row(row) if row else None

    def ingest_agent_context_events(self, payload: AgentContextEventBatchCreate, *, client: dict) -> dict:
        timestamp = now()
        accepted: list[dict] = []
        duplicate_count = 0
        with self.engine.begin() as conn:
            session_row = conn.execute(
                select(db.agent_context_sessions).where(db.agent_context_sessions.c.id == payload.session_id)
            ).mappings().first()
            if session_row is None or session_row["client_id"] != client["id"]:
                raise KeyError(payload.session_id)
            session = self._agent_context_session_from_row(session_row)
            for event_payload in payload.events:
                existing = conn.execute(
                    select(db.agent_context_events.c.id).where(
                        or_(
                            and_(
                                db.agent_context_events.c.session_id == payload.session_id,
                                db.agent_context_events.c.client_event_id == event_payload.client_event_id,
                            ),
                            and_(
                                db.agent_context_events.c.session_id == payload.session_id,
                                db.agent_context_events.c.sequence == event_payload.sequence,
                            ),
                        )
                    )
                ).first()
                if existing:
                    duplicate_count += 1
                    continue

                artifact_row = None
                blob_row = None
                if event_payload.artifact is not None:
                    self._validate_agent_context_path_policy(event_payload.artifact.path, session=session, client=client)
                    self._validate_agent_context_path_policy(event_payload.artifact.uri, session=session, client=client)
                    artifact_row = self._agent_context_artifact_row(
                        project_id=session_row["project_id"],
                        session_id=payload.session_id,
                        payload=event_payload.artifact,
                        timestamp=timestamp,
                    )
                    conn.execute(insert(db.agent_context_artifacts).values(**artifact_row))
                if event_payload.content is not None:
                    blob_row = self._agent_context_blob_row(
                        project_id=session_row["project_id"],
                        session_id=payload.session_id,
                        artifact_id=artifact_row["id"] if artifact_row else None,
                        payload=event_payload.content,
                        timestamp=timestamp,
                    )
                    conn.execute(insert(db.agent_context_blobs).values(**blob_row))

                authority = event_payload.authority or session_row["authority"]
                summary = event_payload.summary or self._agent_context_event_summary(event_payload.event_kind, artifact_row)
                redacted_payload = self._redact_payload(event_payload.payload)
                object_refs = [ref.model_dump(exclude_none=True) for ref in event_payload.object_refs]
                occurred_at = event_payload.occurred_at or timestamp
                checksum = hashlib.sha256(
                    dump_json(
                        {
                            "artifact_id": artifact_row["id"] if artifact_row else None,
                            "authority": authority,
                            "blob_id": blob_row["id"] if blob_row else None,
                            "client_event_id": event_payload.client_event_id,
                            "event_kind": event_payload.event_kind,
                            "object_refs": object_refs,
                            "occurred_at": occurred_at,
                            "payload": redacted_payload,
                            "sequence": event_payload.sequence,
                            "session_id": payload.session_id,
                            "summary": summary,
                        }
                    ).encode("utf-8")
                ).hexdigest()
                event_row = {
                    "id": new_id("ctxevent"),
                    "project_id": session_row["project_id"],
                    "session_id": payload.session_id,
                    "client_event_id": event_payload.client_event_id,
                    "sequence": event_payload.sequence,
                    "event_kind": event_payload.event_kind,
                    "authority": authority,
                    "status": "accepted",
                    "summary": summary,
                    "checksum": checksum,
                    "artifact_id": artifact_row["id"] if artifact_row else None,
                    "blob_id": blob_row["id"] if blob_row else None,
                    "payload_json": dump_json(redacted_payload),
                    "object_refs_json": dump_json(object_refs),
                    "occurred_at": occurred_at,
                    "received_at": timestamp,
                }
                conn.execute(insert(db.agent_context_events).values(**event_row))
                self._record_activity_event(
                    conn,
                    project_id=session_row["project_id"],
                    event_type=f"agent_context.{event_payload.event_kind}",
                    actor_id=client["id"],
                    summary=summary,
                    object_refs=[
                        self._activity_ref("agent_context_session", payload.session_id, session_row["title"]),
                        self._activity_ref("agent_context_event", event_row["id"], event_payload.event_kind),
                        *(
                            [self._activity_ref("agent_context_artifact", artifact_row["id"], artifact_row["title"])]
                            if artifact_row
                            else []
                        ),
                    ],
                    payload={
                        "session_id": payload.session_id,
                        "event_id": event_row["id"],
                        "client_event_id": event_payload.client_event_id,
                        "event_kind": event_payload.event_kind,
                        "authority": authority,
                        "artifact_id": artifact_row["id"] if artifact_row else None,
                        "blob_id": blob_row["id"] if blob_row else None,
                    },
                    lenses=[],
                    timestamp=timestamp,
                )
                accepted.append(self._agent_context_event_from_row(event_row))

            conn.execute(
                update(db.agent_context_sessions)
                .where(db.agent_context_sessions.c.id == payload.session_id)
                .values(updated_at=timestamp)
            )
        return {
            "session": session,
            "accepted_count": len(accepted),
            "duplicate_count": duplicate_count,
            "rejected_count": 0,
            "events": accepted,
        }

    def list_agent_context_events(self, session_id: str, *, limit: int = 100, since_sequence: int | None = None) -> list[dict]:
        normalized_limit = min(500, max(1, limit))
        stmt = (
            select(db.agent_context_events)
            .where(db.agent_context_events.c.session_id == session_id)
            .order_by(db.agent_context_events.c.sequence.asc(), db.agent_context_events.c.id.asc())
            .limit(normalized_limit)
        )
        if since_sequence is not None:
            stmt = stmt.where(db.agent_context_events.c.sequence > since_sequence)
        with self.engine.begin() as conn:
            return [self._agent_context_event_from_row(row) for row in conn.execute(stmt).mappings()]

    def agent_context_event_sequence(self, session_id: str, event_id: str) -> int | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_context_events.c.sequence).where(
                    and_(
                        db.agent_context_events.c.session_id == session_id,
                        db.agent_context_events.c.id == event_id,
                    )
                )
            ).first()
            return int(row.sequence) if row is not None else None

    def agent_context_graph(self, session_id: str) -> dict:
        with self.engine.begin() as conn:
            session_row = conn.execute(
                select(db.agent_context_sessions).where(db.agent_context_sessions.c.id == session_id)
            ).mappings().first()
            if session_row is None:
                raise KeyError(session_id)
            session = self._agent_context_session_from_row(session_row)
            artifacts = [
                self._agent_context_artifact_from_row(row)
                for row in conn.execute(
                    select(db.agent_context_artifacts)
                    .where(db.agent_context_artifacts.c.session_id == session_id)
                    .order_by(db.agent_context_artifacts.c.created_at.asc(), db.agent_context_artifacts.c.id.asc())
                ).mappings()
            ]
            events = [
                self._agent_context_event_from_row(row)
                for row in conn.execute(
                    select(db.agent_context_events)
                    .where(db.agent_context_events.c.session_id == session_id)
                    .order_by(db.agent_context_events.c.sequence.asc(), db.agent_context_events.c.id.asc())
                ).mappings()
            ]

        nodes = [
            {
                "id": session["id"],
                "kind": "session",
                "label": session["title"],
                "authority": session["authority"],
                "metadata": {
                    "runtime_kind": session["runtime_kind"],
                    "status": session["status"],
                    "repository_uri": session.get("repository_uri"),
                    "branch": session.get("branch"),
                },
            }
        ]
        nodes.extend(
            {
                "id": artifact["id"],
                "kind": artifact["kind"],
                "label": artifact["title"],
                "authority": None,
                "metadata": {
                    "path": artifact.get("path"),
                    "uri": artifact.get("uri"),
                    "content_type": artifact["content_type"],
                    "checksum": artifact.get("checksum"),
                },
            }
            for artifact in artifacts
        )
        nodes.extend(
            {
                "id": event["id"],
                "kind": "event",
                "label": event["event_kind"].replace("_", " "),
                "authority": event["authority"],
                "metadata": {"sequence": event["sequence"], "summary": event["summary"]},
            }
            for event in events
        )
        edges = []
        for event in events:
            edges.append(
                {
                    "id": f"ctxedge-{session_id}-{event['id']}",
                    "source_id": session_id,
                    "target_id": event["id"],
                    "relation": "contains",
                    "observed": True,
                    "metadata": {"event_kind": event["event_kind"], "authority": event["authority"]},
                }
            )
            if event.get("artifact_id"):
                edges.append(
                    {
                        "id": f"ctxedge-{event['id']}-{event['artifact_id']}",
                        "source_id": event["id"],
                        "target_id": event["artifact_id"],
                        "relation": self._agent_context_relation_for_event(event["event_kind"]),
                        "observed": event["authority"] != "passive_reconciled",
                        "metadata": {"event_kind": event["event_kind"], "authority": event["authority"]},
                    }
                )
        return {"session": session, "nodes": nodes, "edges": edges, "artifacts": artifacts, "events": events}

    def agent_context_blob_content(self, blob_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(db.agent_context_blobs).where(db.agent_context_blobs.c.id == blob_id)).mappings().first()
            if row is None:
                return None
            blob = self._agent_context_blob_from_row(row)
            text_content = None
            envelope = self._agent_context_blob_envelope(row)
            if envelope:
                text_content = self._decrypt_agent_context_text(envelope)
            return {"blob": blob, "text": text_content}

    def agent_context_artifact_content(self, artifact_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_context_blobs)
                .where(db.agent_context_blobs.c.artifact_id == artifact_id)
                .order_by(db.agent_context_blobs.c.created_at.desc(), db.agent_context_blobs.c.id.desc())
            ).mappings().first()
            if row is None:
                return None
            blob = self._agent_context_blob_from_row(row)
            envelope = self._agent_context_blob_envelope(row)
            text_content = self._decrypt_agent_context_text(envelope) if envelope else None
            return {"blob": blob, "text": text_content}

    def run_agent_context_retention(self) -> dict:
        timestamp = now()
        with self.engine.begin() as conn:
            expired_rows = list(
                conn.execute(
                    select(
                        db.agent_context_blobs.c.id,
                        db.agent_context_blobs.c.metadata_json,
                        db.agent_context_blobs.c.redaction_status,
                        db.agent_context_blobs.c.object_key,
                    ).where(
                        and_(
                            db.agent_context_blobs.c.project_id == DEFAULT_PROJECT_ID,
                            db.agent_context_blobs.c.expires_at.is_not(None),
                            db.agent_context_blobs.c.expires_at <= timestamp,
                            or_(
                                db.agent_context_blobs.c.encrypted_content.is_not(None),
                                db.agent_context_blobs.c.object_key.is_not(None),
                            ),
                        )
                    )
                ).mappings()
            )
            expired_ids = [row["id"] for row in expired_rows]
            for row in expired_rows:
                if row["object_key"] and self.object_store is not None:
                    self.object_store.delete(str(row["object_key"]))
                metadata = load_json(json_value(row, "metadata_json"), {})
                metadata["retention_purged_at"] = timestamp.isoformat()
                metadata["previous_redaction_status"] = row["redaction_status"]
                conn.execute(
                    update(db.agent_context_blobs)
                    .where(db.agent_context_blobs.c.id == row["id"])
                    .values(
                        encrypted_content=None,
                        object_key=None,
                        redaction_status="metadata_only",
                        encryption_status="metadata_only",
                        metadata_json=dump_json(metadata),
                    )
                )
            retained_count = conn.execute(
                select(db.agent_context_blobs.c.id).where(db.agent_context_blobs.c.project_id == DEFAULT_PROJECT_ID)
            ).all()
            self._record_activity_event(
                conn,
                project_id=DEFAULT_PROJECT_ID,
                event_type="agent_context.retention_run",
                actor_id="system-retention",
                summary=f"Purged {len(expired_ids)} expired active context blobs.",
                object_refs=[],
                payload={"purged_blob_count": len(expired_ids), "retained_blob_count": len(retained_count)},
                lenses=[],
                timestamp=timestamp,
            )
        return {"purged_blob_count": len(expired_ids), "retained_blob_count": len(retained_count), "generated_at": timestamp}
