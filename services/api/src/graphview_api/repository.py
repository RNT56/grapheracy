from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Engine, and_, insert, or_, select, text, update

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
from graphview_api.repository_operations import DataOperationsRepositoryMixin
from graphview_api.repository_review import ReviewRepositoryMixin
from graphview_api.repository_serialization import RepositorySerializationMixin
from graphview_api.repository_secrets import SecretRepositoryMixin
from graphview_api.repository_sources import SourceCatalogRepositoryMixin
from graphview_api.redaction import redact_sensitive_text
from graphview_api.schemas import SignalCreate

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
    DataOperationsRepositoryMixin,
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
