from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from graphview_api import db
from graphview_api.json_compat import normalize_json_row
from graphview_api.lenses import normalize_graph_lens

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


def now() -> datetime:
    return datetime.now(tz=UTC)


class GraphReadRepositoryMixin:
    """Graph views, lens projection, bounded traversal, and insight persistence reads."""

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
