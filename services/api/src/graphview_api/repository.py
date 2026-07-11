from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Engine, and_, delete, insert, or_, select, text, update

from graphview_api import db
from graphview_api.action_policy import normalize_safe_action_types
from graphview_api.connectors import NormalizedSourceDocument, stable_id
from graphview_api.lenses import normalize_graph_lens
from graphview_api.json_compat import json_value, normalize_json_row
from graphview_api.repository_actions import ActionRepositoryMixin
from graphview_api.repository_ai import AiPlanningRepositoryMixin
from graphview_api.repository_agent_context import AgentContextRepositoryMixin
from graphview_api.repository_connectors import ConnectorRepositoryMixin
from graphview_api.repository_graph import GraphReadRepositoryMixin
from graphview_api.repository_ingestion import IngestionRepositoryMixin
from graphview_api.repository_nervous_system import NervousSystemRepositoryMixin
from graphview_api.repository_review import ReviewRepositoryMixin
from graphview_api.repository_serialization import RepositorySerializationMixin
from graphview_api.repository_secrets import SecretRepositoryMixin
from graphview_api.repository_sources import SourceCatalogRepositoryMixin
from graphview_api.redaction import redact_sensitive_text
from graphview_api.schemas import (
    ExportBundle,
    SignalCreate,
)

DEFAULT_PROJECT_ID = "project-default"
GRAPH_LENSES = ("research", "engineering", "ops")
SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
SENSITIVE_PAYLOAD_KEYS = {"token", "secret", "password", "api_key", "apikey", "authorization", "credential", "credentials"}
AGENT_CONTEXT_CAPTURE_SCOPE = "context:capture"
AGENT_CONTEXT_DEFAULT_DENIED_PATTERNS = (".env", "id_rsa", "id_ed25519", ".pem", ".p12")


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


class GraphRepository(
    ActionRepositoryMixin,
    AiPlanningRepositoryMixin,
    AgentContextRepositoryMixin,
    ConnectorRepositoryMixin,
    GraphReadRepositoryMixin,
    IngestionRepositoryMixin,
    NervousSystemRepositoryMixin,
    ReviewRepositoryMixin,
    SecretRepositoryMixin,
    SourceCatalogRepositoryMixin,
    RepositorySerializationMixin,
):
    def __init__(
        self,
        engine: Engine,
        *,
        secret_key: str = "local-dev-graphview-secret",
        auto_commit_threshold: float = 0.92,
        safe_action_types: list[str] | tuple[str, ...] | set[str] | frozenset[str] | str | None = None,
        agent_context_max_blob_bytes: int = 512_000,
        agent_context_retention_days: int = 30,
        secret_store=None,
        object_store=None,
    ):
        self.engine = engine
        self.secret_key = secret_key
        self.auto_commit_threshold = auto_commit_threshold
        self.safe_action_types = normalize_safe_action_types(safe_action_types)
        self.agent_context_max_blob_bytes = max(0, agent_context_max_blob_bytes)
        self.agent_context_retention_days = max(1, agent_context_retention_days)
        self.secret_store = secret_store
        self.object_store = object_store

    def initialize(self, *, create_schema: bool = True) -> None:
        if create_schema:
            db.metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            self._ensure_sqlite_columns(conn)
            existing = conn.execute(
                select(db.graph_projects.c.id).where(db.graph_projects.c.id == DEFAULT_PROJECT_ID)
            ).first()
            if existing is None:
                timestamp = now()
                conn.execute(
                    insert(db.graph_projects).values(
                        id=DEFAULT_PROJECT_ID,
                        name="Research Knowledge Map",
                        description="Default internal knowledge graph project.",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            settings = conn.execute(
                select(db.graph_settings.c.project_id).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).first()
            if settings is None:
                timestamp = now()
                conn.execute(
                    insert(db.graph_settings).values(
                        project_id=DEFAULT_PROJECT_ID,
                        llm_enabled=False,
                        llm_provider="openai-compatible",
                        llm_model=None,
                        auto_commit_threshold=self.auto_commit_threshold,
                        settings_json=dump_json({}),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            self._rotate_legacy_secrets(conn)

    def _ensure_sqlite_columns(self, conn) -> None:
        if self.engine.dialect.name != "sqlite":
            return
        for column_name, column_type in [
            ("connector_kind", "VARCHAR(40)"),
            ("remote_id", "TEXT"),
            ("remote_parent_id", "TEXT"),
            ("remote_modified_at", "DATETIME"),
            ("remote_url", "TEXT"),
            ("metadata_json", "TEXT"),
            ("stale_at", "DATETIME"),
        ]:
            self._ensure_sqlite_column(conn, "sources", column_name, column_type)
        self._ensure_sqlite_column(conn, "content_nodes", "metadata_json", "TEXT")
        self._ensure_sqlite_column(conn, "semantic_edges", "metadata_json", "TEXT")
        self._ensure_sqlite_column(conn, "agent_context_blobs", "object_key", "TEXT")
        db.ensure_sqlite_json_shadow_columns(conn)

    def _ensure_sqlite_column(self, conn, table_name: str, column_name: str, column_type: str) -> None:
        existing_columns = {
            row._mapping["name"]
            for row in conn.execute(text(f"PRAGMA table_info({table_name})"))
        }
        if column_name not in existing_columns:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))

    def list_graph_activity_events(
        self,
        *,
        graph_id: str | None = None,
        lens: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[dict]:
        normalized_limit = min(100, max(1, limit))
        normalized_lens = normalize_graph_lens(lens)
        spec = self._graph_view_spec(graph_id)
        stmt = (
            select(db.graph_activity_events)
            .where(db.graph_activity_events.c.project_id == spec.project_id)
            .order_by(db.graph_activity_events.c.created_at.desc(), db.graph_activity_events.c.id.desc())
        )
        if since is not None:
            stmt = stmt.where(db.graph_activity_events.c.created_at > since)

        events: list[dict] = []
        with self.engine.begin() as conn:
            for row in conn.execute(stmt).mappings():
                event = self._activity_event_from_row(row)
                if spec.source_ids and not self._activity_event_matches_scope(event, spec.source_ids):
                    continue
                if normalized_lens != "all" and normalized_lens not in event["lenses"]:
                    continue
                events.append(event)
                if len(events) >= normalized_limit:
                    break
        return events

    def list_graph_activity_events_after(
        self,
        *,
        graph_id: str | None,
        cursor: str,
        limit: int = 100,
    ) -> list[dict]:
        normalized_limit = min(200, max(1, limit))
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            cursor_row = conn.execute(
                select(db.graph_activity_events.c.created_at, db.graph_activity_events.c.id).where(
                    and_(
                        db.graph_activity_events.c.id == cursor,
                        db.graph_activity_events.c.project_id == spec.project_id,
                    )
                )
            ).mappings().first()
            if cursor_row is None:
                return []
            stmt = (
                select(db.graph_activity_events)
                .where(
                    and_(
                        db.graph_activity_events.c.project_id == spec.project_id,
                        or_(
                            db.graph_activity_events.c.created_at > cursor_row["created_at"],
                            and_(
                                db.graph_activity_events.c.created_at == cursor_row["created_at"],
                                db.graph_activity_events.c.id > cursor_row["id"],
                            ),
                        ),
                    )
                )
                .order_by(db.graph_activity_events.c.created_at.asc(), db.graph_activity_events.c.id.asc())
            )
            events: list[dict] = []
            for row in conn.execute(stmt).mappings():
                event = self._activity_event_from_row(row)
                if spec.source_ids and not self._activity_event_matches_scope(event, spec.source_ids):
                    continue
                events.append(event)
                if len(events) >= normalized_limit:
                    break
            return events

    def _auto_commit_inserted_proposals(self, conn, proposals: list[dict], threshold: float) -> int:
        committed = 0
        proposal_rows_by_id = {proposal["id"]: proposal for proposal in proposals}

        for proposal in proposals:
            if proposal["kind"] != "content_node" or (proposal.get("confidence") or 0) < threshold:
                continue
            if self._node_proposal_conflicts(conn, proposal):
                continue
            decision = {
                "id": new_id("review"),
                "project_id": proposal["project_id"],
                "proposal_id": proposal["id"],
                "reviewer_id": "system-autocommit",
                "decision": "accept",
                "edited_value_json": None,
                "rationale": f"Auto-committed because confidence met threshold {threshold}.",
                "decided_at": now(),
            }
            self._record_review_decision(conn, proposal, decision, "accept", None, now())
            committed += 1

        for proposal in proposals:
            if proposal["kind"] != "semantic_edge" or (proposal.get("confidence") or 0) < threshold:
                continue
            value = load_json(json_value(proposal, "proposed_value_json"), {})
            endpoint_ids = [value.get("sourceNodeId"), value.get("targetNodeId")]
            if not all(isinstance(node_id, str) and node_id for node_id in endpoint_ids):
                continue
            if not self._nodes_exist(conn, endpoint_ids, project_id=proposal["project_id"]):
                continue
            decision = {
                "id": new_id("review"),
                "project_id": proposal["project_id"],
                "proposal_id": proposal["id"],
                "reviewer_id": "system-autocommit",
                "decision": "accept",
                "edited_value_json": None,
                "rationale": f"Auto-committed because confidence met threshold {threshold}.",
                "decided_at": now(),
            }
            self._record_review_decision(conn, proposal_rows_by_id[proposal["id"]], decision, "accept", None, now())
            committed += 1
        return committed

    def _node_proposal_conflicts(self, conn, proposal: dict) -> bool:
        value = load_json(json_value(proposal, "proposed_value_json"), {})
        label = str(value.get("label") or "").strip().lower()
        node_id = value.get("id")
        if not label:
            return True
        for row in conn.execute(
            select(db.content_nodes.c.id, db.content_nodes.c.label).where(
                db.content_nodes.c.project_id == proposal["project_id"]
            )
        ).mappings():
            if str(row["label"]).strip().lower() == label and row["id"] != node_id:
                return True
        return False

    def _assign_generated_graph_ids(self, generated_proposals: list[dict]) -> list[dict]:
        node_ids_by_label: dict[str, str] = {}
        assigned: list[dict] = []
        for generated in generated_proposals:
            copied = {**generated, "proposed_value": dict(generated["proposed_value"])}
            if copied.get("kind", "content_node") == "content_node":
                label = copied["proposed_value"].get("label")
                if label:
                    node_id = copied["proposed_value"].get("id") or new_id("node")
                    copied["proposed_value"]["id"] = node_id
                    node_ids_by_label[label.lower()] = node_id
            assigned.append(copied)

        resolved: list[dict] = []
        for generated in assigned:
            if generated.get("kind") == "semantic_edge":
                value = generated["proposed_value"]
                value["id"] = value.get("id") or new_id("edge")
                source_label = value.get("sourceLabel", "")
                target_label = value.get("targetLabel", "")
                source_node_id = value.get("sourceNodeId") or node_ids_by_label.get(source_label.lower())
                target_node_id = value.get("targetNodeId") or node_ids_by_label.get(target_label.lower())
                if not source_node_id or not target_node_id:
                    continue
                value["sourceNodeId"] = source_node_id
                value["targetNodeId"] = target_node_id
            resolved.append(generated)
        return resolved

    def _nodes_exist(self, conn, node_ids: list[str], *, project_id: str = DEFAULT_PROJECT_ID) -> bool:
        found = {
            row["id"]
            for row in conn.execute(
                select(db.content_nodes.c.id).where(
                    and_(
                        db.content_nodes.c.project_id == project_id,
                        db.content_nodes.c.id.in_(node_ids),
                    )
                )
            ).mappings()
        }
        return set(node_ids).issubset(found)

    def _count_by(self, items: list[dict], key: str) -> list[dict]:
        counts: dict[str, int] = {}
        for item in items:
            name = str(item.get(key) or "unknown")
            counts[name] = counts.get(name, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ]

    def _route_signal(self, conn, signal: dict, actor_id: str, timestamp: datetime) -> None:
        policy = self._matching_routing_policy(conn, signal)
        severity = signal["severity"]
        owner_id = None
        suggested_actions: list[str] = []
        due_at = None
        if policy:
            severity = policy["severity"] or severity
            owner_id = policy["owner_id"]
            suggested_actions = policy["suggested_actions"]
            if policy["sla_seconds"]:
                due_at = timestamp + timedelta(seconds=policy["sla_seconds"])
        if owner_id is None:
            owner = self._matching_owner(conn, signal)
            owner_id = owner["id"] if owner else None
        source_ids = [signal["source_id"]] if signal.get("source_id") else []
        object_refs = self._phase25_object_refs(signal)
        observation_row = {
            "id": new_id("observation"),
            "project_id": signal["project_id"],
            "signal_id": signal["id"],
            "kind": "signal_interpretation",
            "summary": f"Interpreted {signal['kind'].replace('_', ' ')} against graph context.",
            "confidence": 0.72,
            "evidence_json": dump_json([]),
            "object_refs_json": dump_json(object_refs),
            "source_ids_json": dump_json(source_ids),
            "node_ids_json": dump_json([]),
            "edge_ids_json": dump_json([]),
            "metadata_json": dump_json({"routed": True}),
            "created_at": timestamp,
        }
        conn.execute(insert(db.observations).values(**observation_row))
        alert_row = {
            "id": new_id("alert"),
            "project_id": signal["project_id"],
            "signal_id": signal["id"],
            "observation_id": observation_row["id"],
            "owner_id": owner_id,
            "policy_id": policy["id"] if policy else None,
            "severity": severity,
            "status": "assigned" if owner_id else "open",
            "title": signal["title"],
            "summary": signal["summary"],
            "reason": f"Routed from {signal['kind'].replace('_', ' ')} signal.",
            "object_refs_json": dump_json(object_refs),
            "due_at": due_at,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        conn.execute(insert(db.alerts).values(**alert_row))
        attention_row = {
            "id": new_id("attention"),
            "project_id": signal["project_id"],
            "kind": signal["kind"],
            "status": "assigned" if owner_id else "open",
            "severity": severity,
            "sla_status": self._sla_status(due_at, timestamp),
            "title": signal["title"],
            "summary": signal["summary"],
            "owner_id": owner_id,
            "assignee_id": None,
            "due_at": due_at,
            "source_id": signal.get("source_id"),
            "signal_id": signal["id"],
            "observation_id": observation_row["id"],
            "alert_id": alert_row["id"],
            "proposal_id": None,
            "decision_record_id": None,
            "action_proposal_id": None,
            "action_run_id": None,
            "outcome_id": None,
            "feedback_event_id": None,
            "object_refs_json": dump_json(object_refs),
            "evidence_json": dump_json([]),
            "suggested_actions_json": dump_json(suggested_actions),
            "blockers_json": dump_json([]),
            "created_at": timestamp,
            "updated_at": timestamp,
            "resolved_at": None,
        }
        conn.execute(insert(db.attention_items).values(**attention_row))
        conn.execute(update(db.signals).where(db.signals.c.id == signal["id"]).values(status="routed"))
        self._record_activity_event(
            conn,
            project_id=signal["project_id"],
            event_type="observation.created",
            actor_id=actor_id,
            summary=observation_row["summary"],
            object_refs=object_refs + [self._activity_ref("observation", observation_row["id"], "Observation")],
            payload={"signal_id": signal["id"], "observation_id": observation_row["id"]},
            lenses=self._phase25_lenses(signal.get("graph_id")),
            timestamp=timestamp,
        )
        self._record_activity_event(
            conn,
            project_id=signal["project_id"],
            event_type="alert.routed",
            actor_id=actor_id,
            summary=f"Routed alert {signal['title']}.",
            object_refs=object_refs + [self._activity_ref("alert", alert_row["id"], signal["title"])],
            payload={"signal_id": signal["id"], "alert_id": alert_row["id"], "attention_item_id": attention_row["id"], "severity": severity, "owner_id": owner_id},
            lenses=self._phase25_lenses(signal.get("graph_id")),
            timestamp=timestamp,
        )
        self._record_activity_event(
            conn,
            project_id=signal["project_id"],
            event_type="attention.assigned" if owner_id else "attention.opened",
            actor_id=actor_id,
            summary=f"Created attention item {signal['title']}.",
            object_refs=object_refs + [self._activity_ref("attention", attention_row["id"], signal["title"])],
            payload={
                "signal_id": signal["id"],
                "alert_id": alert_row["id"],
                "attention_item_id": attention_row["id"],
                "status": attention_row["status"],
                "owner_id": owner_id,
            },
            lenses=self._phase25_lenses(signal.get("graph_id")),
            timestamp=timestamp,
        )

    def _matching_routing_policy(self, conn, signal: dict) -> dict | None:
        policies = [
            self._routing_policy_from_row(row)
            for row in conn.execute(
                select(db.routing_policies)
                .where(and_(db.routing_policies.c.project_id == signal["project_id"], db.routing_policies.c.enabled.is_(True)))
                .order_by(db.routing_policies.c.updated_at.desc(), db.routing_policies.c.id.desc())
            ).mappings()
        ]
        for policy in policies:
            match = policy["match"]
            kinds = match.get("signal_kinds") if isinstance(match, dict) else None
            if isinstance(kinds, list) and signal["kind"] not in kinds:
                continue
            source_kinds = match.get("source_kinds") if isinstance(match, dict) else None
            if isinstance(source_kinds, list) and signal["source_kind"] not in source_kinds:
                continue
            return policy
        return None

    def _matching_owner(self, conn, signal: dict) -> dict | None:
        candidates = [self._owner_from_row(row) for row in conn.execute(select(db.owners).where(db.owners.c.project_id == signal["project_id"])).mappings()]
        scoped = [
            owner
            for owner in candidates
            if (owner["scope_kind"] == "source" and owner["scope_id"] == signal.get("source_id"))
            or (owner["scope_kind"] == "connector" and owner["scope_id"] == signal.get("source_kind"))
            or owner["scope_kind"] == "project"
        ]
        scoped.sort(key=lambda owner: {"source": 0, "connector": 1, "project": 2}.get(owner["scope_kind"], 3))
        return scoped[0] if scoped else None

    def _sla_status(self, due_at: datetime | None, timestamp: datetime) -> str:
        if due_at is None:
            return "none"
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        if due_at <= timestamp:
            return "overdue"
        if due_at - timestamp <= timedelta(hours=2):
            return "at_risk"
        return "on_track"

    def _signal_checksum(self, payload: SignalCreate) -> str:
        stable_payload = {
            "graph_id": payload.graph_id,
            "kind": payload.kind,
            "source_kind": payload.source_kind,
            "source_id": payload.source_id,
            "title": payload.title,
            "summary": payload.summary,
            "payload": payload.payload,
        }
        return hashlib.sha256(dump_json(stable_payload).encode("utf-8")).hexdigest()

    def _phase25_lenses(self, graph_id: str | None) -> list[str]:
        lens = normalize_graph_lens(graph_id.split(":")[-1] if graph_id and ":" in graph_id else None)
        return [] if lens == "all" else [lens]

    def _phase25_object_refs(self, item: dict) -> list[dict]:
        refs: list[dict] = []
        if item.get("source_id"):
            refs.append(self._activity_ref("source", item.get("source_id"), None))
        kind = "graph"
        object_id = item.get("id")
        label = item.get("title") or item.get("summary") or item.get("kind")
        if str(object_id or "").startswith("signal_"):
            kind = "signal"
        elif str(object_id or "").startswith("observation_"):
            kind = "observation"
        elif str(object_id or "").startswith("alert_"):
            kind = "alert"
        elif str(object_id or "").startswith("attention_"):
            kind = "attention"
        elif str(object_id or "").startswith("decision_"):
            kind = "decision"
        elif str(object_id or "").startswith("action_"):
            kind = "action_proposal"
        elif str(object_id or "").startswith("run_"):
            kind = "action_run"
        elif str(object_id or "").startswith("outcome_"):
            kind = "outcome"
        elif str(object_id or "").startswith("feedback_"):
            kind = "feedback"
        refs.append(self._activity_ref(kind, object_id, label))
        return refs

    def _agent_context_token_hash(self, token: str) -> str:
        return hmac.new(self.secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _redact_context_text(self, value: str) -> str:
        return redact_sensitive_text(value)

    def _safe_context_path(self, value: str | None) -> str | None:
        if not value:
            return value
        normalized = value.replace("\\", "/")
        if any(pattern in normalized for pattern in AGENT_CONTEXT_DEFAULT_DENIED_PATTERNS):
            return "[redacted-path]"
        return normalized

    def _validate_agent_context_path_policy(self, value: str | None, *, session: dict, client: dict) -> None:
        if not value:
            return
        normalized = value.replace("\\", "/")
        normalized_lower = normalized.lower()
        denied_patterns = [pattern.lower() for pattern in AGENT_CONTEXT_DEFAULT_DENIED_PATTERNS]
        settings = client.get("settings") or {}
        configured_denied = settings.get("denied_path_fragments")
        if isinstance(configured_denied, list):
            denied_patterns.extend(str(pattern).lower() for pattern in configured_denied)
        if any(pattern and pattern in normalized_lower for pattern in denied_patterns):
            raise ValueError("Agent context path is denied by capture policy")

        if not normalized.startswith("/"):
            return
        allowed_roots = [session.get("workspace_root")]
        configured_roots = settings.get("workspace_roots")
        if isinstance(configured_roots, list):
            allowed_roots.extend(str(root) for root in configured_roots)
        allowed_roots = [root.replace("\\", "/").rstrip("/") for root in allowed_roots if isinstance(root, str) and root]
        if not allowed_roots:
            return
        candidate = os.path.normpath(normalized).replace("\\", "/")
        for root in allowed_roots:
            normalized_root = os.path.normpath(root).replace("\\", "/").rstrip("/")
            if candidate == normalized_root or candidate.startswith(f"{normalized_root}/"):
                return
        raise ValueError("Agent context path is outside configured workspace roots")

    def _agent_context_artifact_row(self, *, project_id: str, session_id: str, payload, timestamp: datetime) -> dict:
        title = payload.title or payload.path or payload.uri or payload.kind.replace("_", " ").title()
        metadata = self._redact_payload(payload.metadata)
        path = self._safe_context_path(payload.path)
        uri = self._safe_context_path(payload.uri)
        return {
            "id": new_id("ctxartifact"),
            "project_id": project_id,
            "session_id": session_id,
            "kind": payload.kind,
            "uri": uri,
            "path": path,
            "title": str(title)[:240],
            "content_type": payload.content_type,
            "checksum": payload.checksum,
            "metadata_json": dump_json(metadata),
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _agent_context_blob_row(self, *, project_id: str, session_id: str, artifact_id: str | None, payload, timestamp: datetime) -> dict:
        raw_text = payload.text or ""
        if payload.content_kind != "text":
            raw_text = ""
        redacted_text = self._redact_context_text(raw_text)
        encoded = redacted_text.encode("utf-8")
        within_limit = payload.content_kind == "text" and bool(raw_text) and len(encoded) <= self.agent_context_max_blob_bytes
        checksum = payload.checksum or hashlib.sha256(encoded or str(payload.metadata).encode("utf-8")).hexdigest()
        blob_id = new_id("ctxblob")
        encrypted_content = self._encrypt_agent_context_text(redacted_text) if within_limit else None
        object_key = None
        if encrypted_content and self.object_store is not None:
            object_key = f"{project_id}/agent-context/{session_id}/{blob_id}.gvenc"
            self.object_store.put_bytes(
                object_key,
                encrypted_content.encode("utf-8"),
                content_type="application/vnd.graphview.encrypted-context",
                checksum=hashlib.sha256(encrypted_content.encode("utf-8")).hexdigest(),
            )
            encrypted_content = None
        byte_count = payload.byte_count if payload.byte_count is not None else len(encoded)
        return {
            "id": blob_id,
            "project_id": project_id,
            "session_id": session_id,
            "artifact_id": artifact_id,
            "content_kind": payload.content_kind,
            "media_type": payload.media_type,
            "redaction_status": "redacted" if within_limit and redacted_text != raw_text else ("metadata_only" if not within_limit else "not_required"),
            "encryption_status": "object_encrypted" if object_key else ("encrypted" if encrypted_content else "metadata_only"),
            "checksum": checksum,
            "byte_count": byte_count,
            "token_count": payload.token_count,
            "encrypted_content": encrypted_content,
            "object_key": object_key,
            "metadata_json": dump_json(self._redact_payload(payload.metadata)),
            "created_at": timestamp,
            "expires_at": timestamp + timedelta(days=self.agent_context_retention_days),
        }

    def _encrypt_agent_context_text(self, text_value: str) -> str:
        encrypted = self._agent_context_fernet().encrypt(text_value.encode("utf-8")).decode("ascii")
        return f"gvenc:fernet:v1:{encrypted}"

    def _agent_context_blob_envelope(self, row) -> str | None:
        if row.get("object_key") and self.object_store is not None:
            return self.object_store.get_bytes(str(row["object_key"])).decode("utf-8")
        return row.get("encrypted_content")

    def _decrypt_agent_context_text(self, envelope_value: str) -> str:
        if not envelope_value.startswith("gvenc:fernet:v1:"):
            return ""
        try:
            encrypted_payload = envelope_value.removeprefix("gvenc:fernet:v1:").encode("ascii")
            decrypted = self._agent_context_fernet().decrypt(encrypted_payload)
        except InvalidToken:
            raise ValueError("Invalid agent context blob envelope")
        return decrypted.decode("utf-8")

    def _agent_context_fernet(self) -> Fernet:
        key = base64.urlsafe_b64encode(hashlib.sha256(self.secret_key.encode("utf-8")).digest())
        return Fernet(key)

    def _agent_context_event_summary(self, event_kind: str, artifact_row: dict | None) -> str:
        label = artifact_row["title"] if artifact_row else "active context"
        return f"Captured {event_kind.replace('_', ' ')} for {label}."

    def _agent_context_relation_for_event(self, event_kind: str) -> str:
        if event_kind in {"file_opened", "file_read", "selection_changed"}:
            return "read"
        if event_kind in {"edit_applied", "diff_observed"}:
            return "modified"
        if event_kind in {"prompt_built", "model_request", "model_response"}:
            return "included_context"
        if event_kind == "search_performed":
            return "searched"
        if event_kind in {"test_run", "shell_command"}:
            return "executed"
        if event_kind == "commit_observed":
            return "committed"
        return "observed"

    def _execute_safe_action(self, conn, proposal_row: dict, payload: dict, timestamp: datetime) -> tuple[str, str | None, str | None, str | None]:
        action_type = proposal_row["action_type"]
        if action_type == "mark_source_stale":
            source_id = payload.get("source_id")
            if not source_id:
                return "failed", None, "missing_source", "source_id is required."
            result = conn.execute(
                update(db.sources)
                .where(and_(db.sources.c.id == source_id, db.sources.c.project_id == proposal_row["project_id"]))
                .values(stale_at=timestamp, updated_at=timestamp)
            )
            if result.rowcount == 0:
                return "failed", None, "source_not_found", "source_id was not found in this project."
            return "succeeded", None, None, None
        if action_type == "mark_source_refreshed":
            source_id = payload.get("source_id")
            if not source_id:
                return "failed", None, "missing_source", "source_id is required."
            result = conn.execute(
                update(db.sources)
                .where(and_(db.sources.c.id == source_id, db.sources.c.project_id == proposal_row["project_id"]))
                .values(stale_at=None, updated_at=timestamp)
            )
            if result.rowcount == 0:
                return "failed", None, "source_not_found", "source_id was not found in this project."
            return "succeeded", None, None, None
        if action_type in {"create_external_ticket", "create_notification", "trigger_workflow"}:
            return "failed", None, "external_adapter_required", "External actions execute only through durable workers."
        if action_type in {"connector_sync", "create_graph_proposal", "request_owner_confirmation"}:
            return "succeeded", f"{action_type}-{uuid4().hex[:10]}", None, None
        return "failed", None, "unsupported_action", "Action type is not executable."

    def _attention_status_for_outcome(self, status_value: str) -> str:
        if status_value in {"resolved", "succeeded"}:
            return "resolved"
        if status_value == "reopened":
            return "reopened"
        if status_value in {"failed", "unresolved"}:
            return "blocked"
        return "waiting_for_outcome"

    def _record_activity_event(
        self,
        conn,
        *,
        project_id: str,
        event_type: str,
        actor_id: str | None,
        summary: str,
        object_refs: list[dict],
        payload: dict | None = None,
        lenses: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> dict:
        event = {
            "id": new_id("activity"),
            "project_id": project_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "summary": summary,
            "object_refs_json": dump_json([ref for ref in object_refs if ref.get("id")]),
            "payload_json": dump_json(payload or {}),
            "lenses_json": dump_json(sorted({lens for lens in (lenses or []) if lens in GRAPH_LENSES})),
            "created_at": timestamp or now(),
        }
        conn.execute(insert(db.graph_activity_events).values(**event))
        return event

    def search(self, query: str, graph_id: str | None = None) -> dict[str, list[dict]]:
        like = f"%{query}%"
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            sources = [
                self._source_from_row(row)
                for row in conn.execute(
                    select(db.sources).where(
                        and_(
                            db.sources.c.project_id == spec.project_id,
                            or_(db.sources.c.title.like(like), db.sources.c.uri.like(like)),
                        )
                    )
                ).mappings()
            ]
            if spec.source_ids:
                source_id_set = set(spec.source_ids)
                sources = [source for source in sources if source["id"] in source_id_set]
            nodes = [
                self._node_from_row(row)
                for row in conn.execute(
                    select(db.content_nodes).where(
                        and_(
                            db.content_nodes.c.project_id == spec.project_id,
                            or_(db.content_nodes.c.label.like(like), db.content_nodes.c.summary.like(like)),
                        )
                    )
                ).mappings()
            ]
            if spec.source_ids:
                nodes = [node for node in nodes if self._item_matches_sources(node, spec.source_ids)]
        return {"sources": sources, "nodes": nodes}

    def export_bundle(self, graph_id: str | None = None, *, include_agent_context_content: bool = False) -> dict:
        from graphview_api.api_v1.repository import GraphProjectionRepository

        spec = self._graph_view_spec(graph_id)
        project, nodes, edges = self.graph(graph_id)
        proposals = self.list_proposals(graph_id=graph_id)
        proposal_ids = {proposal["id"] for proposal in proposals}
        projection = GraphProjectionRepository(self)
        graph_version = projection.graph_version(spec.project_id) if not spec.source_ids else None
        graph_layouts = projection.list_layouts(spec.project_id, include_positions=True) if not spec.source_ids else []
        with self.engine.begin() as conn:
            exported_at = now()
            source_ids = {source["id"] for source in self.list_sources(graph_id=graph_id)}
            return {
                "project": project,
                "sources": self.list_sources(graph_id=graph_id),
                "topics": [
                    self._topic_from_row(row)
                    for row in conn.execute(
                        select(db.topics).where(db.topics.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "nodes": nodes,
                "edges": edges,
                "ingestion_runs": [
                    normalize_json_row(row)
                    for row in conn.execute(
                        select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                    ).mappings()
                    if not spec.source_ids or row["source_id"] in set(spec.source_ids)
                ],
                "proposals": proposals,
                "embeddings": [
                    self._embedding_from_row(row)
                    for row in conn.execute(
                        select(db.content_embeddings).where(db.content_embeddings.c.project_id == spec.project_id)
                    ).mappings()
                    if row["proposal_id"] in proposal_ids
                ],
                "review_decisions": [
                    self._decision_from_row(row)
                    for row in conn.execute(
                        select(db.review_decisions).where(db.review_decisions.c.project_id == spec.project_id)
                    ).mappings()
                    if row["proposal_id"] in proposal_ids
                ],
                "connector_accounts": self.list_connector_accounts() if spec.project_id == DEFAULT_PROJECT_ID else [],
                "connector_targets": self.list_connector_targets() if spec.project_id == DEFAULT_PROJECT_ID else [],
                "connector_sync_runs": self.list_connector_sync_runs() if spec.project_id == DEFAULT_PROJECT_ID else [],
                "source_chunks": [
                    self._source_chunk_from_row(row)
                    for row in conn.execute(
                        select(db.source_chunks).where(db.source_chunks.c.project_id == spec.project_id)
                    ).mappings()
                    if row["source_id"] in source_ids
                ],
                "graph_version": graph_version,
                "graph_layouts": graph_layouts,
                "graph_settings": self.graph_settings() if spec.project_id == DEFAULT_PROJECT_ID else None,
                "planning_sessions": [
                    self._planning_session_from_row(row)
                    for row in conn.execute(
                        select(db.planning_sessions).where(db.planning_sessions.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_runs": [
                    self.get_agent_run(row["id"]) or self._agent_run_from_row(row)
                    for row in conn.execute(
                        select(db.agent_runs).where(db.agent_runs.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "research_tasks": [
                    self._research_task_from_row(row)
                    for row in conn.execute(
                        select(db.research_tasks).where(db.research_tasks.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_action_proposals": [
                    self._agent_action_proposal_from_row(row)
                    for row in conn.execute(
                        select(db.agent_action_proposals).where(db.agent_action_proposals.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "activity_events": [
                    event
                    for event in [
                        self._activity_event_from_row(row)
                        for row in conn.execute(
                            select(db.graph_activity_events)
                            .where(db.graph_activity_events.c.project_id == spec.project_id)
                            .order_by(db.graph_activity_events.c.created_at.desc(), db.graph_activity_events.c.id.desc())
                        ).mappings()
                    ]
                    if not spec.source_ids or self._activity_event_matches_scope(event, spec.source_ids)
                ],
                "signals": [
                    self._signal_from_row(row)
                    for row in conn.execute(
                        select(db.signals).where(db.signals.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "observations": [
                    self._observation_from_row(row)
                    for row in conn.execute(
                        select(db.observations).where(db.observations.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "owners": [
                    self._owner_from_row(row)
                    for row in conn.execute(select(db.owners).where(db.owners.c.project_id == spec.project_id)).mappings()
                ],
                "routing_policies": [
                    self._routing_policy_from_row(row)
                    for row in conn.execute(
                        select(db.routing_policies).where(db.routing_policies.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "alerts": [
                    self._alert_from_row(row)
                    for row in conn.execute(select(db.alerts).where(db.alerts.c.project_id == spec.project_id)).mappings()
                ],
                "attention_items": [
                    self._attention_item_from_row(row)
                    for row in conn.execute(
                        select(db.attention_items).where(db.attention_items.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "decision_records": [
                    self._decision_record_from_row(row)
                    for row in conn.execute(
                        select(db.decision_records).where(db.decision_records.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "action_proposals": [
                    self._action_proposal_from_row(row)
                    for row in conn.execute(
                        select(db.action_proposals).where(db.action_proposals.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "action_runs": [
                    self._action_run_from_row(row)
                    for row in conn.execute(select(db.action_runs).where(db.action_runs.c.project_id == spec.project_id)).mappings()
                ],
                "outcomes": [
                    self._outcome_from_row(row)
                    for row in conn.execute(select(db.outcomes).where(db.outcomes.c.project_id == spec.project_id)).mappings()
                ],
                "feedback_events": [
                    self._feedback_event_from_row(row)
                    for row in conn.execute(
                        select(db.feedback_events).where(db.feedback_events.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_clients": [
                    self._agent_context_client_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_clients).where(db.agent_context_clients.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_sessions": [
                    self._agent_context_session_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_sessions).where(db.agent_context_sessions.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_artifacts": [
                    self._agent_context_artifact_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_artifacts).where(db.agent_context_artifacts.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_blobs": [
                    self._agent_context_blob_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_blobs).where(db.agent_context_blobs.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_blob_contents": [
                    {
                        "blob_id": row["id"],
                        "encrypted_content": envelope,
                        "exported_at": exported_at,
                    }
                    for row in conn.execute(
                        select(db.agent_context_blobs).where(
                            and_(
                                db.agent_context_blobs.c.project_id == spec.project_id,
                                or_(
                                    db.agent_context_blobs.c.encrypted_content.is_not(None),
                                    db.agent_context_blobs.c.object_key.is_not(None),
                                ),
                            )
                        )
                    ).mappings()
                    if (envelope := self._agent_context_blob_envelope(row))
                ]
                if include_agent_context_content
                else [],
                "agent_context_events": [
                    self._agent_context_event_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_events).where(db.agent_context_events.c.project_id == spec.project_id)
                    ).mappings()
                ],
            }

    def backup_bundle(self, actor_id: str, *, include_agent_context_content: bool = False) -> dict:
        bundle = self.export_bundle(include_agent_context_content=include_agent_context_content)
        return {
            "metadata": {
                "schema_version": 1,
                "created_at": now(),
                "created_by": actor_id,
                "project_id": bundle["project"]["id"],
                "source_count": len(bundle["sources"]),
                "node_count": len(bundle["nodes"]),
                "edge_count": len(bundle["edges"]),
                "proposal_count": len(bundle["proposals"]),
                "agent_context_session_count": len(bundle.get("agent_context_sessions", [])),
                "agent_context_content_blob_count": len(bundle.get("agent_context_blob_contents", [])),
            },
            "bundle": bundle,
        }

    def restore_bundle(self, bundle: ExportBundle, *, actor_id: str = "system-restore") -> dict:
        project_id = bundle.project.id
        restore_timestamp = now()
        with self.engine.begin() as conn:
            conn.execute(
                delete(db.upload_parts).where(
                    db.upload_parts.c.session_id.in_(
                        select(db.upload_sessions.c.id).where(db.upload_sessions.c.project_id == project_id)
                    )
                )
            )
            conn.execute(
                delete(db.graph_layout_positions).where(
                    db.graph_layout_positions.c.layout_id.in_(
                        select(db.graph_layouts.c.id).where(db.graph_layouts.c.project_id == project_id)
                    )
                )
            )
            conn.execute(
                update(db.durable_jobs)
                .where(
                    and_(
                        db.durable_jobs.c.project_id == project_id,
                        db.durable_jobs.c.status.in_(["queued", "retry", "running", "cancelling"]),
                    )
                )
                .values(
                    status="cancelled",
                    leased_until=None,
                    worker_id=None,
                    error_code="RestoreSuppressed",
                    error="Suppressed during logical restore",
                    updated_at=restore_timestamp,
                    finished_at=restore_timestamp,
                )
            )
            conn.execute(
                update(db.event_outbox)
                .where(and_(db.event_outbox.c.project_id == project_id, db.event_outbox.c.status == "pending"))
                .values(status="suppressed", published_at=restore_timestamp)
            )
            for table in [
                db.agent_context_events,
                db.agent_context_blobs,
                db.agent_context_artifacts,
                db.agent_context_sessions,
                db.agent_context_clients,
                db.feedback_events,
                db.outcomes,
                db.action_runs,
                db.action_proposals,
                db.decision_records,
                db.attention_items,
                db.alerts,
                db.routing_policies,
                db.owners,
                db.observations,
                db.signals,
                db.graph_activity_events,
                db.agent_action_proposals,
                db.research_tasks,
                db.agent_steps,
                db.agent_runs,
                db.graph_build_specs,
                db.planning_messages,
                db.planning_sessions,
                db.review_decisions,
                db.content_embeddings,
                db.extraction_proposals,
                db.ingestion_runs,
                db.semantic_edges,
                db.content_nodes,
                db.source_chunks,
                db.sources,
                db.upload_sessions,
                db.connector_cursors,
                db.connector_sync_runs,
                db.connector_targets,
                db.connector_accounts,
                db.topics,
                db.graph_layouts,
                db.graph_versions,
                db.graph_settings,
            ]:
                conn.execute(delete(table).where(table.c.project_id == project_id))
            conn.execute(delete(db.graph_projects).where(db.graph_projects.c.id == project_id))

            conn.execute(insert(db.graph_projects).values(**bundle.project.model_dump()))
            connector_accounts = [
                {
                    "id": account.id,
                    "project_id": account.project_id,
                    "kind": account.kind,
                    "display_name": account.display_name,
                    "status": "error",
                    "created_by": account.created_by,
                    "encrypted_token_json": None,
                    "scopes_json": dump_json(account.scopes),
                    "settings_json": dump_json(account.settings),
                    "created_at": account.created_at,
                    "updated_at": restore_timestamp,
                }
                for account in bundle.connector_accounts
            ]
            connector_targets = [
                {
                    "id": target.id,
                    "project_id": target.project_id,
                    "account_id": target.account_id,
                    "connector_kind": target.connector_kind,
                    "target_type": target.target_type,
                    "remote_id": target.remote_id,
                    "title": target.title,
                    "parent_remote_id": target.parent_remote_id,
                    "sync_settings_json": dump_json(target.sync_settings),
                    "last_synced_at": target.last_synced_at,
                    "created_at": target.created_at,
                    "updated_at": restore_timestamp,
                }
                for target in bundle.connector_targets
            ]
            connector_sync_runs = [
                {
                    **sync_run.model_dump(),
                    "status": "failed" if sync_run.status == "running" else sync_run.status,
                    "stage": "restore_suppressed" if sync_run.status == "running" else sync_run.stage,
                    "error": "Suppressed during restore" if sync_run.status == "running" else sync_run.error,
                    "finished_at": restore_timestamp if sync_run.status == "running" else sync_run.finished_at,
                }
                for sync_run in bundle.connector_sync_runs
            ]
            graph_version = bundle.graph_version.model_dump() if bundle.graph_version else None
            graph_layouts = [
                {
                    "id": layout.id,
                    "project_id": layout.project_id,
                    "name": layout.name,
                    "algorithm": layout.algorithm,
                    "graph_version": layout.graph_version,
                    "settings_json": dump_json(layout.settings),
                    "created_by": layout.created_by,
                    "created_at": layout.created_at,
                    "updated_at": layout.updated_at,
                }
                for layout in bundle.graph_layouts
            ]
            graph_layout_positions = [
                {
                    "layout_id": layout.id,
                    "node_id": position.node_id,
                    "x": position.x,
                    "y": position.y,
                    "z": position.z,
                    "cluster_key": position.cluster_key,
                }
                for layout in bundle.graph_layouts
                for position in layout.positions
            ]
            sources = []
            for source in bundle.sources:
                dumped = source.model_dump()
                dumped["metadata_json"] = dump_json(dumped.pop("metadata") or {})
                sources.append(dumped)
            topics = [topic.model_dump() for topic in bundle.topics]
            nodes = [
                {
                    "id": node.id,
                    "project_id": node.project_id,
                    "label": node.label,
                    "kind": node.kind,
                    "summary": node.summary,
                    "topic_ids_json": dump_json(node.topic_ids),
                    "metadata_json": dump_json(node.metadata or {}),
                    "provenance_json": dump_json(node.provenance),
                    "created_at": node.created_at,
                    "updated_at": node.updated_at,
                }
                for node in bundle.nodes
            ]
            edges = [
                {
                    "id": edge.id,
                    "project_id": edge.project_id,
                    "source_node_id": edge.source_node_id,
                    "target_node_id": edge.target_node_id,
                    "relation": edge.relation,
                    "weight": edge.weight,
                    "metadata_json": dump_json(edge.metadata or {}),
                    "provenance_json": dump_json(edge.provenance),
                    "created_at": edge.created_at,
                    "updated_at": edge.updated_at,
                }
                for edge in bundle.edges
            ]
            ingestion_runs = [
                {
                    **run.model_dump(),
                    "status": "cancelled" if run.status in {"queued", "running"} else run.status,
                    "finished_at": restore_timestamp if run.status in {"queued", "running"} else run.finished_at,
                    "error_code": "RestoreSuppressed" if run.status in {"queued", "running"} else run.error_code,
                }
                for run in bundle.ingestion_runs
            ]
            proposals = [
                {
                    "id": proposal.id,
                    "project_id": proposal.project_id,
                    "ingestion_run_id": proposal.ingestion_run_id,
                    "kind": proposal.kind,
                    "status": proposal.status,
                    "proposed_value_json": dump_json(proposal.proposed_value),
                    "confidence": proposal.confidence,
                    "provenance_json": dump_json(proposal.provenance),
                    "created_at": proposal.created_at,
                }
                for proposal in bundle.proposals
            ]
            embeddings = [
                {
                    "id": embedding.id,
                    "project_id": embedding.project_id,
                    "proposal_id": embedding.proposal_id,
                    "content_node_id": embedding.content_node_id,
                    "embedding_model": embedding.embedding_model,
                    "vector_json": dump_json(embedding.vector),
                    "created_at": embedding.created_at,
                }
                for embedding in bundle.embeddings
            ]
            review_decisions = [
                {
                    "id": decision.id,
                    "project_id": decision.project_id,
                    "proposal_id": decision.proposal_id,
                    "reviewer_id": decision.reviewer_id,
                    "decision": decision.decision,
                    "edited_value_json": dump_json(decision.edited_value) if decision.edited_value is not None else None,
                    "rationale": decision.rationale,
                    "decided_at": decision.decided_at,
                }
                for decision in bundle.review_decisions
            ]
            source_chunks = [
                {
                    "id": chunk.id,
                    "project_id": chunk.project_id,
                    "source_id": chunk.source_id,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "heading_path_json": dump_json(chunk.heading_path),
                    "block_type": chunk.block_type,
                    "ordinal": chunk.ordinal,
                    "text": chunk.text,
                    "links_json": dump_json(chunk.links),
                    "mentions_json": dump_json(chunk.mentions),
                    "checksum": chunk.checksum,
                    "locator": chunk.locator,
                    "created_at": chunk.created_at,
                }
                for chunk in bundle.source_chunks
            ]
            graph_settings = None
            if bundle.graph_settings:
                graph_settings = bundle.graph_settings.model_dump()
                graph_settings["settings_json"] = dump_json(graph_settings.pop("settings") or {})
            planning_sessions = [
                {
                    "id": session.id,
                    "project_id": session.project_id,
                    "graph_id": session.graph_id,
                    "lens": session.lens,
                    "title": session.title,
                    "goal": session.goal,
                    "status": session.status,
                    "provider": session.provider,
                    "model": session.model,
                    "created_by": session.created_by,
                    "metadata_json": dump_json(session.metadata),
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                }
                for session in bundle.planning_sessions
            ]
            planning_messages = [
                {
                    "id": message.id,
                    "project_id": message.project_id,
                    "session_id": message.session_id,
                    "agent_run_id": message.agent_run_id,
                    "role": message.role,
                    "content": message.content,
                    "provider": message.provider,
                    "model": message.model,
                    "metadata_json": dump_json(message.metadata),
                    "created_at": message.created_at,
                }
                for session in bundle.planning_sessions
                for message in session.messages
            ]
            graph_build_specs = [
                {
                    "id": spec.id,
                    "project_id": spec.project_id,
                    "session_id": spec.session_id,
                    "version": spec.version,
                    "title": spec.title,
                    "objective": spec.objective,
                    "status": spec.status,
                    "spec_json": dump_json(spec.spec),
                    "created_at": spec.created_at,
                    "updated_at": spec.updated_at,
                }
                for session in bundle.planning_sessions
                for spec in ([session.build_spec] if session.build_spec else [])
            ]
            agent_runs = [
                {
                    "id": run.id,
                    "project_id": run.project_id,
                    "planning_session_id": run.planning_session_id,
                    "kind": run.kind,
                    "status": "cancelled" if run.status in {"queued", "running"} else run.status,
                    "provider": run.provider,
                    "model": run.model,
                    "input_json": dump_json(run.input),
                    "output_json": dump_json(run.output),
                    "trace_id": run.trace_id,
                    "created_by": run.created_by,
                    "started_at": run.started_at,
                    "finished_at": restore_timestamp if run.status in {"queued", "running"} else run.finished_at,
                    "error": "Suppressed during restore" if run.status in {"queued", "running"} else run.error,
                }
                for run in bundle.agent_runs
            ]
            agent_steps = [
                {
                    "id": step.id,
                    "project_id": step.project_id,
                    "agent_run_id": step.agent_run_id,
                    "name": step.name,
                    "status": "failed" if step.status == "running" else step.status,
                    "input_summary": step.input_summary,
                    "output_summary": step.output_summary,
                    "error": "Suppressed during restore" if step.status == "running" else step.error,
                    "trace_id": step.trace_id,
                    "metadata_json": dump_json(step.metadata),
                    "started_at": step.started_at,
                    "finished_at": restore_timestamp if step.status == "running" else step.finished_at,
                }
                for run in bundle.agent_runs
                for step in run.steps
            ]
            research_tasks = [
                {
                    "id": task.id,
                    "project_id": task.project_id,
                    "agent_run_id": task.agent_run_id,
                    "planning_session_id": task.planning_session_id,
                    "query": task.query,
                    "status": "failed" if task.status in {"queued", "running"} else task.status,
                    "provider": task.provider,
                    "model": task.model,
                    "source_policy": task.source_policy,
                    "idempotency_key": task.idempotency_key,
                    "result_json": dump_json({"restore_suppressed": True})
                    if task.status in {"queued", "running"}
                    else dump_json(task.result),
                    "created_by": task.created_by,
                    "created_at": task.created_at,
                    "updated_at": restore_timestamp if task.status in {"queued", "running"} else task.updated_at,
                }
                for task in bundle.research_tasks
            ]
            actions_by_id = {
                action.id: action
                for action in [
                    *bundle.agent_action_proposals,
                    *(action for run in bundle.agent_runs for action in run.action_proposals),
                ]
            }
            agent_action_proposals = [
                {
                    "id": action.id,
                    "project_id": action.project_id,
                    "agent_run_id": action.agent_run_id,
                    "action_type": action.action_type,
                    "status": action.status,
                    "title": action.title,
                    "summary": action.summary,
                    "payload_json": dump_json(action.payload),
                    "citations_json": dump_json(action.citations),
                    "confidence": action.confidence,
                    "created_at": action.created_at,
                    "updated_at": action.updated_at,
                    "applied_at": action.applied_at,
                }
                for action in actions_by_id.values()
            ]
            activity_events = [
                {
                    "id": event.id,
                    "project_id": event.project_id,
                    "event_type": event.event_type,
                    "actor_id": event.actor_id,
                    "summary": event.summary,
                    "object_refs_json": dump_json(event.object_refs),
                    "payload_json": dump_json(event.payload),
                    "lenses_json": dump_json(event.lenses),
                    "created_at": event.created_at,
                }
                for event in bundle.activity_events
            ]
            signals = [
                {
                    "id": signal.id,
                    "project_id": signal.project_id,
                    "graph_id": signal.graph_id,
                    "kind": signal.kind,
                    "status": signal.status,
                    "severity": signal.severity,
                    "source_kind": signal.source_kind,
                    "source_id": signal.source_id,
                    "title": signal.title,
                    "summary": signal.summary,
                    "payload_json": dump_json(signal.payload),
                    "checksum": signal.checksum,
                    "trace_id": signal.trace_id,
                    "actor_id": signal.actor_id,
                    "received_at": signal.received_at,
                    "created_at": signal.created_at,
                }
                for signal in bundle.signals
            ]
            observations = [
                {
                    "id": observation.id,
                    "project_id": observation.project_id,
                    "signal_id": observation.signal_id,
                    "kind": observation.kind,
                    "summary": observation.summary,
                    "confidence": observation.confidence,
                    "evidence_json": dump_json(observation.evidence),
                    "object_refs_json": dump_json([ref.model_dump() for ref in observation.object_refs]),
                    "source_ids_json": dump_json(observation.source_ids),
                    "node_ids_json": dump_json(observation.node_ids),
                    "edge_ids_json": dump_json(observation.edge_ids),
                    "metadata_json": dump_json(observation.metadata),
                    "created_at": observation.created_at,
                }
                for observation in bundle.observations
            ]
            owners = [
                {
                    "id": owner.id,
                    "project_id": owner.project_id,
                    "owner_type": owner.owner_type,
                    "display_name": owner.display_name,
                    "contact": owner.contact,
                    "scope_kind": owner.scope_kind,
                    "scope_id": owner.scope_id,
                    "escalation_contact": owner.escalation_contact,
                    "metadata_json": dump_json(owner.metadata),
                    "created_at": owner.created_at,
                    "updated_at": owner.updated_at,
                }
                for owner in bundle.owners
            ]
            routing_policies = [
                {
                    "id": policy.id,
                    "project_id": policy.project_id,
                    "name": policy.name,
                    "description": policy.description,
                    "enabled": policy.enabled,
                    "match_json": dump_json(policy.match),
                    "severity": policy.severity,
                    "owner_id": policy.owner_id,
                    "sla_seconds": policy.sla_seconds,
                    "suggested_actions_json": dump_json(policy.suggested_actions),
                    "approval_required": policy.approval_required,
                    "metadata_json": dump_json(policy.metadata),
                    "created_at": policy.created_at,
                    "updated_at": policy.updated_at,
                }
                for policy in bundle.routing_policies
            ]
            alerts = [
                {
                    "id": alert.id,
                    "project_id": alert.project_id,
                    "signal_id": alert.signal_id,
                    "observation_id": alert.observation_id,
                    "owner_id": alert.owner_id,
                    "policy_id": alert.policy_id,
                    "severity": alert.severity,
                    "status": alert.status,
                    "title": alert.title,
                    "summary": alert.summary,
                    "reason": alert.reason,
                    "object_refs_json": dump_json([ref.model_dump() for ref in alert.object_refs]),
                    "due_at": alert.due_at,
                    "created_at": alert.created_at,
                    "updated_at": alert.updated_at,
                }
                for alert in bundle.alerts
            ]
            suppressed_action_run_ids = {
                run.id for run in bundle.action_runs if run.status in {"queued", "running"}
            }
            attention_items = [
                {
                    "id": item.id,
                    "project_id": item.project_id,
                    "kind": item.kind,
                    "status": "blocked"
                    if item.action_run_id in suppressed_action_run_ids
                    and item.status in {"waiting_for_action", "waiting_for_outcome"}
                    else item.status,
                    "severity": item.severity,
                    "sla_status": item.sla_status,
                    "title": item.title,
                    "summary": item.summary,
                    "owner_id": item.owner_id,
                    "assignee_id": item.assignee_id,
                    "due_at": item.due_at,
                    "source_id": item.source_id,
                    "signal_id": item.signal_id,
                    "observation_id": item.observation_id,
                    "alert_id": item.alert_id,
                    "proposal_id": item.proposal_id,
                    "decision_record_id": item.decision_record_id,
                    "action_proposal_id": item.action_proposal_id,
                    "action_run_id": item.action_run_id,
                    "outcome_id": item.outcome_id,
                    "feedback_event_id": item.feedback_event_id,
                    "object_refs_json": dump_json([ref.model_dump() for ref in item.object_refs]),
                    "evidence_json": dump_json(item.evidence),
                    "suggested_actions_json": dump_json(item.suggested_actions),
                    "blockers_json": dump_json(item.blockers),
                    "created_at": item.created_at,
                    "updated_at": restore_timestamp
                    if item.action_run_id in suppressed_action_run_ids
                    else item.updated_at,
                    "resolved_at": item.resolved_at,
                }
                for item in bundle.attention_items
            ]
            decision_records = [
                {
                    "id": decision.id,
                    "project_id": decision.project_id,
                    "alert_id": decision.alert_id,
                    "attention_item_id": decision.attention_item_id,
                    "proposal_id": decision.proposal_id,
                    "decision": decision.decision,
                    "rationale": decision.rationale,
                    "actor_id": decision.actor_id,
                    "evidence_json": dump_json(decision.evidence),
                    "object_refs_json": dump_json([ref.model_dump() for ref in decision.object_refs]),
                    "created_at": decision.created_at,
                }
                for decision in bundle.decision_records
            ]
            action_proposals = [
                {
                    "id": action.id,
                    "project_id": action.project_id,
                    "decision_record_id": action.decision_record_id,
                    "alert_id": action.alert_id,
                    "attention_item_id": action.attention_item_id,
                    "action_type": action.action_type,
                    "status": "cancelled"
                    if action.status in {"approved", "queued", "running"}
                    else action.status,
                    "title": action.title,
                    "summary": action.summary,
                    "payload_json": dump_json(action.redacted_payload),
                    "redacted_payload_json": dump_json(action.redacted_payload),
                    "safety_json": dump_json(action.safety.model_dump()),
                    "approval_required": action.approval_required,
                    "created_by": action.created_by,
                    "approved_by": action.approved_by,
                    "rejected_by": action.rejected_by,
                    "rationale": action.rationale,
                    "created_at": action.created_at,
                    "updated_at": restore_timestamp
                    if action.status in {"approved", "queued", "running"}
                    else action.updated_at,
                    "decided_at": action.decided_at,
                }
                for action in bundle.action_proposals
            ]
            action_runs = [
                {
                    "id": run.id,
                    "project_id": run.project_id,
                    "action_proposal_id": run.action_proposal_id,
                    "action_type": run.action_type,
                    "status": "cancelled" if run.status in {"queued", "running"} else run.status,
                    "executor_id": run.executor_id,
                    "target": run.target,
                    "payload_json": dump_json(run.redacted_payload),
                    "redacted_payload_json": dump_json(run.redacted_payload),
                    "external_id": run.external_id,
                    "trace_id": run.trace_id,
                    "error_code": "RestoreSuppressed"
                    if run.status in {"queued", "running"}
                    else run.error_code,
                    "error": "Suppressed during restore"
                    if run.status in {"queued", "running"}
                    else run.error,
                    "started_at": run.started_at,
                    "finished_at": restore_timestamp
                    if run.status in {"queued", "running"}
                    else run.finished_at,
                }
                for run in bundle.action_runs
            ]
            outcomes = [
                {
                    "id": outcome.id,
                    "project_id": outcome.project_id,
                    "action_run_id": outcome.action_run_id,
                    "attention_item_id": outcome.attention_item_id,
                    "alert_id": outcome.alert_id,
                    "status": outcome.status,
                    "title": outcome.title,
                    "summary": outcome.summary,
                    "result_json": dump_json(outcome.result),
                    "actor_id": outcome.actor_id,
                    "occurred_at": outcome.occurred_at,
                    "created_at": outcome.created_at,
                }
                for outcome in bundle.outcomes
            ]
            feedback_events = [
                {
                    "id": feedback.id,
                    "project_id": feedback.project_id,
                    "outcome_id": feedback.outcome_id,
                    "action_run_id": feedback.action_run_id,
                    "attention_item_id": feedback.attention_item_id,
                    "kind": feedback.kind,
                    "summary": feedback.summary,
                    "effect_json": dump_json(feedback.effect),
                    "proposed_value_json": dump_json(feedback.proposed_value) if feedback.proposed_value is not None else None,
                    "actor_id": feedback.actor_id,
                    "created_at": feedback.created_at,
                }
                for feedback in bundle.feedback_events
            ]
            agent_context_clients = [
                {
                    "id": client.id,
                    "project_id": client.project_id,
                    "display_name": client.display_name,
                    "runtime_kind": client.runtime_kind,
                    "status": "revoked",
                    "created_by": client.created_by,
                    "token_hash": "restored:revoked",
                    "scopes_json": dump_json(client.scopes),
                    "settings_json": dump_json(client.settings),
                    "created_at": client.created_at,
                    "updated_at": restore_timestamp,
                    "last_seen_at": client.last_seen_at,
                    "revoked_at": restore_timestamp,
                }
                for client in bundle.agent_context_clients
            ]
            agent_context_sessions = [
                {
                    "id": session.id,
                    "project_id": session.project_id,
                    "client_id": session.client_id,
                    "runtime_kind": session.runtime_kind,
                    "authority": session.authority,
                    "status": "cancelled" if session.status == "running" else session.status,
                    "title": session.title,
                    "workspace_root": session.workspace_root,
                    "repository_uri": session.repository_uri,
                    "branch": session.branch,
                    "commit_sha": session.commit_sha,
                    "metadata_json": dump_json(session.metadata),
                    "started_at": session.started_at,
                    "ended_at": restore_timestamp if session.status == "running" else session.ended_at,
                    "updated_at": restore_timestamp if session.status == "running" else session.updated_at,
                }
                for session in bundle.agent_context_sessions
            ]
            agent_context_artifacts = [
                {
                    "id": artifact.id,
                    "project_id": artifact.project_id,
                    "session_id": artifact.session_id,
                    "kind": artifact.kind,
                    "uri": artifact.uri,
                    "path": artifact.path,
                    "title": artifact.title,
                    "content_type": artifact.content_type,
                    "checksum": artifact.checksum,
                    "metadata_json": dump_json(artifact.metadata),
                    "created_at": artifact.created_at,
                    "updated_at": artifact.updated_at,
                }
                for artifact in bundle.agent_context_artifacts
            ]
            agent_context_blob_content_by_id = {
                content.blob_id: content.encrypted_content for content in bundle.agent_context_blob_contents
            }
            restored_blob_object_keys: dict[str, str] = {}
            if self.object_store is not None:
                for blob_id, envelope in agent_context_blob_content_by_id.items():
                    object_key = f"{bundle.project.id}/agent-context/restored/{blob_id}.gvenc"
                    self.object_store.put_bytes(
                        object_key,
                        envelope.encode("utf-8"),
                        content_type="application/vnd.graphview.encrypted-context",
                        checksum=hashlib.sha256(envelope.encode("utf-8")).hexdigest(),
                    )
                    restored_blob_object_keys[blob_id] = object_key
            agent_context_blobs = [
                {
                    "id": blob.id,
                    "project_id": blob.project_id,
                    "session_id": blob.session_id,
                    "artifact_id": blob.artifact_id,
                    "content_kind": blob.content_kind,
                    "media_type": blob.media_type,
                    "redaction_status": blob.redaction_status
                    if agent_context_blob_content_by_id.get(blob.id)
                    else "metadata_only",
                    "encryption_status": blob.encryption_status
                    if agent_context_blob_content_by_id.get(blob.id)
                    else "metadata_only",
                    "checksum": blob.checksum,
                    "byte_count": blob.byte_count,
                    "token_count": blob.token_count,
                    "encrypted_content": None
                    if blob.id in restored_blob_object_keys
                    else agent_context_blob_content_by_id.get(blob.id),
                    "object_key": restored_blob_object_keys.get(blob.id),
                    "metadata_json": dump_json(blob.metadata),
                    "created_at": blob.created_at,
                    "expires_at": blob.expires_at,
                }
                for blob in bundle.agent_context_blobs
            ]
            agent_context_events = [
                {
                    "id": event.id,
                    "project_id": event.project_id,
                    "session_id": event.session_id,
                    "client_event_id": event.client_event_id,
                    "sequence": event.sequence,
                    "event_kind": event.event_kind,
                    "authority": event.authority,
                    "status": event.status,
                    "summary": event.summary,
                    "checksum": event.checksum,
                    "artifact_id": event.artifact_id,
                    "blob_id": event.blob_id,
                    "payload_json": dump_json(event.payload),
                    "object_refs_json": dump_json(event.object_refs),
                    "occurred_at": event.occurred_at,
                    "received_at": event.received_at,
                }
                for event in bundle.agent_context_events
            ]

            if graph_version:
                conn.execute(insert(db.graph_versions).values(**graph_version))
            for table, rows in [
                (db.topics, topics),
                (db.connector_accounts, connector_accounts),
                (db.connector_targets, connector_targets),
                (db.connector_sync_runs, connector_sync_runs),
                (db.graph_layouts, graph_layouts),
                (db.sources, sources),
                (db.source_chunks, source_chunks),
                (db.content_nodes, nodes),
                (db.graph_layout_positions, graph_layout_positions),
                (db.semantic_edges, edges),
                (db.ingestion_runs, ingestion_runs),
                (db.extraction_proposals, proposals),
                (db.content_embeddings, embeddings),
                (db.review_decisions, review_decisions),
                (db.planning_sessions, planning_sessions),
                (db.graph_build_specs, graph_build_specs),
                (db.agent_runs, agent_runs),
                (db.agent_steps, agent_steps),
                (db.planning_messages, planning_messages),
                (db.research_tasks, research_tasks),
                (db.agent_action_proposals, agent_action_proposals),
                (db.graph_activity_events, activity_events),
                (db.signals, signals),
                (db.observations, observations),
                (db.owners, owners),
                (db.routing_policies, routing_policies),
                (db.alerts, alerts),
                (db.attention_items, attention_items),
                (db.decision_records, decision_records),
                (db.action_proposals, action_proposals),
                (db.action_runs, action_runs),
                (db.outcomes, outcomes),
                (db.feedback_events, feedback_events),
                (db.agent_context_clients, agent_context_clients),
                (db.agent_context_sessions, agent_context_sessions),
                (db.agent_context_artifacts, agent_context_artifacts),
                (db.agent_context_blobs, agent_context_blobs),
                (db.agent_context_events, agent_context_events),
            ]:
                if rows:
                    conn.execute(insert(table), rows)
            if graph_settings:
                conn.execute(insert(db.graph_settings).values(**graph_settings))
            elif project_id == DEFAULT_PROJECT_ID:
                timestamp = now()
                conn.execute(
                    insert(db.graph_settings).values(
                        project_id=DEFAULT_PROJECT_ID,
                        llm_enabled=False,
                        llm_provider="openai-compatible",
                        llm_model=None,
                        auto_commit_threshold=self.auto_commit_threshold,
                        settings_json=dump_json({}),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )

            conn.execute(
                insert(db.audit_events).values(
                    id=new_id("audit"),
                    project_id=project_id,
                    actor_id=actor_id,
                    action="project.restore",
                    resource_type="project",
                    resource_id=project_id,
                    outcome="succeeded",
                    summary="Restored a logical project bundle with side effects suppressed.",
                    metadata_json=dump_json(
                        {
                            "source_count": len(bundle.sources),
                            "node_count": len(bundle.nodes),
                            "edge_count": len(bundle.edges),
                            "layout_count": len(bundle.graph_layouts),
                            "connector_account_count": len(bundle.connector_accounts),
                        }
                    ),
                    trace_id=new_id("trace"),
                    occurred_at=restore_timestamp,
                )
            )

        return self.export_bundle()

    def _upsert_connector_source(self, conn, document: NormalizedSourceDocument, timestamp: datetime, *, target_id: str) -> dict:
        source_id = stable_id("src", document.connector_kind, document.remote_id)
        metadata = {**document.metadata, "targetId": target_id}
        values = {
            "id": source_id,
            "project_id": DEFAULT_PROJECT_ID,
            "kind": document.source_kind,
            "title": document.title,
            "uri": document.uri,
            "object_key": f"{document.connector_kind}/{document.remote_id}",
            "checksum": document.checksum,
            "connector_kind": document.connector_kind,
            "remote_id": document.remote_id,
            "remote_parent_id": document.remote_parent_id,
            "remote_modified_at": document.remote_modified_at,
            "remote_url": document.remote_url,
            "metadata_json": dump_json(metadata),
            "stale_at": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        existing = conn.execute(
            select(db.sources.c.id).where(
                and_(db.sources.c.project_id == DEFAULT_PROJECT_ID, db.sources.c.id == source_id)
            )
        ).first()
        if existing is None:
            conn.execute(insert(db.sources).values(**values))
        else:
            update_values = {key: value for key, value in values.items() if key not in {"id", "project_id", "created_at"}}
            conn.execute(update(db.sources).where(db.sources.c.id == source_id).values(**update_values))
        return self._source_from_row(values)

    def _ensure_topics_for_heading_path(self, conn, heading_path: list[str], timestamp: datetime) -> None:
        parent_id = None
        for depth, heading in enumerate(heading_path):
            if not heading:
                continue
            topic_id = stable_id("topic", *heading_path[: depth + 1])
            existing = conn.execute(
                select(db.topics.c.id).where(and_(db.topics.c.id == topic_id, db.topics.c.project_id == DEFAULT_PROJECT_ID))
            ).first()
            if existing is None:
                conn.execute(
                    insert(db.topics).values(
                        id=topic_id,
                        project_id=DEFAULT_PROJECT_ID,
                        name=heading[:240],
                        description=f"Imported heading path: {' / '.join(heading_path[: depth + 1])}",
                        parent_topic_id=parent_id,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            parent_id = topic_id

    def _proposal_value_exists(self, conn, kind: str, value: dict) -> bool:
        proposed_id = value.get("id")
        for row in conn.execute(
            select(db.extraction_proposals).where(
                and_(
                    db.extraction_proposals.c.project_id == DEFAULT_PROJECT_ID,
                    db.extraction_proposals.c.kind == kind,
                )
            )
        ).mappings():
            existing = load_json(json_value(row, "proposed_value_json"), {})
            if proposed_id and existing.get("id") == proposed_id:
                return True
            if kind == "content_node" and existing.get("label") == value.get("label"):
                return True
            if kind == "semantic_edge" and (
                existing.get("sourceNodeId"),
                existing.get("targetNodeId"),
                existing.get("relation"),
            ) == (
                value.get("sourceNodeId"),
                value.get("targetNodeId"),
                value.get("relation"),
            ):
                return True
        return False

    def _planning_session_with_children(self, session: dict) -> dict:
        with self.engine.begin() as conn:
            messages = [
                self._planning_message_from_row(row)
                for row in conn.execute(
                    select(db.planning_messages)
                    .where(db.planning_messages.c.session_id == session["id"])
                    .order_by(db.planning_messages.c.created_at, db.planning_messages.c.id)
                ).mappings()
            ]
            build_spec_row = conn.execute(
                select(db.graph_build_specs)
                .where(db.graph_build_specs.c.session_id == session["id"])
                .order_by(db.graph_build_specs.c.version.desc())
            ).mappings().first()
        role_order = {"system": 0, "user": 1, "assistant": 2}
        session["messages"] = sorted(
            messages,
            key=lambda message: (
                message["created_at"],
                message.get("agent_run_id") or "",
                role_order.get(message["role"], 9),
                message["id"],
            ),
        )
        session["build_spec"] = self._graph_build_spec_from_row(build_spec_row) if build_spec_row else None
        return session

    def _agent_step_row(
        self,
        *,
        project_id: str,
        agent_run_id: str,
        name: str,
        status: str,
        input_summary: str | None,
        output_summary: str | None,
        trace_id: str,
        timestamp: datetime,
        error: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        return {
            "id": new_id("agentstep"),
            "project_id": project_id,
            "agent_run_id": agent_run_id,
            "name": name,
            "status": status,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "error": error,
            "trace_id": trace_id,
            "metadata_json": dump_json(metadata or {}),
            "started_at": timestamp,
            "finished_at": timestamp if status in {"completed", "failed", "waiting_for_review"} else None,
        }

    def _agent_citations_from_context(self, *, nodes: list[dict], sources: list[dict], chunks: list[dict]) -> list[dict]:
        citations: list[dict] = []
        seen: set[str] = set()
        sources_by_id = {source["id"]: source for source in sources}
        for chunk in chunks:
            source = sources_by_id.get(chunk["source_id"])
            citation_id = f"citation-{chunk['id']}"
            seen.add(citation_id)
            citations.append(
                {
                    "id": citation_id,
                    "label": chunk["heading_path"][0] if chunk["heading_path"] else source["title"] if source else "Source chunk",
                    "source_id": chunk["source_id"],
                    "source_title": source["title"] if source else None,
                    "source_chunk_id": chunk["id"],
                    "node_id": None,
                    "proposal_id": None,
                    "locator": chunk["locator"],
                    "quote": chunk["text"][:360],
                    "url": source.get("remote_url") or source.get("uri") if source else None,
                    "confidence": 0.76,
                }
            )
        for node in nodes:
            citation_id = f"citation-{node['id']}"
            if citation_id in seen:
                continue
            provenance = node.get("provenance", [{}])[0] if node.get("provenance") else {}
            source = sources_by_id.get(provenance.get("sourceId"))
            citations.append(
                {
                    "id": citation_id,
                    "label": node["label"],
                    "source_id": provenance.get("sourceId"),
                    "source_title": source["title"] if source else None,
                    "source_chunk_id": None,
                    "node_id": node["id"],
                    "proposal_id": None,
                    "locator": provenance.get("locator"),
                    "quote": node.get("summary"),
                    "url": source.get("remote_url") or source.get("uri") if source else None,
                    "confidence": 0.7,
                }
            )
        return citations[:10]

    def _planning_session_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        data.setdefault("messages", [])
        data.setdefault("build_spec", None)
        return data

    def _planning_message_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _graph_build_spec_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["spec"] = load_json(data.pop("spec_json"), {})
        return data

    def _agent_run_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["input"] = load_json(data.pop("input_json"), {})
        data["output"] = load_json(data.pop("output_json"), {})
        data["mode"] = data["input"].get("_agent_mode") or ("planning" if data.get("planning_session_id") or data.get("kind") == "planning" else "graph")
        data["focus_target"] = data["input"].get("_focus_target")
        data.setdefault("steps", [])
        data["tool_calls"] = data["output"].get("tool_calls") or self._agent_tool_calls_from_run(data)
        data["generated_artifacts"] = data["output"].get("generated_artifacts") or self._agent_artifacts_from_run(data)
        data.setdefault("action_proposals", [])
        return data

    def _agent_tool_calls_from_run(self, run: dict) -> list[dict]:
        status_by_run_status = {
            "queued": "running",
            "running": "running",
            "waiting_for_review": "pending_review",
            "completed": "succeeded",
            "failed": "failed",
            "cancelled": "blocked",
        }
        kind_by_run_kind = {
            "planning": "graph_query",
            "graph_query": "graph_query",
            "research": "research_run",
            "action_apply": "review_action",
        }
        output = run.get("output", {})
        input_payload = run.get("input", {})
        affected_graph_ids = [
            str(item)
            for item in [
                input_payload.get("node_id"),
                input_payload.get("source_id"),
                output.get("source_id"),
                *(output.get("proposal_ids") or []),
            ]
            if item
        ]
        return [
            {
                "id": f"{run['id']}-tool",
                "kind": kind_by_run_kind.get(run.get("kind"), "graph_query"),
                "input": {key: value for key, value in input_payload.items() if not str(key).startswith("_")},
                "status": status_by_run_status.get(run.get("status"), "succeeded"),
                "citations": output.get("citations") or [],
                "affected_graph_ids": affected_graph_ids,
                "resulting_proposal_id": (output.get("proposal_ids") or [None])[0],
                "summary": output.get("answer") or output.get("message") or run.get("kind"),
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
            }
        ]

    def _agent_artifacts_from_run(self, run: dict) -> list[dict]:
        output = run.get("output", {})
        if "build_spec" in output:
            return [
                {
                    "id": f"{run['id']}-artifact-plan",
                    "kind": "plan",
                    "title": str(output.get("build_spec", {}).get("title") or "Generated plan"),
                    "payload": output.get("build_spec") or {},
                    "citations": output.get("citations") or [],
                }
            ]
        if output.get("source_id") or output.get("proposal_ids"):
            return [
                {
                    "id": f"{run['id']}-artifact-evidence",
                    "kind": "evidence_bundle",
                    "title": "Research evidence",
                    "payload": {
                        "source_id": output.get("source_id"),
                        "proposal_ids": output.get("proposal_ids") or [],
                    },
                    "citations": output.get("citations") or [],
                }
            ]
        return []

    def _agent_step_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _research_task_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["result"] = load_json(data.pop("result_json"), {})
        return data

    def _agent_action_proposal_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["payload"] = load_json(data.pop("payload_json"), {})
        data["citations"] = load_json(data.pop("citations_json"), [])
        return data

    def _signal_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["payload"] = self._redact_payload(load_json(data.pop("payload_json"), {}))
        return data

    def _observation_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["evidence"] = load_json(data.pop("evidence_json"), [])
        data["object_refs"] = load_json(data.pop("object_refs_json"), [])
        data["source_ids"] = load_json(data.pop("source_ids_json"), [])
        data["node_ids"] = load_json(data.pop("node_ids_json"), [])
        data["edge_ids"] = load_json(data.pop("edge_ids_json"), [])
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _owner_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _routing_policy_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["match"] = load_json(data.pop("match_json"), {})
        data["suggested_actions"] = load_json(data.pop("suggested_actions_json"), [])
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _alert_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["object_refs"] = load_json(data.pop("object_refs_json"), [])
        return data

    def _attention_item_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["object_refs"] = load_json(data.pop("object_refs_json"), [])
        data["evidence"] = load_json(data.pop("evidence_json"), [])
        data["suggested_actions"] = load_json(data.pop("suggested_actions_json"), [])
        data["blockers"] = load_json(data.pop("blockers_json"), [])
        data["sla_status"] = self._sla_status(data.get("due_at"), now())
        return data

    def _decision_record_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["evidence"] = load_json(data.pop("evidence_json"), [])
        data["object_refs"] = load_json(data.pop("object_refs_json"), [])
        return data

    def _action_proposal_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("payload_json", None)
        data["redacted_payload"] = load_json(data.pop("redacted_payload_json"), {})
        data["safety"] = load_json(data.pop("safety_json"), {})
        return data

    def _action_run_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("payload_json", None)
        data["redacted_payload"] = load_json(data.pop("redacted_payload_json"), {})
        return data

    def _outcome_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["result"] = load_json(data.pop("result_json"), {})
        return data

    def _feedback_event_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["effect"] = load_json(data.pop("effect_json"), {})
        data["proposed_value"] = load_json(data.pop("proposed_value_json"), None)
        return data
