from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
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
from graphview_api.repository_connectors import ConnectorRepositoryMixin
from graphview_api.repository_secrets import SecretRepositoryMixin
from graphview_api.schemas import (
    AgentActionApprovalCreate,
    ActionProposalCreate,
    ActionProposalDecision,
    ActionRunCreate,
    AlertAssign,
    AgentContextClientCreate,
    AgentContextEventBatchCreate,
    AgentContextSessionCreate,
    AgentContextSessionUpdate,
    AttentionTransition,
    DecisionRecordCreate,
    FeedbackEventCreate,
    AgentRunCreate,
    ExportBundle,
    GraphBuildSpecCreate,
    GraphQueryCreate,
    GraphResearchCreate,
    GraphSettingsUpdate,
    ObservationCreate,
    OutcomeCreate,
    OwnerCreate,
    OwnerUpdate,
    PlanningMessageCreate,
    PlanningSessionCreate,
    ProposalCreate,
    RoutingPolicyCreate,
    RoutingPolicyUpdate,
    ReviewDecisionCreate,
    SignalCreate,
    SourceCreate,
    SourceUpdate,
)

DEFAULT_PROJECT_ID = "project-default"
DEMO_PROJECT_ID = "project-ios26-swift-demo"


@dataclass(frozen=True)
class GraphViewSpec:
    id: str
    project_id: str
    label: str
    description: str | None
    kind: str
    source_ids: tuple[str, ...] = ()


ENGINEERING_NODE_KINDS = {"system", "component", "service", "api", "repository", "module", "package", "file", "symbol"}
OPS_NODE_KINDS = {
    "workflow",
    "policy",
    "process",
    "vendor",
    "decision",
    "requirement",
    "risk",
    "event",
    "incident",
    "project",
    "owner",
    "review_cycle",
    "task",
    "team",
    "organization",
}
RESEARCH_NODE_KINDS = {"concept", "topic", "term", "document", "source", "dataset"}
ENGINEERING_RELATIONS = {"depends_on", "defines", "imports", "implements", "contains", "references"}
OPS_RELATIONS = {"owned_by", "has_review_cycle", "governs", "supports", "depends_on"}
RESEARCH_RELATIONS = {"supports", "contradicts", "causes", "mentions", "defines", "relates_to", "references"}
GRAPH_LENSES = ("research", "engineering", "ops")
SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
SENSITIVE_PAYLOAD_KEYS = {"token", "secret", "password", "api_key", "apikey", "authorization", "credential", "credentials"}
AI_PROVIDER_IDS = {"openai", "anthropic", "gemini"}
AI_PROVIDER_CREDENTIALS_KEY = "ai_provider_credentials"
AI_DEFAULT_PROVIDER_KEY = "ai_default_provider"
SENSITIVE_SETTINGS_KEYS = SENSITIVE_PAYLOAD_KEYS | {
    "access_token",
    "encrypted_api_key",
    "llm_api_key",
    "refresh_token",
}
AGENT_CONTEXT_CAPTURE_SCOPE = "context:capture"
AGENT_CONTEXT_DEFAULT_DENIED_PATTERNS = (".env", "id_rsa", "id_ed25519", ".pem", ".p12")
AGENT_CONTEXT_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*([^\s'\"`]+)"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


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


def load_json(value: str | None, fallback: object):
    if value is None:
        return fallback
    return json.loads(value)


class GraphRepository(ActionRepositoryMixin, ConnectorRepositoryMixin, SecretRepositoryMixin):
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

    def list_graph_views(self) -> list[dict]:
        with self.engine.begin() as conn:
            project_rows = [normalize_json_row(row) for row in conn.execute(select(db.graph_projects)).mappings()]

        specs = [self._project_view_spec(project) for project in project_rows]
        if any(project["id"] == DEMO_PROJECT_ID for project in project_rows):
            specs.extend(self._demo_scope_specs())

        return [self._graph_view_summary(spec) for spec in specs]

    def _project_view_spec(self, project: dict) -> GraphViewSpec:
        return GraphViewSpec(
            id=project["id"],
            project_id=project["id"],
            label=project["name"],
            description=project.get("description"),
            kind="project",
        )

    def _demo_scope_specs(self) -> list[GraphViewSpec]:
        return [
            GraphViewSpec(
                id=f"{DEMO_PROJECT_ID}:planning",
                project_id=DEMO_PROJECT_ID,
                label="iOS 26 Planning Scope",
                description="Product, architecture, design, privacy, testing, and release planning from the full iOS demo graph.",
                kind="scope",
                source_ids=("src-team-blueprint", "src-liquid-glass"),
            ),
            GraphViewSpec(
                id=f"{DEMO_PROJECT_ID}:platform-services",
                project_id=DEMO_PROJECT_ID,
                label="iOS Platform Services Scope",
                description="SwiftUI, SwiftData, App Intents, widgets, Siri, and Apple documentation links from the full iOS demo graph.",
                kind="scope",
                source_ids=("src-swiftui-docs", "src-swiftdata", "src-app-intents", "src-ios26-whats-new"),
            ),
        ]

    def _graph_view_spec(self, graph_id: str | None = None) -> GraphViewSpec:
        requested_id = graph_id or DEFAULT_PROJECT_ID
        for spec in self._demo_scope_specs():
            if spec.id == requested_id:
                return spec
        with self.engine.begin() as conn:
            row = conn.execute(select(db.graph_projects).where(db.graph_projects.c.id == requested_id)).mappings().first()
            if row is not None:
                return self._project_view_spec(normalize_json_row(row))
            fallback = conn.execute(
                select(db.graph_projects).where(db.graph_projects.c.id == DEFAULT_PROJECT_ID)
            ).mappings().one()
        return self._project_view_spec(dict(fallback))

    def _graph_view_summary(self, spec: GraphViewSpec) -> dict:
        project, nodes, edges = self.graph(spec.id)
        sources = self.list_sources(graph_id=spec.id)
        proposals = self.list_proposals(graph_id=spec.id)
        return {
            "id": spec.id,
            "project_id": spec.project_id,
            "label": spec.label,
            "description": spec.description,
            "kind": spec.kind,
            "source_ids": list(spec.source_ids),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source_count": len(sources),
            "pending_proposal_count": sum(1 for proposal in proposals if proposal["status"] == "pending_review"),
        }

    def project(self) -> dict:
        with self.engine.begin() as conn:
            return dict(
                conn.execute(
                    select(db.graph_projects).where(db.graph_projects.c.id == DEFAULT_PROJECT_ID)
                ).mappings().one()
            )

    def graph(self, graph_id: str | None = None, lens: str | None = None) -> tuple[dict, list[dict], list[dict]]:
        normalized_lens = normalize_graph_lens(lens)
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            project = dict(
                conn.execute(
                    select(db.graph_projects).where(db.graph_projects.c.id == spec.project_id)
                ).mappings().one()
            )
            nodes = [
                self._node_from_row(row)
                for row in conn.execute(
                    select(db.content_nodes).where(db.content_nodes.c.project_id == spec.project_id)
                ).mappings()
            ]
            edges = [
                self._edge_from_row(row)
                for row in conn.execute(
                    select(db.semantic_edges).where(db.semantic_edges.c.project_id == spec.project_id)
                ).mappings()
            ]
        if spec.source_ids:
            nodes = [node for node in nodes if self._item_matches_sources(node, spec.source_ids)]
            included_node_ids = {node["id"] for node in nodes}
            edges = [
                edge
                for edge in edges
                if self._item_matches_sources(edge, spec.source_ids)
                or (edge["source_node_id"] in included_node_ids and edge["target_node_id"] in included_node_ids)
            ]
        if normalized_lens != "all":
            nodes, edges = self._apply_graph_lens(nodes, edges, normalized_lens)
        if spec.kind == "scope":
            project = {**project, "name": spec.label, "description": spec.description}
        return project, nodes, edges

    def _item_matches_sources(self, item: dict, source_ids: tuple[str, ...]) -> bool:
        source_id_set = set(source_ids)
        return any(provenance.get("sourceId") in source_id_set for provenance in item.get("provenance", []))

    def _apply_graph_lens(self, nodes: list[dict], edges: list[dict], lens: str) -> tuple[list[dict], list[dict]]:
        initial_node_ids = {node["id"] for node in nodes if self._node_matches_lens(node, lens)}
        lens_edge_ids = {
            edge["id"]
            for edge in edges
            if self._edge_matches_lens(edge, lens)
            or (edge["source_node_id"] in initial_node_ids and edge["target_node_id"] in initial_node_ids)
        }
        included_node_ids = set(initial_node_ids)
        for edge in edges:
            if edge["id"] in lens_edge_ids:
                included_node_ids.add(edge["source_node_id"])
                included_node_ids.add(edge["target_node_id"])
        filtered_nodes = [node for node in nodes if node["id"] in included_node_ids]
        node_ids = {node["id"] for node in filtered_nodes}
        filtered_edges = [
            edge
            for edge in edges
            if edge["id"] in lens_edge_ids and edge["source_node_id"] in node_ids and edge["target_node_id"] in node_ids
        ]
        return filtered_nodes, filtered_edges

    def _node_matches_lens(self, node: dict, lens: str) -> bool:
        metadata = node.get("metadata", {})
        if self._metadata_has_lens(metadata, lens) or self._legacy_mode_matches_lens(metadata, lens):
            return True
        label = str(node.get("label") or "")
        kind = str(node.get("kind") or "")
        if lens == "engineering":
            return kind in ENGINEERING_NODE_KINDS or bool(re.search(r"^(Repository|Path|Symbol|Dependency|Issue|PR)\b", label, flags=re.IGNORECASE))
        if lens == "ops":
            return kind in OPS_NODE_KINDS or bool(re.search(r"\b(policy|process|vendor|incident|project|owner|review)\b", label, flags=re.IGNORECASE))
        return kind in RESEARCH_NODE_KINDS

    def _edge_matches_lens(self, edge: dict, lens: str) -> bool:
        metadata = edge.get("metadata", {})
        if self._metadata_has_lens(metadata, lens) or self._legacy_mode_matches_lens(metadata, lens):
            return True
        relation = str(edge.get("relation") or "")
        if lens == "engineering":
            return relation in ENGINEERING_RELATIONS
        if lens == "ops":
            return relation in OPS_RELATIONS
        return relation in RESEARCH_RELATIONS

    def _proposal_matches_lens(self, proposal: dict, lens: str) -> bool:
        if lens == "all":
            return True
        value = proposal.get("proposed_value", {})
        metadata = value.get("metadata", {}) if isinstance(value, dict) else {}
        if self._metadata_has_lens(metadata, lens) or self._legacy_mode_matches_lens(metadata, lens):
            return True
        if proposal.get("kind") == "semantic_edge":
            relation = str(value.get("relation") or "")
            if lens == "engineering":
                return relation in ENGINEERING_RELATIONS
            if lens == "ops":
                return relation in OPS_RELATIONS
            return relation in RESEARCH_RELATIONS
        node = {"label": value.get("label"), "kind": value.get("kind"), "metadata": metadata}
        return self._node_matches_lens(node, lens)

    def _metadata_has_lens(self, metadata: dict, lens: str) -> bool:
        lenses = metadata.get("extractionLenses")
        return isinstance(lenses, list) and lens in lenses

    def _legacy_mode_matches_lens(self, metadata: dict, lens: str) -> bool:
        mode = metadata.get("mode")
        return (
            (mode == "engineering-repository" and lens == "engineering")
            or (mode == "ops-document-map" and lens == "ops")
            or (mode == "research" and lens == "research")
        )

    def neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        limit: int = 25,
        graph_id: str | None = None,
        lens: str | None = None,
    ) -> dict | None:
        normalized_depth = min(2, max(1, depth))
        normalized_limit = min(100, max(1, limit))
        _, nodes, edges = self.graph(graph_id, lens)

        nodes_by_id = {node["id"]: node for node in nodes}
        if node_id not in nodes_by_id:
            return None

        adjacency: dict[str, set[str]] = {node["id"]: set() for node in nodes}
        degree_by_node_id = {node["id"]: 0 for node in nodes}
        for edge in edges:
            source_id = edge["source_node_id"]
            target_id = edge["target_node_id"]
            if source_id not in nodes_by_id or target_id not in nodes_by_id:
                continue
            adjacency[source_id].add(target_id)
            adjacency[target_id].add(source_id)
            degree_by_node_id[source_id] += 1
            degree_by_node_id[target_id] += 1

        distance_by_node_id = {node_id: 0}
        frontier = {node_id}
        for distance in range(1, normalized_depth + 1):
            next_ids = {
                neighbor_id
                for current_id in frontier
                for neighbor_id in adjacency.get(current_id, set())
                if neighbor_id not in distance_by_node_id
            }
            for next_id in next_ids:
                distance_by_node_id[next_id] = distance
            frontier = next_ids

        ranked_node_ids = sorted(
            distance_by_node_id,
            key=lambda current_id: (
                distance_by_node_id[current_id],
                -degree_by_node_id.get(current_id, 0),
                nodes_by_id[current_id]["label"],
                current_id,
            ),
        )
        included_ids = set(ranked_node_ids[:normalized_limit])
        included_ids.add(node_id)
        ordered_included_ids = [current_id for current_id in ranked_node_ids if current_id in included_ids]

        neighborhood_edges = [
            edge
            for edge in sorted(
                edges,
                key=lambda item: (
                    item["source_node_id"],
                    item["target_node_id"],
                    item["relation"],
                    item["id"],
                ),
            )
            if edge["source_node_id"] in included_ids and edge["target_node_id"] in included_ids
        ]
        edge_limit = normalized_limit * 2
        returned_edges = neighborhood_edges[:edge_limit]

        return {
            "center_node": nodes_by_id[node_id],
            "depth": normalized_depth,
            "limit": normalized_limit,
            "nodes": [nodes_by_id[current_id] for current_id in ordered_included_ids],
            "edges": returned_edges,
            "omitted_node_count": max(0, len(ranked_node_ids) - len(included_ids)),
            "omitted_edge_count": max(0, len(neighborhood_edges) - len(returned_edges)),
        }

    def path(
        self,
        source_node_id: str,
        target_node_id: str,
        *,
        max_depth: int = 4,
        graph_id: str | None = None,
        lens: str | None = None,
    ) -> dict | None:
        normalized_max_depth = min(6, max(1, max_depth))
        _, nodes, edges = self.graph(graph_id, lens)

        nodes_by_id = {node["id"]: node for node in nodes}
        source_node = nodes_by_id.get(source_node_id)
        target_node = nodes_by_id.get(target_node_id)
        if source_node is None or target_node is None:
            return None

        if source_node_id == target_node_id:
            return {
                "source_node": source_node,
                "target_node": target_node,
                "max_depth": normalized_max_depth,
                "path_found": True,
                "distance": 0,
                "nodes": [source_node],
                "edges": [],
            }

        edges_by_id = {edge["id"]: edge for edge in edges}
        adjacency: dict[str, list[tuple[str, str]]] = {node["id"]: [] for node in nodes}
        for edge in edges:
            source_id = edge["source_node_id"]
            target_id = edge["target_node_id"]
            if source_id not in nodes_by_id or target_id not in nodes_by_id:
                continue
            adjacency[source_id].append((target_id, edge["id"]))
            adjacency[target_id].append((source_id, edge["id"]))

        for node_id, neighbors in adjacency.items():
            neighbors.sort(
                key=lambda item: (
                    nodes_by_id[item[0]]["label"],
                    item[0],
                    edges_by_id[item[1]]["relation"],
                    item[1],
                )
            )

        queue: list[str] = [source_node_id]
        distance_by_node_id = {source_node_id: 0}
        parent_by_node_id: dict[str, tuple[str, str]] = {}
        found = False
        index = 0
        while index < len(queue) and not found:
            current_id = queue[index]
            index += 1
            current_distance = distance_by_node_id[current_id]
            if current_distance >= normalized_max_depth:
                continue
            for neighbor_id, edge_id in adjacency.get(current_id, []):
                if neighbor_id in distance_by_node_id:
                    continue
                distance_by_node_id[neighbor_id] = current_distance + 1
                parent_by_node_id[neighbor_id] = (current_id, edge_id)
                if neighbor_id == target_node_id:
                    found = True
                    break
                queue.append(neighbor_id)

        if target_node_id not in parent_by_node_id:
            return {
                "source_node": source_node,
                "target_node": target_node,
                "max_depth": normalized_max_depth,
                "path_found": False,
                "distance": None,
                "nodes": [],
                "edges": [],
            }

        path_node_ids = [target_node_id]
        path_edge_ids: list[str] = []
        current_id = target_node_id
        while current_id != source_node_id:
            parent_id, edge_id = parent_by_node_id[current_id]
            path_node_ids.append(parent_id)
            path_edge_ids.append(edge_id)
            current_id = parent_id
        path_node_ids.reverse()
        path_edge_ids.reverse()

        return {
            "source_node": source_node,
            "target_node": target_node,
            "max_depth": normalized_max_depth,
            "path_found": True,
            "distance": len(path_edge_ids),
            "nodes": [nodes_by_id[node_id] for node_id in path_node_ids],
            "edges": [edges_by_id[edge_id] for edge_id in path_edge_ids],
        }

    def insights(self, graph_id: str | None = None, lens: str | None = None) -> dict:
        project, nodes, edges = self.graph(graph_id, lens)
        sources = self.list_sources(graph_id=graph_id)
        proposals = self.list_proposals(graph_id=graph_id, lens=lens)
        proposal_ids = {proposal["id"] for proposal in proposals}
        decisions = [
            decision
            for decision in self.list_review_decisions(graph_id=graph_id)
            if decision["proposal_id"] in proposal_ids
        ]

        node_ids = {node["id"] for node in nodes}
        degree_by_node_id = {node["id"]: 0 for node in nodes}
        connected_edge_count = 0
        for edge in edges:
            source_exists = edge["source_node_id"] in node_ids
            target_exists = edge["target_node_id"] in node_ids
            if source_exists and target_exists:
                connected_edge_count += 1
                degree_by_node_id[edge["source_node_id"]] += 1
                degree_by_node_id[edge["target_node_id"]] += 1

        reviewed_items = nodes + edges
        traced_item_count = sum(1 for item in reviewed_items if item.get("provenance"))
        total_reviewed_items = len(reviewed_items)
        coverage_percent = 100.0 if total_reviewed_items == 0 else round(
            (traced_item_count / total_reviewed_items) * 100,
            2,
        )

        top_nodes = [
            {
                "id": node["id"],
                "label": node["label"],
                "kind": node["kind"],
                "degree": degree_by_node_id.get(node["id"], 0),
            }
            for node in sorted(
                nodes,
                key=lambda node: (-degree_by_node_id.get(node["id"], 0), node["label"], node["id"]),
            )[:5]
        ]

        return {
            "project_id": project["id"],
            "generated_at": now(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source_count": len(sources),
            "proposal_count": len(proposals),
            "pending_proposal_count": sum(1 for proposal in proposals if proposal["status"] == "pending_review"),
            "review_decision_count": len(decisions),
            "connected_edge_count": connected_edge_count,
            "orphan_edge_count": len(edges) - connected_edge_count,
            "provenance_coverage": {
                "reviewed_item_count": total_reviewed_items,
                "traced_item_count": traced_item_count,
                "missing_item_count": total_reviewed_items - traced_item_count,
                "coverage_percent": coverage_percent,
            },
            "source_kinds": self._count_by(sources, "kind"),
            "node_kinds": self._count_by(nodes, "kind"),
            "relation_counts": self._count_by(edges, "relation"),
            "proposal_statuses": self._count_by(proposals, "status"),
            "top_nodes": top_nodes,
        }

    def list_sources(self, query: str | None = None, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        stmt = select(db.sources).where(db.sources.c.project_id == spec.project_id)
        if spec.source_ids:
            stmt = stmt.where(db.sources.c.id.in_(spec.source_ids))
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(db.sources.c.title.like(like), db.sources.c.uri.like(like)))
        stmt = stmt.order_by(db.sources.c.created_at.desc())
        with self.engine.begin() as conn:
            return [self._source_from_row(row) for row in conn.execute(stmt).mappings()]

    def create_source(self, payload: SourceCreate, graph_id: str | None = None) -> dict:
        spec = self._graph_view_spec(graph_id)
        timestamp = now()
        source = {
            "id": new_id("src"),
            "project_id": spec.project_id,
            **self._source_values_from_payload(payload),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.sources).values(**source))
            self._record_activity_event(
                conn,
                project_id=spec.project_id,
                event_type="source.created",
                actor_id=None,
                summary=f"Added source {source['title']}.",
                object_refs=[self._activity_ref("source", source["id"], source["title"])],
                payload={"source_id": source["id"], "kind": source["kind"]},
                timestamp=timestamp,
            )
        return self._source_from_row(source)

    def update_source(self, source_id: str, payload: SourceUpdate) -> dict | None:
        values = self._source_values_from_payload(payload, exclude_unset=True)
        if not values:
            return self.get_source(source_id)
        values["updated_at"] = now()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(db.sources)
                .where(and_(db.sources.c.id == source_id, db.sources.c.project_id == DEFAULT_PROJECT_ID))
                .values(**values)
            )
            if result.rowcount == 0:
                return None
        return self.get_source(source_id)

    def get_source(self, source_id: str, project_id: str | None = None) -> dict | None:
        conditions = [db.sources.c.id == source_id]
        if project_id is not None:
            conditions.append(db.sources.c.project_id == project_id)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.sources).where(and_(*conditions))
            ).mappings().first()
            return self._source_from_row(row) if row else None

    def delete_source(self, source_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                delete(db.sources).where(
                    and_(db.sources.c.id == source_id, db.sources.c.project_id == DEFAULT_PROJECT_ID)
                )
            )
            return result.rowcount > 0

    def graph_settings(self) -> dict:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            return self._settings_from_row(row)

    def graph_settings_with_secrets(self) -> dict:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            return self._settings_from_row(row, redact=False)

    def update_graph_settings(self, payload: GraphSettingsUpdate) -> dict:
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return self.graph_settings()
        values["updated_at"] = now()
        with self.engine.begin() as conn:
            if "settings" in values:
                settings_payload = values.pop("settings") or {}
                row = conn.execute(
                    select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                ).mappings().one()
                merged_settings = load_json(json_value(row, "settings_json"), {})
                for key, value in settings_payload.items():
                    if key == "llm_api_key":
                        credentials = dict(merged_settings.get(AI_PROVIDER_CREDENTIALS_KEY) or {})
                        if value:
                            credentials["openai"] = {
                                "encrypted_api_key": self._encrypt_json({"api_key": str(value)}),
                                "updated_at": now().isoformat(),
                            }
                        else:
                            credentials.pop("openai", None)
                        merged_settings[AI_PROVIDER_CREDENTIALS_KEY] = credentials
                        merged_settings.pop("llm_api_key", None)
                        continue
                    if value is None:
                        merged_settings.pop(key, None)
                    else:
                        merged_settings[key] = value
                values["settings_json"] = dump_json(merged_settings)
            conn.execute(
                update(db.graph_settings)
                .where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                .values(**values)
            )
        return self.graph_settings()

    def ai_provider_api_keys(self) -> dict[str, str]:
        settings_doc = self.graph_settings_with_secrets()["settings"]
        credentials = settings_doc.get(AI_PROVIDER_CREDENTIALS_KEY)
        if not isinstance(credentials, dict):
            return {}
        api_keys: dict[str, str] = {}
        for provider_id, credential in credentials.items():
            if provider_id not in AI_PROVIDER_IDS or not isinstance(credential, dict):
                continue
            encrypted_api_key = credential.get("encrypted_api_key")
            if not encrypted_api_key:
                continue
            try:
                decrypted = self._decrypt_json(str(encrypted_api_key))
            except Exception:
                continue
            api_key = decrypted.get("api_key")
            if isinstance(api_key, str) and api_key:
                api_keys[provider_id] = api_key
        return api_keys

    def ai_default_provider(self) -> str | None:
        provider_id = self.graph_settings_with_secrets()["settings"].get(AI_DEFAULT_PROVIDER_KEY)
        if provider_id == "graphview-local" or provider_id in AI_PROVIDER_IDS:
            return str(provider_id)
        return None

    def upsert_ai_provider_api_key(self, provider_id: str, api_key: str, *, make_default: bool = True) -> dict:
        if provider_id not in AI_PROVIDER_IDS:
            raise ValueError(f"Provider {provider_id} does not accept user API keys")
        cleaned_key = api_key.strip()
        if not cleaned_key:
            raise ValueError("API key is required")
        timestamp = now()
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            settings_doc = load_json(json_value(row, "settings_json"), {})
            credentials = dict(settings_doc.get(AI_PROVIDER_CREDENTIALS_KEY) or {})
            credentials[provider_id] = {
                "encrypted_api_key": self._encrypt_json({"api_key": cleaned_key}),
                "updated_at": timestamp.isoformat(),
            }
            settings_doc[AI_PROVIDER_CREDENTIALS_KEY] = credentials
            if make_default:
                settings_doc[AI_DEFAULT_PROVIDER_KEY] = provider_id
            conn.execute(
                update(db.graph_settings)
                .where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                .values(settings_json=dump_json(settings_doc), updated_at=timestamp)
            )
        return self.graph_settings()

    def delete_ai_provider_api_key(self, provider_id: str) -> dict:
        if provider_id not in AI_PROVIDER_IDS:
            raise ValueError(f"Provider {provider_id} does not accept user API keys")
        timestamp = now()
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            settings_doc = load_json(json_value(row, "settings_json"), {})
            credentials = dict(settings_doc.get(AI_PROVIDER_CREDENTIALS_KEY) or {})
            credentials.pop(provider_id, None)
            if credentials:
                settings_doc[AI_PROVIDER_CREDENTIALS_KEY] = credentials
            else:
                settings_doc.pop(AI_PROVIDER_CREDENTIALS_KEY, None)
            if settings_doc.get(AI_DEFAULT_PROVIDER_KEY) == provider_id:
                settings_doc[AI_DEFAULT_PROVIDER_KEY] = "graphview-local"
            conn.execute(
                update(db.graph_settings)
                .where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                .values(settings_json=dump_json(settings_doc), updated_at=timestamp)
            )
        return self.graph_settings()

    def create_planning_session(self, payload: PlanningSessionCreate, actor_id: str) -> dict:
        spec = self._graph_view_spec(payload.graph_id)
        timestamp = now()
        session = {
            "id": new_id("plan"),
            "project_id": spec.project_id,
            "graph_id": payload.graph_id,
            "lens": normalize_graph_lens(payload.lens),
            "title": payload.title,
            "goal": payload.goal,
            "status": "active",
            "provider": payload.provider,
            "model": payload.model,
            "created_by": actor_id,
            "metadata_json": dump_json(payload.metadata),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.planning_sessions).values(**session))
        return self.get_planning_session(session["id"]) or self._planning_session_from_row(session)

    def list_planning_sessions(self, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            sessions = [
                self._planning_session_from_row(row)
                for row in conn.execute(
                    select(db.planning_sessions)
                    .where(db.planning_sessions.c.project_id == spec.project_id)
                    .order_by(db.planning_sessions.c.updated_at.desc(), db.planning_sessions.c.id.desc())
                ).mappings()
            ]
        return [self._planning_session_with_children(session) for session in sessions]

    def get_planning_session(self, session_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.planning_sessions).where(db.planning_sessions.c.id == session_id)
            ).mappings().first()
            if row is None:
                return None
            session = self._planning_session_from_row(row)
        return self._planning_session_with_children(session)

    def add_planning_message(
        self,
        session_id: str,
        payload: PlanningMessageCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        assistant_content: str,
        assistant_metadata: dict,
        agent_run_output: dict,
    ) -> dict:
        session = self.get_planning_session(session_id)
        if session is None:
            raise KeyError(session_id)
        timestamp = now()
        trace_id = new_id("trace")
        agent_run = {
            "id": new_id("agent"),
            "project_id": session["project_id"],
            "planning_session_id": session_id,
            "kind": "planning",
            "status": "completed",
            "provider": provider,
            "model": model,
            "input_json": dump_json({"message": payload.content, "session_id": session_id}),
            "output_json": dump_json(agent_run_output),
            "trace_id": trace_id,
            "created_by": actor_id,
            "started_at": timestamp,
            "finished_at": timestamp,
            "error": None,
        }
        user_message = {
            "id": new_id("msg"),
            "project_id": session["project_id"],
            "session_id": session_id,
            "agent_run_id": agent_run["id"],
            "role": "user",
            "content": payload.content,
            "provider": provider,
            "model": model,
            "metadata_json": dump_json({}),
            "created_at": timestamp,
        }
        assistant_message = {
            "id": new_id("msg"),
            "project_id": session["project_id"],
            "session_id": session_id,
            "agent_run_id": agent_run["id"],
            "role": "assistant",
            "content": assistant_content,
            "provider": provider,
            "model": model,
            "metadata_json": dump_json(assistant_metadata),
            "created_at": timestamp,
        }
        step = self._agent_step_row(
            project_id=session["project_id"],
            agent_run_id=agent_run["id"],
            name="agent.plan",
            status="completed",
            input_summary=payload.content[:500],
            output_summary=assistant_content[:500],
            trace_id=trace_id,
            timestamp=timestamp,
        )
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_runs).values(**agent_run))
            conn.execute(insert(db.agent_steps).values(**step))
            conn.execute(insert(db.planning_messages), [user_message, assistant_message])
            conn.execute(
                update(db.planning_sessions)
                .where(db.planning_sessions.c.id == session_id)
                .values(updated_at=timestamp, provider=provider, model=model)
            )
            self._record_activity_event(
                conn,
                project_id=session["project_id"],
                event_type="agent.run.completed",
                actor_id=actor_id,
                summary="Completed planning agent run.",
                object_refs=[
                    self._activity_ref("agent_run", agent_run["id"], "planning"),
                    self._activity_ref("planning_session", session_id, session["title"]),
                ],
                payload={"agent_run_id": agent_run["id"], "kind": "planning", "status": "completed"},
                lenses=[] if normalize_graph_lens(session["lens"]) == "all" else [normalize_graph_lens(session["lens"])],
                timestamp=timestamp,
            )
        return self.get_planning_session(session_id) or session

    def upsert_graph_build_spec(self, session_id: str, payload: GraphBuildSpecCreate) -> dict:
        session = self.get_planning_session(session_id)
        if session is None:
            raise KeyError(session_id)
        timestamp = now()
        with self.engine.begin() as conn:
            current = conn.execute(
                select(db.graph_build_specs)
                .where(db.graph_build_specs.c.session_id == session_id)
                .order_by(db.graph_build_specs.c.version.desc())
            ).mappings().first()
            version = 1 if current is None else current["version"] + 1
            spec = {
                "id": new_id("buildspec"),
                "project_id": session["project_id"],
                "session_id": session_id,
                "version": version,
                "title": payload.title or session["title"],
                "objective": payload.objective or session["goal"],
                "status": payload.status,
                "spec_json": dump_json(payload.spec),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            conn.execute(insert(db.graph_build_specs).values(**spec))
            conn.execute(update(db.planning_sessions).where(db.planning_sessions.c.id == session_id).values(updated_at=timestamp))
        return self._graph_build_spec_from_row(spec)

    def create_agent_run(
        self,
        payload: AgentRunCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        output: dict | None = None,
        status: str = "completed",
        error: str | None = None,
    ) -> dict:
        project_id = DEFAULT_PROJECT_ID
        if payload.planning_session_id:
            session = self.get_planning_session(payload.planning_session_id)
            if session is None:
                raise KeyError(payload.planning_session_id)
            project_id = session["project_id"]
        elif isinstance(payload.input.get("graph_id"), str) and payload.input["graph_id"]:
            project_id = self._graph_view_spec(payload.input["graph_id"]).project_id
        timestamp = now()
        trace_id = new_id("trace")
        run_input = dict(payload.input)
        run_input.setdefault("_agent_mode", payload.mode)
        if payload.focus_target is not None:
            run_input.setdefault("_focus_target", payload.focus_target.model_dump(exclude_none=True))
        run = {
            "id": new_id("agent"),
            "project_id": project_id,
            "planning_session_id": payload.planning_session_id,
            "kind": payload.kind,
            "status": status,
            "provider": provider,
            "model": model,
            "input_json": dump_json(run_input),
            "output_json": dump_json(output or {}),
            "trace_id": trace_id,
            "created_by": actor_id,
            "started_at": timestamp,
            "finished_at": timestamp if status in {"completed", "failed", "waiting_for_review"} else None,
            "error": error,
        }
        step = self._agent_step_row(
            project_id=project_id,
            agent_run_id=run["id"],
            name=f"agent.{payload.kind}",
            status=status,
            input_summary=dump_json(run_input)[:500],
            output_summary=dump_json(output or {})[:500],
            error=error,
            trace_id=trace_id,
            timestamp=timestamp,
        )
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_runs).values(**run))
            conn.execute(insert(db.agent_steps).values(**step))
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type=f"agent.run.{status}",
                actor_id=actor_id,
                summary=f"{status.replace('_', ' ').title()} {payload.kind.replace('_', ' ')} agent run.",
                object_refs=[
                    self._activity_ref("agent_run", run["id"], payload.kind),
                    *self._activity_refs_from_agent_payload(run_input, output or {}),
                ],
                payload={
                    "agent_run_id": run["id"],
                    "kind": payload.kind,
                    "status": status,
                    "trace_id": trace_id,
                },
                lenses=self._activity_lenses_from_agent_payload(run_input, output or {}),
                timestamp=timestamp,
            )
        return self.get_agent_run(run["id"]) or self._agent_run_from_row(run)

    def get_agent_run(self, agent_run_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(db.agent_runs).where(db.agent_runs.c.id == agent_run_id)).mappings().first()
            if row is None:
                return None
            run = self._agent_run_from_row(row)
            run["steps"] = [
                self._agent_step_from_row(step)
                for step in conn.execute(
                    select(db.agent_steps)
                    .where(db.agent_steps.c.agent_run_id == agent_run_id)
                    .order_by(db.agent_steps.c.started_at, db.agent_steps.c.id)
                ).mappings()
            ]
            run["action_proposals"] = [
                self._agent_action_proposal_from_row(action)
                for action in conn.execute(
                    select(db.agent_action_proposals)
                    .where(db.agent_action_proposals.c.agent_run_id == agent_run_id)
                    .order_by(db.agent_action_proposals.c.created_at, db.agent_action_proposals.c.id)
                ).mappings()
            ]
            return run

    def graph_query_context(
        self,
        payload: GraphQueryCreate,
        *,
        actor_id: str | None = None,
    ) -> dict:
        spec = self._graph_view_spec(payload.graph_id)
        from graphview_api.repository_retrieval import RetrievalMatcher

        retrieval = RetrievalMatcher(self)
        with self.engine.begin() as conn:
            project = dict(
                conn.execute(
                    select(db.graph_projects).where(db.graph_projects.c.id == spec.project_id)
                ).mappings().one()
            )
            if self.engine.dialect.name == "postgresql":
                matches = retrieval.postgres(conn, spec=spec, payload=payload)
            else:
                matches = retrieval.portable(conn, spec=spec, payload=payload)

            node_ids = [match["id"] for match in matches if match["kind"] == "node"]
            source_ids = {match["source_id"] for match in matches if match.get("source_id")}
            chunk_ids = [match["id"] for match in matches if match["kind"] == "chunk"]
            if payload.node_id and payload.node_id not in node_ids:
                node_ids.insert(0, payload.node_id)
            if payload.source_id:
                source_ids.add(payload.source_id)
            if payload.source_chunk_id and payload.source_chunk_id not in chunk_ids:
                chunk_ids.insert(0, payload.source_chunk_id)

            node_stmt = select(db.content_nodes).where(db.content_nodes.c.project_id == spec.project_id)
            node_stmt = node_stmt.where(db.content_nodes.c.id.in_(node_ids[:12])) if node_ids else node_stmt.where(False)
            selected_nodes = [self._node_from_row(row) for row in conn.execute(node_stmt).mappings()]
            selected_nodes.sort(key=lambda item: node_ids.index(item["id"]) if item["id"] in node_ids else len(node_ids))
            if normalize_graph_lens(payload.lens) != "all":
                selected_nodes = [node for node in selected_nodes if self._node_matches_lens(node, normalize_graph_lens(payload.lens))]
            for node in selected_nodes:
                source_ids.update(
                    item["sourceId"]
                    for item in node.get("provenance", [])
                    if item.get("sourceId")
                )

            allowed_source_ids = set(spec.source_ids) if spec.source_ids else None
            if allowed_source_ids is not None:
                source_ids.intersection_update(allowed_source_ids)
            source_stmt = select(db.sources).where(db.sources.c.project_id == spec.project_id)
            source_stmt = source_stmt.where(db.sources.c.id.in_(source_ids)) if source_ids else source_stmt.where(False)
            sources = [self._source_from_row(row) for row in conn.execute(source_stmt).mappings()]
            sources.sort(key=lambda item: next((index for index, match in enumerate(matches) if match.get("source_id") == item["id"]), len(matches)))

            chunk_stmt = select(db.source_chunks).where(db.source_chunks.c.project_id == spec.project_id)
            chunk_stmt = chunk_stmt.where(db.source_chunks.c.id.in_(chunk_ids[:12])) if chunk_ids else chunk_stmt.where(False)
            chunks = [self._source_chunk_from_row(row) for row in conn.execute(chunk_stmt).mappings()]
            chunks.sort(key=lambda item: chunk_ids.index(item["id"]) if item["id"] in chunk_ids else len(chunk_ids))
            chunk_source_ids = {chunk["source_id"] for chunk in chunks}
            for source in sources:
                if source["id"] in chunk_source_ids or len(chunks) >= 8:
                    continue
                fallback_chunks = conn.execute(
                    select(db.source_chunks)
                    .where(
                        and_(
                            db.source_chunks.c.project_id == spec.project_id,
                            db.source_chunks.c.source_id == source["id"],
                        )
                    )
                    .order_by(db.source_chunks.c.ordinal, db.source_chunks.c.id)
                    .limit(2)
                ).mappings()
                chunks.extend(self._source_chunk_from_row(row) for row in fallback_chunks)

            selected_node_ids = [node["id"] for node in selected_nodes]
            edge_stmt = select(db.semantic_edges).where(db.semantic_edges.c.project_id == spec.project_id)
            if selected_node_ids:
                edge_stmt = edge_stmt.where(
                    or_(
                        db.semantic_edges.c.source_node_id.in_(selected_node_ids),
                        db.semantic_edges.c.target_node_id.in_(selected_node_ids),
                    )
                ).limit(8)
                edges = [self._edge_from_row(row) for row in conn.execute(edge_stmt).mappings()]
            else:
                edges = []

            timestamp = now()
            conn.execute(
                insert(db.audit_events).values(
                    id=new_id("audit"),
                    project_id=spec.project_id,
                    actor_id=actor_id,
                    action="ai.retrieval",
                    resource_type="graph",
                    resource_id=spec.id,
                    outcome="succeeded",
                    summary=f"Retrieved {len(matches)} bounded graph anchors for cited AI context.",
                    metadata_json=dump_json(
                        {
                            "query_sha256": hashlib.sha256(payload.question.encode("utf-8")).hexdigest(),
                            "lens": payload.lens,
                            "node_id": payload.node_id,
                            "source_id": payload.source_id,
                            "source_chunk_id": payload.source_chunk_id,
                            "match_count": len(matches),
                            "citation_candidate_count": len(selected_nodes) + len(chunks),
                        }
                    ),
                    trace_id=new_id("trace"),
                    occurred_at=timestamp,
                )
            )

        chunks = chunks[:8]
        sources = sources[:6]
        selected_nodes = selected_nodes[:6]
        citations = self._agent_citations_from_context(nodes=selected_nodes, sources=sources, chunks=chunks)
        return {
            "project": project,
            "question": payload.question,
            "nodes": selected_nodes,
            "edges": edges,
            "sources": sources,
            "chunks": chunks,
            "citations": citations,
        }

    def create_research_task(
        self,
        payload: GraphResearchCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        agent_run_id: str | None,
        result: dict,
    ) -> dict:
        spec = self._graph_view_spec(payload.graph_id)
        timestamp = now()
        idempotency_key = hashlib.sha256(
            f"{spec.project_id}:{payload.query}:{payload.lens}:{provider}:{model}:{payload.source_policy}".encode("utf-8")
        ).hexdigest()[:40]
        existing = self.get_research_task_by_key(idempotency_key)
        if existing:
            return existing
        task = {
            "id": new_id("research"),
            "project_id": spec.project_id,
            "agent_run_id": agent_run_id,
            "planning_session_id": None,
            "query": payload.query,
            "status": "proposal_ready",
            "provider": provider,
            "model": model,
            "source_policy": payload.source_policy,
            "idempotency_key": idempotency_key,
            "result_json": dump_json(result),
            "created_by": actor_id,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.research_tasks).values(**task))
            self._record_activity_event(
                conn,
                project_id=spec.project_id,
                event_type="research.proposal_ready",
                actor_id=actor_id,
                summary=f"Prepared research proposals for {payload.query}.",
                object_refs=[
                    self._activity_ref("research_task", task["id"], payload.query),
                    *([self._activity_ref("agent_run", agent_run_id, "research")] if agent_run_id else []),
                    *self._activity_refs_from_agent_payload({"lens": payload.lens}, result),
                ],
                payload={
                    "research_task_id": task["id"],
                    "agent_run_id": agent_run_id,
                    "query": payload.query,
                    "source_policy": payload.source_policy,
                    "proposal_ids": result.get("proposal_ids", []),
                    "source_id": result.get("source_id"),
                },
                lenses=[] if normalize_graph_lens(payload.lens) == "all" else [normalize_graph_lens(payload.lens)],
                timestamp=timestamp,
            )
        return self._research_task_from_row(task)

    def get_research_task_by_key(self, idempotency_key: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.research_tasks).where(db.research_tasks.c.idempotency_key == idempotency_key)
            ).mappings().first()
            return self._research_task_from_row(row) if row else None

    def create_agent_action_proposal(
        self,
        *,
        agent_run_id: str,
        action_type: str,
        title: str,
        summary: str,
        payload: dict,
        citations: list[dict] | None = None,
        confidence: float | None = None,
    ) -> dict:
        run = self.get_agent_run(agent_run_id)
        if run is None:
            raise KeyError(agent_run_id)
        timestamp = now()
        action = {
            "id": new_id("action"),
            "project_id": run["project_id"],
            "agent_run_id": agent_run_id,
            "action_type": action_type,
            "status": "pending_review",
            "title": title,
            "summary": summary,
            "payload_json": dump_json(payload),
            "citations_json": dump_json(citations or []),
            "confidence": confidence,
            "created_at": timestamp,
            "updated_at": timestamp,
            "applied_at": None,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_action_proposals).values(**action))
            conn.execute(
                update(db.agent_runs)
                .where(db.agent_runs.c.id == agent_run_id)
                .values(status="waiting_for_review", finished_at=timestamp)
            )
            self._record_activity_event(
                conn,
                project_id=run["project_id"],
                event_type="agent.action_proposed",
                actor_id=run.get("created_by"),
                summary=f"Proposed agent action {title}.",
                object_refs=[
                    self._activity_ref("agent_action_proposal", action["id"], title),
                    self._activity_ref("agent_run", agent_run_id, run["kind"]),
                    *self._activity_refs_from_agent_payload(run.get("input", {}), payload),
                ],
                payload={
                    "action_proposal_id": action["id"],
                    "agent_run_id": agent_run_id,
                    "action_type": action_type,
                    "status": "pending_review",
                },
                lenses=self._activity_lenses_from_agent_payload(run.get("input", {}), payload),
                timestamp=timestamp,
            )
        return self._agent_action_proposal_from_row(action)

    def approve_agent_action(self, payload: AgentActionApprovalCreate, reviewer_id: str) -> dict:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_action_proposals).where(db.agent_action_proposals.c.id == payload.action_proposal_id)
            ).mappings().first()
            if row is None:
                raise KeyError(payload.action_proposal_id)
            action = self._agent_action_proposal_from_row(row)
            if action["status"] != "pending_review":
                return action
            timestamp = now()
            if payload.decision == "reject":
                conn.execute(
                    update(db.agent_action_proposals)
                    .where(db.agent_action_proposals.c.id == payload.action_proposal_id)
                    .values(status="rejected", updated_at=timestamp)
                )
                self._record_activity_event(
                    conn,
                    project_id=action["project_id"],
                    event_type="agent.action_rejected",
                    actor_id=reviewer_id,
                    summary=f"Rejected agent action {action['title']}.",
                    object_refs=[
                        self._activity_ref("agent_action_proposal", action["id"], action["title"]),
                        self._activity_ref("agent_run", action["agent_run_id"], action["action_type"]),
                    ],
                    payload={
                        "action_proposal_id": action["id"],
                        "agent_run_id": action["agent_run_id"],
                        "decision": payload.decision,
                        "rationale": payload.rationale,
                    },
                    lenses=[],
                    timestamp=timestamp,
                )
                return self.get_agent_action(payload.action_proposal_id) or action

        action_payload = action["payload"]
        if action["action_type"] == "review_decision":
            self.review(
                ReviewDecisionCreate(
                    proposal_id=action_payload["proposal_id"],
                    decision=action_payload.get("decision", "accept"),
                    rationale=payload.rationale or action_payload.get("rationale") or "Approved by AI action review.",
                ),
                reviewer_id,
            )
        with self.engine.begin() as conn:
            conn.execute(
                update(db.agent_action_proposals)
                .where(db.agent_action_proposals.c.id == payload.action_proposal_id)
                .values(status="applied", updated_at=timestamp, applied_at=timestamp)
            )
            self._record_activity_event(
                conn,
                project_id=action["project_id"],
                event_type="agent.action_applied",
                actor_id=reviewer_id,
                summary=f"Applied agent action {action['title']}.",
                object_refs=[
                    self._activity_ref("agent_action_proposal", action["id"], action["title"]),
                    self._activity_ref("agent_run", action["agent_run_id"], action["action_type"]),
                    *self._activity_refs_from_agent_payload({}, action.get("payload", {})),
                ],
                payload={
                    "action_proposal_id": action["id"],
                    "agent_run_id": action["agent_run_id"],
                    "decision": payload.decision,
                    "rationale": payload.rationale,
                },
                lenses=self._activity_lenses_from_agent_payload({}, action.get("payload", {})),
                timestamp=timestamp,
            )
        return self.get_agent_action(payload.action_proposal_id) or action

    def get_agent_action(self, action_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_action_proposals).where(db.agent_action_proposals.c.id == action_id)
            ).mappings().first()
            return self._agent_action_proposal_from_row(row) if row else None

    def list_source_chunks(self, source_id: str | None = None, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        stmt = select(db.source_chunks).where(db.source_chunks.c.project_id == spec.project_id)
        if spec.source_ids:
            stmt = stmt.where(db.source_chunks.c.source_id.in_(spec.source_ids))
        if source_id:
            stmt = stmt.where(db.source_chunks.c.source_id == source_id)
        stmt = stmt.order_by(db.source_chunks.c.source_id, db.source_chunks.c.ordinal, db.source_chunks.c.id)
        with self.engine.begin() as conn:
            return [self._source_chunk_from_row(row) for row in conn.execute(stmt).mappings()]

    def list_ingestion_runs(self) -> list[dict]:
        with self.engine.begin() as conn:
            return [
                normalize_json_row(row)
                for row in conn.execute(
                    select(db.ingestion_runs)
                    .where(db.ingestion_runs.c.project_id == DEFAULT_PROJECT_ID)
                    .order_by(db.ingestion_runs.c.started_at.desc())
                ).mappings()
            ]

    def create_ingestion_result(
        self,
        *,
        source_payload: SourceCreate,
        generated_proposals: list[dict],
        embedding_model: str,
        embedding_vector: list[float],
        actor_id: str,
        source_text: str | None = None,
        graph_id: str | None = None,
    ) -> dict:
        spec = self._graph_view_spec(graph_id)
        timestamp = now()
        source = {
            "id": new_id("src"),
            "project_id": spec.project_id,
            **self._source_values_from_payload(source_payload),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        ingestion_run = {
            "id": new_id("run"),
            "project_id": spec.project_id,
            "source_id": source["id"],
            "status": "proposal_ready",
            "stage": "propose",
            "trace_id": new_id("trace"),
            "started_at": timestamp,
            "finished_at": timestamp,
            "error_code": None,
        }
        generated_with_ids = self._assign_generated_graph_ids(generated_proposals)
        proposals: list[dict] = []
        embeddings: list[dict] = []
        for generated in generated_with_ids:
            provenance = [
                {
                    "sourceId": source["id"],
                    "sourceUri": source.get("uri"),
                    "locator": generated.get("locator"),
                    "extractedBy": "worker",
                    "actorId": actor_id,
                    "ingestionRunId": ingestion_run["id"],
                    "observedAt": timestamp.isoformat(),
                    "traceId": ingestion_run["trace_id"],
                }
            ]
            proposal = {
                "id": new_id("proposal"),
                "project_id": spec.project_id,
                "ingestion_run_id": ingestion_run["id"],
                "kind": generated.get("kind", "content_node"),
                "status": "pending_review",
                "proposed_value_json": dump_json(generated["proposed_value"]),
                "confidence": generated.get("confidence"),
                "provenance_json": dump_json(provenance),
                "created_at": timestamp,
            }
            embedding = {
                "id": new_id("embedding"),
                "project_id": spec.project_id,
                "proposal_id": proposal["id"],
                "content_node_id": None,
                "embedding_model": embedding_model,
                "vector_json": dump_json(embedding_vector),
                "created_at": timestamp,
            }
            proposals.append(proposal)
            embeddings.append(embedding)
        with self.engine.begin() as conn:
            conn.execute(insert(db.sources).values(**source))
            conn.execute(insert(db.ingestion_runs).values(**ingestion_run))
            chunk_rows = self._source_chunk_rows(
                project_id=spec.project_id,
                source_id=source["id"],
                source_title=source["title"],
                source_text=source_text,
                timestamp=timestamp,
            )
            if chunk_rows:
                conn.execute(insert(db.source_chunks), chunk_rows)
            if proposals:
                conn.execute(insert(db.extraction_proposals), proposals)
                conn.execute(insert(db.content_embeddings), embeddings)
            proposal_outputs = [self._proposal_from_row(proposal) for proposal in proposals]
            activity_lenses = self._activity_lenses_for_proposals(proposal_outputs)
            self._record_activity_event(
                conn,
                project_id=spec.project_id,
                event_type="source.created",
                actor_id=actor_id,
                summary=f"Added source {source['title']}.",
                object_refs=[self._activity_ref("source", source["id"], source["title"])],
                payload={"source_id": source["id"], "kind": source["kind"]},
                lenses=activity_lenses,
                timestamp=timestamp,
            )
            self._record_activity_event(
                conn,
                project_id=spec.project_id,
                event_type="ingestion.proposal_ready",
                actor_id=actor_id,
                summary=f"Ingested {source['title']} and generated {len(proposals)} proposals.",
                object_refs=[
                    self._activity_ref("source", source["id"], source["title"]),
                    self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run["stage"]),
                ],
                payload={
                    "source_id": source["id"],
                    "ingestion_run_id": ingestion_run["id"],
                    "proposal_count": len(proposals),
                    "chunk_count": len(chunk_rows),
                },
                lenses=activity_lenses,
                timestamp=timestamp,
            )
            for proposal in proposal_outputs:
                self._record_proposal_created_activity(
                    conn,
                    proposal=proposal,
                    source=self._source_from_row(source),
                    ingestion_run=ingestion_run,
                    actor_id=actor_id,
                    timestamp=timestamp,
                )
        return {
            "source": self._source_from_row(source),
            "ingestion_run": ingestion_run,
            "proposals": proposal_outputs,
            "embeddings": [self._embedding_from_row(embedding) for embedding in embeddings],
        }

    def _source_chunk_rows(
        self,
        *,
        project_id: str,
        source_id: str,
        source_title: str,
        source_text: str | None,
        timestamp: datetime,
    ) -> list[dict]:
        if not source_text or not source_text.strip():
            return []
        blocks = [block.strip() for block in source_text.strip().split("\n\n") if block.strip()]
        if len(blocks) == 1:
            blocks = [line.strip() for line in source_text.strip().splitlines() if line.strip()] or blocks
        rows = []
        active_heading = source_title
        for ordinal, block in enumerate(blocks):
            block_type = "heading" if block.startswith("#") else "paragraph"
            text_value = block.lstrip("# ").strip() if block_type == "heading" else block
            if block_type == "heading":
                active_heading = text_value
            rows.append(
                {
                    "id": new_id("chunk"),
                    "project_id": project_id,
                    "source_id": source_id,
                    "parent_chunk_id": None,
                    "heading_path_json": dump_json([active_heading]),
                    "block_type": block_type,
                    "ordinal": ordinal,
                    "text": text_value,
                    "links_json": dump_json(self._links_from_text(text_value)),
                    "mentions_json": dump_json(self._mentions_from_text(text_value)),
                    "checksum": hashlib.sha256(f"{source_id}:{ordinal}:{text_value}".encode("utf-8")).hexdigest(),
                    "locator": f"{source_id}#block-{ordinal + 1}",
                    "created_at": timestamp,
                }
            )
        return rows

    def _links_from_text(self, text_value: str) -> list[str]:
        return [word.rstrip(".,)") for word in text_value.split() if word.startswith(("http://", "https://"))]

    def _mentions_from_text(self, text_value: str) -> list[str]:
        return sorted({match.strip("@.,:;()[]") for match in text_value.split() if match.startswith("@")})

    def create_connector_sync_result(
        self,
        *,
        target_id: str,
        documents: list[NormalizedSourceDocument],
        generated_proposals_by_remote_id: dict[str, list[dict]],
        embedding_model: str,
        embedding_vectors_by_remote_id: dict[str, list[float]],
        actor_id: str,
        auto_commit_threshold: float | None = None,
        full_snapshot: bool = True,
        tombstone_remote_ids: set[str] | None = None,
    ) -> dict:
        timestamp = now()
        threshold = self.auto_commit_threshold if auto_commit_threshold is None else auto_commit_threshold
        sync_run = {
            "id": new_id("sync"),
            "project_id": "",
            "target_id": target_id,
            "status": "running",
            "stage": "connector.fetch",
            "source_count": 0,
            "chunk_count": 0,
            "proposal_count": 0,
            "auto_committed_count": 0,
            "error": None,
            "trace_id": new_id("trace"),
            "started_at": timestamp,
            "finished_at": None,
        }
        inserted_proposals: list[dict] = []
        inserted_embeddings: list[dict] = []
        source_outputs: list[dict] = []
        chunk_count = 0
        deleted_count = 0
        tombstone_remote_ids = tombstone_remote_ids or set()

        with self.engine.begin() as conn:
            target_row = conn.execute(
                select(db.connector_targets).where(db.connector_targets.c.id == target_id)
            ).mappings().first()
            if target_row is None:
                raise KeyError(target_id)
            project_id = target_row["project_id"]
            sync_run["project_id"] = project_id
            conn.execute(insert(db.connector_sync_runs).values(**sync_run))

            observed_remote_ids = {document.remote_id for document in documents}
            stale_timestamp = timestamp
            for row in conn.execute(
                select(db.sources).where(
                    and_(
                        db.sources.c.project_id == project_id,
                        db.sources.c.connector_kind == target_row["connector_kind"],
                    )
                )
            ).mappings():
                source_metadata = load_json(json_value(row, "metadata_json"), {})
                should_stale = (
                    source_metadata.get("targetId") == target_id
                    and row["remote_id"]
                    and ((full_snapshot and row["remote_id"] not in observed_remote_ids) or row["remote_id"] in tombstone_remote_ids)
                )
                if should_stale:
                    conn.execute(
                        update(db.sources)
                        .where(db.sources.c.id == row["id"])
                        .values(stale_at=stale_timestamp, updated_at=timestamp)
                    )
                    deleted_count += 1

            for document in documents:
                source = self._upsert_connector_source(conn, document, timestamp, target_id=target_id)
                source_outputs.append(source)
                conn.execute(delete(db.source_chunks).where(db.source_chunks.c.source_id == source["id"]))
                chunk_id_by_key: dict[str, str] = {}
                chunk_rows = []
                for chunk in document.chunks:
                    chunk_id = stable_id("chunk", source["id"], chunk.stable_key)
                    chunk_id_by_key[chunk.stable_key] = chunk_id
                    chunk_rows.append(
                        {
                            "id": chunk_id,
                            "project_id": project_id,
                            "source_id": source["id"],
                            "parent_chunk_id": chunk_id_by_key.get(chunk.parent_stable_key or ""),
                            "heading_path_json": dump_json(chunk.heading_path),
                            "block_type": chunk.block_type,
                            "ordinal": chunk.ordinal,
                            "text": chunk.text,
                            "links_json": dump_json(chunk.links),
                            "mentions_json": dump_json(chunk.mentions),
                            "checksum": chunk.checksum,
                            "locator": chunk.locator,
                            "created_at": timestamp,
                        }
                    )
                    self._ensure_topics_for_heading_path(conn, chunk.heading_path, timestamp)
                if chunk_rows:
                    conn.execute(insert(db.source_chunks), chunk_rows)
                    chunk_count += len(chunk_rows)

                ingestion_run = {
                    "id": new_id("run"),
                    "project_id": project_id,
                    "source_id": source["id"],
                    "status": "proposal_ready",
                    "stage": "propose",
                    "trace_id": sync_run["trace_id"],
                    "started_at": timestamp,
                    "finished_at": timestamp,
                    "error_code": None,
                }
                conn.execute(insert(db.ingestion_runs).values(**ingestion_run))

                generated = self._assign_generated_graph_ids(generated_proposals_by_remote_id.get(document.remote_id, []))
                document_inserted_proposals: list[dict] = []
                for proposal_input in generated:
                    value = dict(proposal_input["proposed_value"])
                    if self._proposal_value_exists(conn, proposal_input.get("kind", "content_node"), value):
                        continue
                    provenance = [
                        {
                            "sourceId": source["id"],
                            "sourceUri": source.get("uri"),
                            "locator": proposal_input.get("locator"),
                            "extractedBy": "worker",
                            "actorId": actor_id,
                            "ingestionRunId": ingestion_run["id"],
                            "observedAt": timestamp.isoformat(),
                            "traceId": sync_run["trace_id"],
                            "connectorKind": document.connector_kind,
                            "remoteId": document.remote_id,
                        }
                    ]
                    proposal = {
                        "id": new_id("proposal"),
                        "project_id": project_id,
                        "ingestion_run_id": ingestion_run["id"],
                        "kind": proposal_input.get("kind", "content_node"),
                        "status": "pending_review",
                        "proposed_value_json": dump_json(value),
                        "confidence": proposal_input.get("confidence"),
                        "provenance_json": dump_json(provenance),
                        "created_at": timestamp,
                    }
                    embedding = {
                        "id": new_id("embedding"),
                        "project_id": project_id,
                        "proposal_id": proposal["id"],
                        "content_node_id": None,
                        "embedding_model": embedding_model,
                        "vector_json": dump_json(embedding_vectors_by_remote_id.get(document.remote_id, [])),
                        "created_at": timestamp,
                    }
                    conn.execute(insert(db.extraction_proposals).values(**proposal))
                    conn.execute(insert(db.content_embeddings).values(**embedding))
                    inserted_proposals.append(proposal)
                    document_inserted_proposals.append(proposal)
                    inserted_embeddings.append(embedding)

                proposal_outputs = [self._proposal_from_row(proposal) for proposal in document_inserted_proposals]
                activity_lenses = self._activity_lenses_for_proposals(proposal_outputs)
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="source.synced",
                    actor_id=actor_id,
                    summary=f"Synced source {source['title']}.",
                    object_refs=[
                        self._activity_ref("source", source["id"], source["title"]),
                        self._activity_ref("connector_target", target_id, target_row["title"]),
                    ],
                    payload={
                        "source_id": source["id"],
                        "target_id": target_id,
                        "remote_id": document.remote_id,
                        "connector_kind": document.connector_kind,
                    },
                    lenses=activity_lenses,
                    timestamp=timestamp,
                )
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="ingestion.proposal_ready",
                    actor_id=actor_id,
                    summary=f"Ingested {source['title']} and generated {len(document_inserted_proposals)} proposals.",
                    object_refs=[
                        self._activity_ref("source", source["id"], source["title"]),
                        self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run["stage"]),
                        self._activity_ref("connector_target", target_id, target_row["title"]),
                    ],
                    payload={
                        "source_id": source["id"],
                        "ingestion_run_id": ingestion_run["id"],
                        "proposal_count": len(document_inserted_proposals),
                    },
                    lenses=activity_lenses,
                    timestamp=timestamp,
                )
                for proposal in proposal_outputs:
                    self._record_proposal_created_activity(
                        conn,
                        proposal=proposal,
                        source=source,
                        ingestion_run=ingestion_run,
                        actor_id=actor_id,
                        timestamp=timestamp,
                    )

            auto_committed = self._auto_commit_inserted_proposals(conn, inserted_proposals, threshold)
            conn.execute(
                update(db.connector_sync_runs)
                .where(db.connector_sync_runs.c.id == sync_run["id"])
                .values(
                    status="completed",
                    stage="review.commit",
                    source_count=len(source_outputs),
                    chunk_count=chunk_count,
                    proposal_count=len(inserted_proposals),
                    auto_committed_count=auto_committed,
                    finished_at=now(),
                )
            )
            conn.execute(
                update(db.connector_targets)
                .where(db.connector_targets.c.id == target_id)
                .values(last_synced_at=timestamp, updated_at=timestamp)
            )
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type="connector.sync_completed",
                actor_id=actor_id,
                summary=f"Completed connector sync for {target_row['title']}.",
                object_refs=[
                    self._activity_ref("connector_sync_run", sync_run["id"], "completed"),
                    self._activity_ref("connector_target", target_id, target_row["title"]),
                ],
                payload={
                    "sync_run_id": sync_run["id"],
                    "target_id": target_id,
                    "source_count": len(source_outputs),
                    "chunk_count": chunk_count,
                    "proposal_count": len(inserted_proposals),
                    "auto_committed_count": auto_committed,
                },
                lenses=self._activity_lenses_for_proposals([self._proposal_from_row(proposal) for proposal in inserted_proposals]),
                timestamp=timestamp,
            )

        sync_run = self.get_connector_sync_run(sync_run["id"], project_id=project_id) or sync_run
        return {
            "sync_run": sync_run,
            "sources": source_outputs,
            "proposals": [self._proposal_from_row(proposal) for proposal in inserted_proposals],
            "embeddings": [self._embedding_from_row(embedding) for embedding in inserted_embeddings],
            "deleted_count": deleted_count,
        }

    def create_proposal(self, payload: ProposalCreate, actor_id: str) -> dict:
        source = self.get_source(payload.source_id)
        if source is None:
            raise KeyError(payload.source_id)

        timestamp = now()
        ingestion_run = {
            "id": new_id("run"),
            "project_id": source["project_id"],
            "source_id": payload.source_id,
            "status": "proposal_ready",
            "stage": "propose",
            "trace_id": new_id("trace"),
            "started_at": timestamp,
            "finished_at": timestamp,
            "error_code": None,
        }
        provenance = [
            {
                "sourceId": payload.source_id,
                "sourceUri": source.get("uri"),
                "locator": payload.locator,
                "extractedBy": "human",
                "actorId": actor_id,
                "ingestionRunId": ingestion_run["id"],
                "observedAt": timestamp.isoformat(),
                "traceId": ingestion_run["trace_id"],
            }
        ]
        proposal = {
            "id": new_id("proposal"),
            "project_id": source["project_id"],
            "ingestion_run_id": ingestion_run["id"],
            "kind": payload.kind,
            "status": "pending_review",
            "proposed_value_json": dump_json(payload.proposed_value),
            "confidence": payload.confidence,
            "provenance_json": dump_json(provenance),
            "created_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.ingestion_runs).values(**ingestion_run))
            conn.execute(insert(db.extraction_proposals).values(**proposal))
            proposal_output = self._proposal_from_row(proposal)
            self._record_activity_event(
                conn,
                project_id=source["project_id"],
                event_type="ingestion.proposal_ready",
                actor_id=actor_id,
                summary=f"Created a manual proposal run for {source['title']}.",
                object_refs=[
                    self._activity_ref("source", source["id"], source["title"]),
                    self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run["stage"]),
                ],
                payload={
                    "source_id": source["id"],
                    "ingestion_run_id": ingestion_run["id"],
                    "proposal_count": 1,
                },
                lenses=self._activity_lenses_for_proposals([proposal_output]),
                timestamp=timestamp,
            )
            self._record_proposal_created_activity(
                conn,
                proposal=proposal_output,
                source=source,
                ingestion_run=ingestion_run,
                actor_id=actor_id,
                timestamp=timestamp,
            )
        return proposal_output

    def list_proposals(self, graph_id: str | None = None, lens: str | None = None) -> list[dict]:
        normalized_lens = normalize_graph_lens(lens)
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            proposals = [
                self._proposal_from_row(row)
                for row in conn.execute(
                    select(db.extraction_proposals)
                    .where(db.extraction_proposals.c.project_id == spec.project_id)
                    .order_by(db.extraction_proposals.c.created_at.desc())
                ).mappings()
            ]
            if not spec.source_ids:
                return [proposal for proposal in proposals if self._proposal_matches_lens(proposal, normalized_lens)]
            run_ids = {
                row["id"]
                for row in conn.execute(
                    select(db.ingestion_runs.c.id).where(
                        and_(
                            db.ingestion_runs.c.project_id == spec.project_id,
                            db.ingestion_runs.c.source_id.in_(spec.source_ids),
                        )
                    )
                ).mappings()
            }
        return [
            proposal
            for proposal in proposals
            if proposal["ingestion_run_id"] in run_ids and self._proposal_matches_lens(proposal, normalized_lens)
        ]

    def review_queue(self, *, limit: int = 25, graph_id: str | None = None, lens: str | None = None) -> dict:
        normalized_limit = min(100, max(1, limit))
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            proposals = [
                proposal for proposal in self.list_proposals(graph_id=graph_id, lens=lens)
                if proposal["status"] == "pending_review"
            ]
            runs_by_id = {
                row["id"]: normalize_json_row(row)
                for row in conn.execute(
                    select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                ).mappings()
            }
            sources_by_id = {
                row["id"]: self._source_from_row(row)
                for row in conn.execute(select(db.sources).where(db.sources.c.project_id == spec.project_id)).mappings()
            }
        _, nodes, _ = self.graph(graph_id, lens)
        reviewed_node_ids = {node["id"] for node in nodes}

        items: list[dict] = []
        for proposal in proposals:
            source = None
            if run := runs_by_id.get(proposal["ingestion_run_id"]):
                source = sources_by_id.get(run["source_id"])
            items.append(self._review_queue_item(proposal, source, reviewed_node_ids))

        items.sort(
            key=lambda item: (
                -item["priority_score"],
                item["proposal"]["created_at"],
                item["proposal"]["id"],
            )
        )
        return {
            "generated_at": now(),
            "pending_count": len(items),
            "ready_count": sum(1 for item in items if item["ready_to_commit"]),
            "blocked_count": sum(1 for item in items if item["blocked"]),
            "items": items[:normalized_limit],
        }

    def review_dashboard(self, graph_id: str | None = None, lens: str | None = None) -> dict:
        project, _, _ = self.graph(graph_id, lens)
        proposals = self.list_proposals(graph_id=graph_id, lens=lens)
        proposal_ids = {proposal["id"] for proposal in proposals}
        decisions = [
            decision
            for decision in self.list_review_decisions(graph_id=graph_id)
            if decision["proposal_id"] in proposal_ids
        ]

        queue = self.review_queue(limit=1, graph_id=graph_id, lens=lens)
        pending_proposals = [proposal for proposal in proposals if proposal["status"] == "pending_review"]
        oldest_pending = min(
            pending_proposals,
            key=lambda proposal: (proposal["created_at"], proposal["id"]),
            default=None,
        )
        accepted_count = sum(1 for decision in decisions if decision["decision"] == "accept")
        rejected_count = sum(1 for decision in decisions if decision["decision"] == "reject")
        edited_count = sum(1 for decision in decisions if decision["decision"] == "edit")
        deferred_count = sum(1 for decision in decisions if decision["decision"] == "defer")
        review_decision_count = len(decisions)
        committed_count = accepted_count + edited_count

        return {
            "project_id": project["id"],
            "generated_at": now(),
            "proposal_count": len(proposals),
            "pending_count": queue["pending_count"],
            "ready_count": queue["ready_count"],
            "blocked_count": queue["blocked_count"],
            "review_decision_count": review_decision_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "edited_count": edited_count,
            "deferred_count": deferred_count,
            "acceptance_rate": 0.0 if review_decision_count == 0 else round((accepted_count / review_decision_count) * 100, 2),
            "commit_rate": 0.0 if review_decision_count == 0 else round((committed_count / review_decision_count) * 100, 2),
            "proposal_kind_counts": self._count_by(proposals, "kind"),
            "pending_kind_counts": self._count_by(pending_proposals, "kind"),
            "decision_counts": self._count_by(decisions, "decision"),
            "reviewer_counts": self._count_by(decisions, "reviewer_id"),
            "oldest_pending_proposal_id": oldest_pending["id"] if oldest_pending else None,
            "oldest_pending_created_at": oldest_pending["created_at"] if oldest_pending else None,
        }

    def review_activity(self, *, limit: int = 10, graph_id: str | None = None, lens: str | None = None) -> dict:
        normalized_limit = min(100, max(1, limit))
        spec = self._graph_view_spec(graph_id)
        scoped_proposals = self.list_proposals(graph_id=graph_id, lens=lens)
        scoped_proposal_ids = {proposal["id"] for proposal in scoped_proposals}
        with self.engine.begin() as conn:
            decisions = [
                self._decision_from_row(row)
                for row in conn.execute(
                    select(db.review_decisions)
                    .where(db.review_decisions.c.project_id == spec.project_id)
                    .order_by(db.review_decisions.c.decided_at.desc(), db.review_decisions.c.id.desc())
                ).mappings()
                if row["proposal_id"] in scoped_proposal_ids
            ]
            proposal_ids = [decision["proposal_id"] for decision in decisions]
            proposals_by_id = {
                proposal["id"]: proposal
                for proposal in self._proposals_for_ids(conn, proposal_ids, spec.project_id)
            }
            runs_by_id = {
                row["id"]: normalize_json_row(row)
                for row in conn.execute(
                    select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                ).mappings()
            }
            sources_by_id = {
                row["id"]: self._source_from_row(row)
                for row in conn.execute(select(db.sources).where(db.sources.c.project_id == spec.project_id)).mappings()
            }

        items = []
        for decision in decisions[:normalized_limit]:
            proposal = proposals_by_id.get(decision["proposal_id"])
            source = None
            if proposal and (run := runs_by_id.get(proposal["ingestion_run_id"])):
                source = sources_by_id.get(run["source_id"])
            items.append(
                {
                    "decision": decision,
                    "proposal": proposal,
                    "source": source,
                    "summary": self._review_activity_summary(decision, proposal),
                }
            )

        return {
            "generated_at": now(),
            "review_decision_count": len(decisions),
            "returned_count": len(items),
            "items": items,
        }

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

    def source_review_coverage(self, *, limit: int = 25, graph_id: str | None = None, lens: str | None = None) -> dict:
        normalized_limit = min(100, max(1, limit))
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            sources = [
                self._source_from_row(row)
                for row in conn.execute(
                    select(db.sources)
                    .where(db.sources.c.project_id == spec.project_id)
                    .order_by(db.sources.c.created_at.desc(), db.sources.c.id.desc())
                ).mappings()
            ]
            if spec.source_ids:
                source_id_set = set(spec.source_ids)
                sources = [source for source in sources if source["id"] in source_id_set]
            runs_by_id = {
                row["id"]: normalize_json_row(row)
                for row in conn.execute(
                    select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                ).mappings()
            }
            proposals = self.list_proposals(graph_id=graph_id, lens=lens)
            decisions = [
                self._decision_from_row(row)
                for row in conn.execute(
                    select(db.review_decisions).where(db.review_decisions.c.project_id == spec.project_id)
                ).mappings()
            ]

        proposals_by_source_id: dict[str, list[dict]] = {source["id"]: [] for source in sources}
        for proposal in proposals:
            run = runs_by_id.get(proposal["ingestion_run_id"])
            if run and run["source_id"] in proposals_by_source_id:
                proposals_by_source_id[run["source_id"]].append(proposal)

        decisions_by_proposal_id: dict[str, list[dict]] = {}
        for decision in decisions:
            decisions_by_proposal_id.setdefault(decision["proposal_id"], []).append(decision)

        summaries = [
            self._source_review_summary(source, proposals_by_source_id.get(source["id"], []), decisions_by_proposal_id)
            for source in sources
        ]
        summaries.sort(
            key=lambda item: (
                -item["pending_count"],
                -item["proposal_count"],
                item["last_reviewed_at"] is None,
                item["last_reviewed_at"] or datetime.min.replace(tzinfo=UTC),
                item["source"]["title"],
                item["source"]["id"],
            )
        )

        return {
            "generated_at": now(),
            "source_count": len(sources),
            "proposal_count": len(proposals),
            "pending_count": sum(summary["pending_count"] for summary in summaries),
            "reviewed_count": sum(summary["reviewed_count"] for summary in summaries),
            "returned_count": min(len(summaries), normalized_limit),
            "sources": summaries[:normalized_limit],
        }

    def review(self, payload: ReviewDecisionCreate, reviewer_id: str) -> dict:
        with self.engine.begin() as conn:
            proposal_row = conn.execute(
                select(db.extraction_proposals).where(db.extraction_proposals.c.id == payload.proposal_id)
            ).mappings().first()
            if proposal_row is None:
                raise KeyError(payload.proposal_id)

            timestamp = now()
            edited = payload.edited_value
            project_id = proposal_row["project_id"]
            decision = {
                "id": new_id("review"),
                "project_id": project_id,
                "proposal_id": payload.proposal_id,
                "reviewer_id": reviewer_id,
                "decision": payload.decision,
                "edited_value_json": dump_json(edited) if edited is not None else None,
                "rationale": payload.rationale,
                "decided_at": timestamp,
            }
            self._record_review_decision(conn, proposal_row, decision, payload.decision, edited, timestamp)
        return self._decision_from_row(decision)

    def _record_review_decision(
        self,
        conn,
        proposal_row: dict,
        decision: dict,
        decision_value: str,
        edited: dict | None,
        timestamp: datetime,
    ) -> None:
        project_id = proposal_row["project_id"]
        proposal_id = proposal_row["id"]
        conn.execute(insert(db.review_decisions).values(**decision))
        conn.execute(
            update(db.extraction_proposals)
            .where(db.extraction_proposals.c.id == proposal_id)
            .values(status=self._proposal_status(decision_value))
        )
        proposal = self._proposal_from_row(proposal_row)
        proposal["status"] = self._proposal_status(decision_value)
        source = self._source_from_provenance(conn, proposal.get("provenance", []), project_id)
        self._record_activity_event(
            conn,
            project_id=project_id,
            event_type="proposal.reviewed",
            actor_id=decision["reviewer_id"],
            summary=self._review_activity_summary(self._decision_from_row(decision), proposal),
            object_refs=self._activity_refs_for_proposal(
                proposal,
                source=source,
                decision=self._decision_from_row(decision),
            ),
            payload={
                "proposal_id": proposal_id,
                "decision_id": decision["id"],
                "decision": decision_value,
                "status": proposal["status"],
                "rationale": decision.get("rationale"),
            },
            lenses=self._activity_lenses_for_proposal(proposal),
            timestamp=timestamp,
        )

        if decision_value not in {"accept", "edit"}:
            return

        value = edited if edited is not None else load_json(json_value(proposal_row, "proposed_value_json"), {})
        if proposal_row["kind"] == "content_node":
            node_id = value.get("id") or new_id("node")
            existing = conn.execute(
                select(db.content_nodes.c.id).where(
                    and_(db.content_nodes.c.id == node_id, db.content_nodes.c.project_id == project_id)
                )
            ).first()
            if existing is None:
                conn.execute(
                    insert(db.content_nodes).values(
                        id=node_id,
                        project_id=project_id,
                        label=value.get("label", "Untitled concept"),
                        kind=value.get("kind", "concept"),
                        summary=value.get("summary"),
                        topic_ids_json=dump_json(value.get("topicIds", [])),
                        metadata_json=dump_json(value.get("metadata") or {}),
                        provenance_json=json_value(proposal_row, "provenance_json"),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="graph.node_committed",
                    actor_id=decision["reviewer_id"],
                    summary=f"Committed node {value.get('label') or node_id}.",
                    object_refs=[
                        *self._activity_refs_for_proposal(
                            proposal,
                            source=source,
                            decision=self._decision_from_row(decision),
                        ),
                        self._activity_ref("node", node_id, value.get("label") or node_id),
                    ],
                    payload={
                        "proposal_id": proposal_id,
                        "decision_id": decision["id"],
                        "node_id": node_id,
                        "kind": value.get("kind", "concept"),
                    },
                    lenses=self._activity_lenses_for_proposal(proposal),
                    timestamp=timestamp,
                )
            conn.execute(
                update(db.content_embeddings)
                .where(db.content_embeddings.c.proposal_id == proposal_id)
                .values(content_node_id=node_id)
            )
            return

        if proposal_row["kind"] == "semantic_edge":
            if not self._nodes_exist(conn, [value["sourceNodeId"], value["targetNodeId"]], project_id=project_id):
                raise ValueError("Semantic edge endpoints must be accepted before the edge can be committed")
            edge_id = value.get("id") or new_id("edge")
            existing = conn.execute(
                select(db.semantic_edges.c.id).where(
                    and_(
                        db.semantic_edges.c.project_id == project_id,
                        or_(
                            db.semantic_edges.c.id == edge_id,
                            and_(
                                db.semantic_edges.c.source_node_id == value["sourceNodeId"],
                                db.semantic_edges.c.target_node_id == value["targetNodeId"],
                                db.semantic_edges.c.relation == value.get("relation", "relates_to"),
                            ),
                        ),
                    )
                )
            ).first()
            if existing is None:
                conn.execute(
                    insert(db.semantic_edges).values(
                        id=edge_id,
                        project_id=project_id,
                        source_node_id=value["sourceNodeId"],
                        target_node_id=value["targetNodeId"],
                        relation=value.get("relation", "relates_to"),
                        weight=value.get("weight"),
                        metadata_json=dump_json(value.get("metadata") or {}),
                        provenance_json=json_value(proposal_row, "provenance_json"),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="graph.edge_committed",
                    actor_id=decision["reviewer_id"],
                    summary=(
                        f"Committed relationship {value.get('sourceLabel') or value.get('sourceNodeId')} "
                        f"{value.get('relation', 'relates_to')} {value.get('targetLabel') or value.get('targetNodeId')}."
                    ),
                    object_refs=[
                        *self._activity_refs_for_proposal(
                            proposal,
                            source=source,
                            decision=self._decision_from_row(decision),
                        ),
                        self._activity_ref("edge", edge_id, value.get("label") or value.get("relation", "relates_to")),
                    ],
                    payload={
                        "proposal_id": proposal_id,
                        "decision_id": decision["id"],
                        "edge_id": edge_id,
                        "source_node_id": value["sourceNodeId"],
                        "target_node_id": value["targetNodeId"],
                        "relation": value.get("relation", "relates_to"),
                    },
                    lenses=self._activity_lenses_for_proposal(proposal),
                    timestamp=timestamp,
                )

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

    def lineage(self, entity_kind: str, entity_id: str, graph_id: str | None = None) -> dict | None:
        project_id = self._graph_view_spec(graph_id).project_id
        with self.engine.begin() as conn:
            if entity_kind == "source":
                return self._lineage_for_source(conn, entity_id, project_id)
            if entity_kind == "proposal":
                return self._lineage_for_proposal(conn, entity_id, project_id)
            if entity_kind == "node":
                return self._lineage_for_node(conn, entity_id, project_id)
            if entity_kind == "edge":
                return self._lineage_for_edge(conn, entity_id, project_id)
        return None

    def _lineage_for_source(self, conn, source_id: str, project_id: str) -> dict | None:
        source_row = conn.execute(
            select(db.sources).where(and_(db.sources.c.id == source_id, db.sources.c.project_id == project_id))
        ).mappings().first()
        if source_row is None:
            return None

        runs = [
            normalize_json_row(row)
            for row in conn.execute(
                select(db.ingestion_runs)
                .where(and_(db.ingestion_runs.c.source_id == source_id, db.ingestion_runs.c.project_id == project_id))
                .order_by(db.ingestion_runs.c.started_at.desc())
            ).mappings()
        ]
        run_ids = [run["id"] for run in runs]
        proposals = self._proposals_for_run_ids(conn, run_ids, project_id)
        proposal_ids = [proposal["id"] for proposal in proposals]
        return {
            "entity_kind": "source",
            "entity_id": source_id,
            "source": self._source_from_row(source_row),
            "ingestion_runs": runs,
            "proposals": proposals,
            "review_decisions": self._decisions_for_proposal_ids(conn, proposal_ids, project_id),
            "nodes": self._nodes_for_source(conn, source_id, project_id),
            "edges": self._edges_for_source(conn, source_id, project_id),
            "provenance": self._provenance_from_items(proposals),
        }

    def _lineage_for_proposal(self, conn, proposal_id: str, project_id: str) -> dict | None:
        proposal_row = conn.execute(
            select(db.extraction_proposals).where(
                and_(db.extraction_proposals.c.id == proposal_id, db.extraction_proposals.c.project_id == project_id)
            )
        ).mappings().first()
        if proposal_row is None:
            return None

        proposal = self._proposal_from_row(proposal_row)
        run = self._run_by_id(conn, proposal["ingestion_run_id"], project_id)
        source = self._source_by_id(conn, run["source_id"], project_id) if run else None
        nodes = self._nodes_for_proposal(conn, proposal, project_id)
        edges = self._edges_for_proposal(conn, proposal, project_id)
        return {
            "entity_kind": "proposal",
            "entity_id": proposal_id,
            "source": source,
            "ingestion_runs": [run] if run else [],
            "proposals": [proposal],
            "review_decisions": self._decisions_for_proposal_ids(conn, [proposal_id], project_id),
            "nodes": nodes,
            "edges": edges,
            "provenance": proposal["provenance"],
        }

    def _lineage_for_node(self, conn, node_id: str, project_id: str) -> dict | None:
        row = conn.execute(
            select(db.content_nodes).where(
                and_(db.content_nodes.c.id == node_id, db.content_nodes.c.project_id == project_id)
            )
        ).mappings().first()
        if row is None:
            return None

        node = self._node_from_row(row)
        provenance = node["provenance"]
        proposal = self._proposal_for_node(conn, node_id, project_id)
        proposals = [proposal] if proposal else []
        run = self._run_from_provenance(conn, provenance, project_id)
        source = self._source_from_provenance(conn, provenance, project_id)
        return {
            "entity_kind": "node",
            "entity_id": node_id,
            "source": source,
            "ingestion_runs": [run] if run else [],
            "proposals": proposals,
            "review_decisions": self._decisions_for_proposal_ids(conn, [proposal["id"] for proposal in proposals], project_id),
            "nodes": [node],
            "edges": self._edges_for_node(conn, node_id, project_id),
            "provenance": provenance,
        }

    def _lineage_for_edge(self, conn, edge_id: str, project_id: str) -> dict | None:
        row = conn.execute(
            select(db.semantic_edges).where(
                and_(db.semantic_edges.c.id == edge_id, db.semantic_edges.c.project_id == project_id)
            )
        ).mappings().first()
        if row is None:
            return None

        edge = self._edge_from_row(row)
        provenance = edge["provenance"]
        proposal = self._proposal_for_edge(conn, edge, project_id)
        proposals = [proposal] if proposal else []
        run = self._run_from_provenance(conn, provenance, project_id)
        source = self._source_from_provenance(conn, provenance, project_id)
        endpoint_nodes = [
            node
            for node_id in [edge["source_node_id"], edge["target_node_id"]]
            if (node := self._node_by_id(conn, node_id, project_id)) is not None
        ]
        return {
            "entity_kind": "edge",
            "entity_id": edge_id,
            "source": source,
            "ingestion_runs": [run] if run else [],
            "proposals": proposals,
            "review_decisions": self._decisions_for_proposal_ids(conn, [proposal["id"] for proposal in proposals], project_id),
            "nodes": endpoint_nodes,
            "edges": [edge],
            "provenance": provenance,
        }

    def _source_by_id(self, conn, source_id: str, project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
        row = conn.execute(
            select(db.sources).where(and_(db.sources.c.id == source_id, db.sources.c.project_id == project_id))
        ).mappings().first()
        return self._source_from_row(row) if row else None

    def _run_by_id(self, conn, run_id: str, project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
        row = conn.execute(
            select(db.ingestion_runs).where(
                and_(db.ingestion_runs.c.id == run_id, db.ingestion_runs.c.project_id == project_id)
            )
        ).mappings().first()
        return normalize_json_row(row) if row else None

    def _node_by_id(self, conn, node_id: str, project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
        row = conn.execute(
            select(db.content_nodes).where(
                and_(db.content_nodes.c.id == node_id, db.content_nodes.c.project_id == project_id)
            )
        ).mappings().first()
        return self._node_from_row(row) if row else None

    def _proposals_for_run_ids(self, conn, run_ids: list[str], project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        if not run_ids:
            return []
        return [
            self._proposal_from_row(row)
            for row in conn.execute(
                select(db.extraction_proposals)
                .where(
                    and_(
                        db.extraction_proposals.c.project_id == project_id,
                        db.extraction_proposals.c.ingestion_run_id.in_(run_ids),
                    )
                )
                .order_by(db.extraction_proposals.c.created_at.desc())
            ).mappings()
        ]

    def _proposals_for_ids(self, conn, proposal_ids: list[str], project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        if not proposal_ids:
            return []
        return [
            self._proposal_from_row(row)
            for row in conn.execute(
                select(db.extraction_proposals).where(
                    and_(
                        db.extraction_proposals.c.project_id == project_id,
                        db.extraction_proposals.c.id.in_(proposal_ids),
                    )
                )
            ).mappings()
        ]

    def _decisions_for_proposal_ids(
        self,
        conn,
        proposal_ids: list[str],
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> list[dict]:
        if not proposal_ids:
            return []
        return [
            self._decision_from_row(row)
            for row in conn.execute(
                select(db.review_decisions)
                .where(
                    and_(
                        db.review_decisions.c.project_id == project_id,
                        db.review_decisions.c.proposal_id.in_(proposal_ids),
                    )
                )
                .order_by(db.review_decisions.c.decided_at.desc())
            ).mappings()
        ]

    def _proposal_for_node(self, conn, node_id: str, project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
        row = conn.execute(
            select(db.extraction_proposals)
            .join(db.content_embeddings, db.content_embeddings.c.proposal_id == db.extraction_proposals.c.id)
            .where(
                and_(
                    db.extraction_proposals.c.project_id == project_id,
                    db.content_embeddings.c.content_node_id == node_id,
                )
            )
        ).mappings().first()
        return self._proposal_from_row(row) if row else None

    def _proposal_for_edge(self, conn, edge: dict, project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
        for row in conn.execute(
            select(db.extraction_proposals).where(
                and_(
                    db.extraction_proposals.c.project_id == project_id,
                    db.extraction_proposals.c.kind == "semantic_edge",
                )
            )
        ).mappings():
            proposal = self._proposal_from_row(row)
            value = proposal["proposed_value"]
            if value.get("id") == edge["id"] or (
                value.get("sourceNodeId") == edge["source_node_id"]
                and value.get("targetNodeId") == edge["target_node_id"]
                and value.get("relation", "relates_to") == edge["relation"]
            ):
                return proposal
        return None

    def _nodes_for_proposal(self, conn, proposal: dict, project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        if proposal["kind"] != "content_node":
            return []
        value = proposal["proposed_value"]
        node_id = value.get("id")
        if not node_id:
            return []
        node = self._node_by_id(conn, node_id, project_id)
        return [node] if node else []

    def _edges_for_proposal(self, conn, proposal: dict, project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        if proposal["kind"] != "semantic_edge":
            return []
        value = proposal["proposed_value"]
        edge_id = value.get("id")
        stmt = select(db.semantic_edges).where(db.semantic_edges.c.project_id == project_id)
        if edge_id:
            stmt = stmt.where(db.semantic_edges.c.id == edge_id)
        else:
            stmt = stmt.where(
                and_(
                    db.semantic_edges.c.source_node_id == value.get("sourceNodeId"),
                    db.semantic_edges.c.target_node_id == value.get("targetNodeId"),
                    db.semantic_edges.c.relation == value.get("relation", "relates_to"),
                )
            )
        return [self._edge_from_row(row) for row in conn.execute(stmt).mappings()]

    def _nodes_for_source(self, conn, source_id: str, project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        return [
            self._node_from_row(row)
            for row in conn.execute(select(db.content_nodes).where(db.content_nodes.c.project_id == project_id)).mappings()
            if any(item.get("sourceId") == source_id for item in load_json(json_value(row, "provenance_json"), []))
        ]

    def _edges_for_source(self, conn, source_id: str, project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        return [
            self._edge_from_row(row)
            for row in conn.execute(select(db.semantic_edges).where(db.semantic_edges.c.project_id == project_id)).mappings()
            if any(item.get("sourceId") == source_id for item in load_json(json_value(row, "provenance_json"), []))
        ]

    def _edges_for_node(self, conn, node_id: str, project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        return [
            self._edge_from_row(row)
            for row in conn.execute(
                select(db.semantic_edges).where(
                    and_(
                        db.semantic_edges.c.project_id == project_id,
                        or_(db.semantic_edges.c.source_node_id == node_id, db.semantic_edges.c.target_node_id == node_id),
                    )
                )
            ).mappings()
        ]

    def _source_from_provenance(
        self,
        conn,
        provenance: list[dict],
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> dict | None:
        source_id = next((item.get("sourceId") for item in provenance if item.get("sourceId")), None)
        return self._source_by_id(conn, source_id, project_id) if source_id else None

    def _run_from_provenance(
        self,
        conn,
        provenance: list[dict],
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> dict | None:
        run_id = next((item.get("ingestionRunId") for item in provenance if item.get("ingestionRunId")), None)
        return self._run_by_id(conn, run_id, project_id) if run_id else None

    def _provenance_from_items(self, proposals: list[dict]) -> list[dict]:
        seen: set[str] = set()
        provenance: list[dict] = []
        for proposal in proposals:
            for item in proposal["provenance"]:
                key = dump_json(item)
                if key not in seen:
                    seen.add(key)
                    provenance.append(item)
        return provenance

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
        redacted = value
        for pattern in AGENT_CONTEXT_SECRET_PATTERNS:
            redacted = pattern.sub(lambda match: f"{match.group(1)}=[redacted]" if match.lastindex else "[redacted]", redacted)
        return redacted

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

    def _record_proposal_created_activity(
        self,
        conn,
        *,
        proposal: dict,
        source: dict | None,
        ingestion_run: dict | None,
        actor_id: str,
        timestamp: datetime,
    ) -> None:
        self._record_activity_event(
            conn,
            project_id=proposal["project_id"],
            event_type="proposal.created",
            actor_id=actor_id,
            summary=self._proposal_activity_summary("Created", proposal),
            object_refs=self._activity_refs_for_proposal(proposal, source=source, ingestion_run=ingestion_run),
            payload={
                "proposal_id": proposal["id"],
                "kind": proposal["kind"],
                "status": proposal["status"],
                "confidence": proposal.get("confidence"),
                "source_id": source["id"] if source else None,
                "ingestion_run_id": ingestion_run["id"] if ingestion_run else proposal.get("ingestion_run_id"),
            },
            lenses=self._activity_lenses_for_proposal(proposal),
            timestamp=timestamp,
        )

    def _activity_ref(self, kind: str, object_id: str | None, label: str | None = None) -> dict:
        return {"kind": kind, "id": object_id or "", "label": label}

    def _activity_refs_for_proposal(
        self,
        proposal: dict,
        *,
        source: dict | None = None,
        ingestion_run: dict | None = None,
        decision: dict | None = None,
    ) -> list[dict]:
        value = proposal.get("proposed_value", {})
        refs = []
        if source is not None:
            refs.append(self._activity_ref("source", source["id"], source["title"]))
        if ingestion_run is not None:
            refs.append(self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run.get("stage")))
        refs.append(self._activity_ref("proposal", proposal["id"], self._proposal_activity_label(proposal)))
        if decision is not None:
            refs.append(self._activity_ref("review_decision", decision["id"], decision["decision"]))
        if proposal.get("kind") == "content_node" and isinstance(value.get("id"), str):
            refs.append(self._activity_ref("node", value["id"], value.get("label") or value["id"]))
        if proposal.get("kind") == "semantic_edge" and isinstance(value.get("id"), str):
            refs.append(self._activity_ref("edge", value["id"], value.get("label") or value.get("relation", "relates_to")))
        return refs

    def _activity_refs_from_agent_payload(self, input_payload: dict, output_payload: dict) -> list[dict]:
        refs: list[dict] = []
        for key, kind in [
            ("source_id", "source"),
            ("node_id", "node"),
            ("proposal_id", "proposal"),
            ("research_task_id", "research_task"),
            ("action_proposal_id", "agent_action_proposal"),
        ]:
            value = output_payload.get(key) or input_payload.get(key)
            if isinstance(value, str) and value:
                refs.append(self._activity_ref(kind, value, None))
        for proposal_id in output_payload.get("proposal_ids") or input_payload.get("proposal_ids") or []:
            if isinstance(proposal_id, str) and proposal_id:
                refs.append(self._activity_ref("proposal", proposal_id, None))
        return refs

    def _activity_lenses_from_agent_payload(self, input_payload: dict, output_payload: dict) -> list[str]:
        lens = normalize_graph_lens(input_payload.get("lens") if isinstance(input_payload.get("lens"), str) else None)
        if lens != "all":
            return [lens]
        output_lens = normalize_graph_lens(output_payload.get("lens") if isinstance(output_payload.get("lens"), str) else None)
        return [] if output_lens == "all" else [output_lens]

    def _activity_lenses_for_proposals(self, proposals: list[dict]) -> list[str]:
        lenses: set[str] = set()
        for proposal in proposals:
            lenses.update(self._activity_lenses_for_proposal(proposal))
        return sorted(lenses)

    def _activity_lenses_for_proposal(self, proposal: dict) -> list[str]:
        return [lens for lens in GRAPH_LENSES if self._proposal_matches_lens(proposal, lens)]

    def _proposal_activity_label(self, proposal: dict) -> str:
        value = proposal.get("proposed_value", {})
        if proposal.get("kind") == "semantic_edge":
            return (
                f"{value.get('sourceLabel') or value.get('sourceNodeId') or 'source'} "
                f"{value.get('relation') or 'relates_to'} "
                f"{value.get('targetLabel') or value.get('targetNodeId') or 'target'}"
            )
        return str(value.get("label") or value.get("id") or "Untitled proposal")

    def _proposal_activity_summary(self, verb: str, proposal: dict) -> str:
        if proposal.get("kind") == "semantic_edge":
            return f"{verb} relationship proposal {self._proposal_activity_label(proposal)}."
        return f"{verb} node proposal {self._proposal_activity_label(proposal)}."

    def _activity_event_matches_scope(self, event: dict, source_ids: tuple[str, ...]) -> bool:
        scoped_source_ids = set(source_ids)
        for ref in event.get("object_refs", []):
            if ref.get("kind") == "source" and ref.get("id") in scoped_source_ids:
                return True
        payload = event.get("payload", {})
        return payload.get("source_id") in scoped_source_ids

    def _review_activity_summary(self, decision: dict, proposal: dict | None) -> str:
        action = {
            "accept": "Accepted",
            "reject": "Rejected",
            "edit": "Edited",
            "defer": "Deferred",
        }.get(decision["decision"], "Reviewed")
        if proposal is None:
            return f"{action} unavailable proposal {decision['proposal_id']}."

        value = proposal["proposed_value"]
        if proposal["kind"] == "semantic_edge":
            source_label = value.get("sourceLabel") or value.get("sourceNodeId") or "source node"
            target_label = value.get("targetLabel") or value.get("targetNodeId") or "target node"
            relation = value.get("relation", "relates_to")
            return f"{action} relationship proposal {source_label} {relation} {target_label}."

        label = value.get("label") or value.get("id") or "Untitled node"
        return f"{action} node proposal {label}."

    def _source_review_summary(
        self,
        source: dict,
        proposals: list[dict],
        decisions_by_proposal_id: dict[str, list[dict]],
    ) -> dict:
        decisions = [
            decision
            for proposal in proposals
            for decision in decisions_by_proposal_id.get(proposal["id"], [])
        ]
        proposal_count = len(proposals)
        pending_count = sum(1 for proposal in proposals if proposal["status"] == "pending_review")
        reviewed_count = proposal_count - pending_count
        if proposal_count == 0:
            status = "no_proposals"
        elif pending_count == proposal_count:
            status = "pending_review"
        elif pending_count > 0:
            status = "mixed"
        else:
            status = "reviewed"

        return {
            "source": source,
            "status": status,
            "proposal_count": proposal_count,
            "pending_count": pending_count,
            "reviewed_count": reviewed_count,
            "decision_count": len(decisions),
            "accepted_count": sum(1 for decision in decisions if decision["decision"] == "accept"),
            "rejected_count": sum(1 for decision in decisions if decision["decision"] == "reject"),
            "edited_count": sum(1 for decision in decisions if decision["decision"] == "edit"),
            "deferred_count": sum(1 for decision in decisions if decision["decision"] == "defer"),
            "last_reviewed_at": max((decision["decided_at"] for decision in decisions), default=None),
        }

    def _review_queue_item(self, proposal: dict, source: dict | None, reviewed_node_ids: set[str]) -> dict:
        value = proposal["proposed_value"]
        source_title = source["title"] if source else None
        source_id = source["id"] if source else None
        locator = proposal["provenance"][0].get("locator") if proposal.get("provenance") else proposal.get("locator")
        citation = {
            "id": f"citation-{proposal['id']}",
            "label": source_title or "Proposal evidence",
            "source_id": source_id,
            "source_title": source_title,
            "proposal_id": proposal["id"],
            "locator": locator,
            "quote": value.get("summary") or value.get("label") or value.get("relation"),
            "confidence": proposal.get("confidence"),
        }
        if proposal["kind"] == "semantic_edge":
            endpoint_ids = [
                node_id
                for node_id in [value.get("sourceNodeId"), value.get("targetNodeId")]
                if isinstance(node_id, str) and node_id
            ]
            missing_endpoint_ids = [node_id for node_id in endpoint_ids if node_id not in reviewed_node_ids]
            blocked = bool(missing_endpoint_ids) or len(endpoint_ids) < 2
            return {
                "proposal": proposal,
                "source": source,
                "priority_score": 30 if blocked else 90,
                "action": "accept_endpoints" if blocked else "review_relationship",
                "work_item_kind": "new_relation",
                "change_summary": f"{value.get('sourceLabel') or value.get('sourceNodeId') or 'Source'} {value.get('relation') or 'relates_to'} {value.get('targetLabel') or value.get('targetNodeId') or 'target'}",
                "evidence_summary": source_title or "Relationship proposal evidence",
                "affected_graph_ids": endpoint_ids,
                "citations": [citation],
                "blocked": blocked,
                "ready_to_commit": not blocked,
                "reason": (
                    "Accept endpoint nodes before this relationship can be committed."
                    if blocked
                    else "Relationship endpoints are reviewed and ready for decision."
                ),
                "endpoint_node_ids": endpoint_ids,
                "missing_endpoint_node_ids": missing_endpoint_ids,
            }

        confidence = proposal.get("confidence") or 0
        return {
            "proposal": proposal,
            "source": source,
            "priority_score": 80 if confidence >= 0.75 else 60,
            "action": "review_node",
            "work_item_kind": "new_entity",
            "change_summary": f"Create {value.get('kind') or 'concept'}: {value.get('label') or 'Untitled proposal'}",
            "evidence_summary": source_title or "Source extraction proposal",
            "affected_graph_ids": [value["id"]] if isinstance(value.get("id"), str) else [],
            "citations": [citation],
            "blocked": False,
            "ready_to_commit": True,
            "reason": "High-confidence node proposal is ready for review." if confidence >= 0.75 else "Node proposal is ready for review.",
            "endpoint_node_ids": [],
            "missing_endpoint_node_ids": [],
        }

    def list_review_decisions(self, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            return [
                self._decision_from_row(row)
                for row in conn.execute(
                    select(db.review_decisions)
                    .where(db.review_decisions.c.project_id == spec.project_id)
                    .order_by(db.review_decisions.c.decided_at.desc())
                ).mappings()
            ]

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
        spec = self._graph_view_spec(graph_id)
        project, nodes, edges = self.graph(graph_id)
        proposals = self.list_proposals(graph_id=graph_id)
        proposal_ids = {proposal["id"] for proposal in proposals}
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

    def restore_bundle(self, bundle: ExportBundle) -> dict:
        project_id = bundle.project.id
        with self.engine.begin() as conn:
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
                db.connector_sync_runs,
                db.connector_targets,
                db.connector_accounts,
                db.topics,
                db.graph_settings,
            ]:
                conn.execute(delete(table).where(table.c.project_id == project_id))
            conn.execute(delete(db.graph_projects).where(db.graph_projects.c.id == project_id))

            conn.execute(insert(db.graph_projects).values(**bundle.project.model_dump()))
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
            ingestion_runs = [run.model_dump() for run in bundle.ingestion_runs]
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
                    "status": run.status,
                    "provider": run.provider,
                    "model": run.model,
                    "input_json": dump_json(run.input),
                    "output_json": dump_json(run.output),
                    "trace_id": run.trace_id,
                    "created_by": run.created_by,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "error": run.error,
                }
                for run in bundle.agent_runs
            ]
            agent_steps = [
                {
                    "id": step.id,
                    "project_id": step.project_id,
                    "agent_run_id": step.agent_run_id,
                    "name": step.name,
                    "status": step.status,
                    "input_summary": step.input_summary,
                    "output_summary": step.output_summary,
                    "error": step.error,
                    "trace_id": step.trace_id,
                    "metadata_json": dump_json(step.metadata),
                    "started_at": step.started_at,
                    "finished_at": step.finished_at,
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
                    "status": task.status,
                    "provider": task.provider,
                    "model": task.model,
                    "source_policy": task.source_policy,
                    "idempotency_key": task.idempotency_key,
                    "result_json": dump_json(task.result),
                    "created_by": task.created_by,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
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
            attention_items = [
                {
                    "id": item.id,
                    "project_id": item.project_id,
                    "kind": item.kind,
                    "status": item.status,
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
                    "updated_at": item.updated_at,
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
                    "status": action.status,
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
                    "updated_at": action.updated_at,
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
                    "status": run.status,
                    "executor_id": run.executor_id,
                    "target": run.target,
                    "payload_json": dump_json(run.redacted_payload),
                    "redacted_payload_json": dump_json(run.redacted_payload),
                    "external_id": run.external_id,
                    "trace_id": run.trace_id,
                    "error_code": run.error_code,
                    "error": run.error,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
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
                    "status": client.status,
                    "created_by": client.created_by,
                    "token_hash": f"restored:{client.id}",
                    "scopes_json": dump_json(client.scopes),
                    "settings_json": dump_json(client.settings),
                    "created_at": client.created_at,
                    "updated_at": client.updated_at,
                    "last_seen_at": client.last_seen_at,
                    "revoked_at": client.revoked_at,
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
                    "status": session.status,
                    "title": session.title,
                    "workspace_root": session.workspace_root,
                    "repository_uri": session.repository_uri,
                    "branch": session.branch,
                    "commit_sha": session.commit_sha,
                    "metadata_json": dump_json(session.metadata),
                    "started_at": session.started_at,
                    "ended_at": session.ended_at,
                    "updated_at": session.updated_at,
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

            for table, rows in [
                (db.topics, topics),
                (db.sources, sources),
                (db.source_chunks, source_chunks),
                (db.content_nodes, nodes),
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

    def _agent_context_client_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("token_hash", None)
        data["scopes"] = load_json(data.pop("scopes_json"), [])
        data["settings"] = self._redact_payload(load_json(data.pop("settings_json"), {}))
        return data

    def _agent_context_session_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _agent_context_artifact_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _agent_context_blob_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("encrypted_content", None)
        data.pop("object_key", None)
        data["metadata"] = load_json(data.pop("metadata_json"), {})
        return data

    def _agent_context_event_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["payload"] = load_json(data.pop("payload_json"), {})
        data["object_refs"] = load_json(data.pop("object_refs_json"), [])
        return data

    def _activity_event_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["object_refs"] = load_json(data.pop("object_refs_json"), [])
        data["payload"] = load_json(data.pop("payload_json"), {})
        data["lenses"] = load_json(data.pop("lenses_json"), [])
        return data

    def _settings_from_row(self, row, *, redact: bool = True) -> dict:
        data = normalize_json_row(row)
        settings = load_json(data.pop("settings_json"), {})
        data["settings"] = self._redact_settings(settings) if redact else settings
        return data

    def _redact_settings(self, value):
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                key_lower = key.lower()
                if key == AI_PROVIDER_CREDENTIALS_KEY and isinstance(item, dict):
                    redacted[key] = {
                        provider_id: {
                            "configured": isinstance(credential, dict) and bool(credential.get("encrypted_api_key")),
                            "updated_at": credential.get("updated_at") if isinstance(credential, dict) else None,
                        }
                        for provider_id, credential in item.items()
                    }
                elif key_lower in SENSITIVE_SETTINGS_KEYS:
                    continue
                else:
                    redacted[key] = self._redact_settings(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_settings(item) for item in value]
        return value

    def _connector_account_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("encrypted_token_json", None)
        data["scopes"] = load_json(data.pop("scopes_json"), [])
        data["settings"] = load_json(data.pop("settings_json"), {})
        return data

    def _connector_target_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["sync_settings"] = load_json(data.pop("sync_settings_json"), {})
        return data

    def _connector_sync_run_from_row(self, row) -> dict:
        return normalize_json_row(row)

    def _source_chunk_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["heading_path"] = load_json(data.pop("heading_path_json"), [])
        data["links"] = load_json(data.pop("links_json"), [])
        data["mentions"] = load_json(data.pop("mentions_json"), [])
        return data

    def _topic_from_row(self, row) -> dict:
        return normalize_json_row(row)

    def _proposal_status(self, decision: str) -> str:
        return {
            "accept": "accepted",
            "reject": "rejected",
            "edit": "edited",
            "defer": "deferred",
        }[decision]

    def _proposal_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["proposed_value"] = load_json(data.pop("proposed_value_json"), {})
        data["provenance"] = load_json(data.pop("provenance_json"), [])
        return data

    def _decision_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["edited_value"] = load_json(data.pop("edited_value_json"), None)
        return data

    def _embedding_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["vector"] = load_json(data.pop("vector_json"), [])
        return data

    def _source_values_from_payload(self, payload: SourceCreate | SourceUpdate, *, exclude_unset: bool = False) -> dict:
        values = payload.model_dump(exclude_unset=exclude_unset)
        if "metadata" in values:
            values["metadata_json"] = dump_json(values.pop("metadata") or {})
        return values

    def _source_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json", None), {})
        return data

    def _node_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["topic_ids"] = load_json(data.pop("topic_ids_json"), [])
        data["metadata"] = load_json(data.pop("metadata_json", None), {})
        data["provenance"] = load_json(data.pop("provenance_json"), [])
        return data

    def _edge_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = load_json(data.pop("metadata_json", None), {})
        data["provenance"] = load_json(data.pop("provenance_json"), [])
        return data
