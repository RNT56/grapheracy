from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict

from graphview_api.api_v1.repository import GraphProjectionRepository
from graphview_api.api_v1.schemas import GraphBounds
from graphview_api.repository import GraphRepository


class GraphProjectionService:
    def __init__(self, projection: GraphProjectionRepository, legacy: GraphRepository):
        self.projection = projection
        self.legacy = legacy

    def project_id(self, graph_id: str) -> str:
        return graph_id.split(":", 1)[0]

    def viewport(
        self,
        graph_id: str,
        *,
        zoom: float,
        bounds: GraphBounds,
        layout_name: str,
        max_nodes: int,
        max_edges: int,
    ) -> dict:
        project_id = self.project_id(graph_id)
        version = self.projection.graph_version(project_id)
        projected = self.projection.projected_viewport(
            project_id,
            layout_name=layout_name,
            bounds=bounds,
            zoom=zoom,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
        if projected is not None:
            level = "clusters" if projected["clusters"] else "nodes"
            etag = f'"graph-{project_id}-v{version["version"]}-{layout_name}-{zoom:.2f}"'
            return {
                "graph_id": graph_id,
                "project_id": project_id,
                "graph_version": version["version"],
                "etag": etag,
                "zoom": zoom,
                "level": level,
                "bounds": bounds.model_dump(),
                "nodes": projected["nodes"],
                "edges": projected["edges"],
                "clusters": projected["clusters"],
                "omitted_node_count": max(0, projected["total_nodes"] - len(projected["nodes"]) - sum(cluster["node_count"] for cluster in projected["clusters"])),
                "omitted_edge_count": max(0, version["edge_count"] - sum(edge["count"] for edge in projected["edges"])),
                "page": {"next_cursor": None, "returned_count": len(projected["nodes"]) + len(projected["clusters"]), "total_count": projected["total_nodes"]},
            }
        nodes, edges = self.projection.graph_rows(project_id)
        layout = self.projection.get_layout(project_id, layout_name)
        saved_positions = {item["node_id"]: item for item in (layout or {}).get("positions", [])}
        positioned = []
        for node in nodes:
            position = saved_positions.get(node["id"]) or self._deterministic_position(node["id"])
            if bounds.min_x <= position["x"] <= bounds.max_x and bounds.min_y <= position["y"] <= bounds.max_y:
                positioned.append({"node": node, "x": position["x"], "y": position["y"], "z": position.get("z")})

        node_ids = {item["node"]["id"] for item in positioned}
        visible_edges = [edge for edge in edges if edge["source_node_id"] in node_ids and edge["target_node_id"] in node_ids]
        cluster_mode = zoom < 1.75 or len(positioned) > max_nodes
        if cluster_mode:
            nodes_out, clusters, edges_out = self._cluster(positioned, visible_edges, zoom=zoom, max_items=max_nodes, max_edges=max_edges)
            level = "clusters" if not nodes_out else "mixed"
        else:
            selected = positioned[:max_nodes]
            selected_ids = {item["node"]["id"] for item in selected}
            selected_edges = [edge for edge in visible_edges if edge["source_node_id"] in selected_ids and edge["target_node_id"] in selected_ids][:max_edges]
            nodes_out = selected
            clusters = []
            edges_out = [
                {
                    "id": edge["id"],
                    "source_id": edge["source_node_id"],
                    "target_id": edge["target_node_id"],
                    "relation": edge["relation"],
                    "weight": edge.get("weight"),
                    "count": 1,
                    "edge": edge,
                }
                for edge in selected_edges
            ]
            level = "nodes"

        etag = f'"graph-{project_id}-v{version["version"]}-{layout_name}-{zoom:.2f}"'
        return {
            "graph_id": graph_id,
            "project_id": project_id,
            "graph_version": version["version"],
            "etag": etag,
            "zoom": zoom,
            "level": level,
            "bounds": bounds.model_dump(),
            "nodes": nodes_out,
            "edges": edges_out,
            "clusters": clusters,
            "omitted_node_count": max(0, len(positioned) - len(nodes_out) - sum(cluster["node_count"] for cluster in clusters)),
            "omitted_edge_count": max(0, len(visible_edges) - sum(edge["count"] for edge in edges_out)),
            "page": {"next_cursor": None, "returned_count": len(nodes_out) + len(clusters), "total_count": len(positioned)},
        }

    def subgraph(self, graph_id: str, *, focus_node_id: str | None, depth: int, max_nodes: int) -> dict:
        project_id = self.project_id(graph_id)
        version = self.projection.graph_version(project_id)
        if focus_node_id:
            result = self.legacy.neighborhood(focus_node_id, depth=depth, limit=max_nodes, graph_id=graph_id)
            if result is None:
                return None
            nodes = result["nodes"]
            edges = result["edges"]
            omitted_nodes = result["omitted_node_count"]
            omitted_edges = result["omitted_edge_count"]
        else:
            _, all_nodes, all_edges = self.legacy.graph(graph_id)
            nodes = all_nodes[:max_nodes]
            node_ids = {node["id"] for node in nodes}
            edges = [edge for edge in all_edges if edge["source_node_id"] in node_ids and edge["target_node_id"] in node_ids]
            omitted_nodes = max(0, len(all_nodes) - len(nodes))
            omitted_edges = max(0, len(all_edges) - len(edges))
        return {
            "graph_id": graph_id,
            "project_id": project_id,
            "graph_version": version["version"],
            "focus_node_id": focus_node_id,
            "depth": depth,
            "nodes": nodes,
            "edges": edges,
            "omitted_node_count": omitted_nodes,
            "omitted_edge_count": omitted_edges,
        }

    def search(self, graph_id: str, query: str, *, limit: int, actor_id: str) -> dict:
        hybrid = self.projection.hybrid_search(graph_id, query, limit=limit, actor_id=actor_id)
        if hybrid is not None:
            return {
                "graph_id": graph_id,
                "query": query,
                "anchors": hybrid,
                "page": {"next_cursor": None, "returned_count": len(hybrid), "total_count": len(hybrid)},
            }
        result = self.legacy.search(query, graph_id)
        anchors = []
        for index, node in enumerate(result.get("nodes", [])):
            anchors.append({
                "id": node["id"], "kind": "node", "label": node["label"], "summary": node.get("summary"),
                "score": max(0.01, 1 - index * 0.04), "node_id": node["id"], "source_id": None,
            })
        for index, source in enumerate(result.get("sources", [])):
            anchors.append({
                "id": source["id"], "kind": "source", "label": source["title"], "summary": None,
                "score": max(0.01, 0.9 - index * 0.04), "node_id": None, "source_id": source["id"],
            })
        anchors = sorted(anchors, key=lambda item: (-item["score"], item["label"].lower()))[:limit]
        return {
            "graph_id": graph_id,
            "query": query,
            "anchors": anchors,
            "page": {"next_cursor": None, "returned_count": len(anchors), "total_count": len(anchors)},
        }

    def _cluster(self, positioned: list[dict], edges: list[dict], *, zoom: float, max_items: int, max_edges: int):
        cell_size = max(0.04, min(0.8, 0.65 / (2 ** max(0.0, zoom))))
        groups = defaultdict(list)
        for item in positioned:
            cell = (math.floor(item["x"] / cell_size), math.floor(item["y"] / cell_size))
            groups[cell].append(item)
        ordered_groups = sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:max_items]
        nodes_out = []
        clusters = []
        node_to_visible = {}
        for cell, items in ordered_groups:
            if len(items) == 1:
                nodes_out.append(items[0])
                node_to_visible[items[0]["node"]["id"]] = items[0]["node"]["id"]
                continue
            cluster_id = f"cluster:{cell[0]}:{cell[1]}"
            kinds = Counter(item["node"]["kind"] for item in items)
            clusters.append({
                "id": cluster_id,
                "label": f"{len(items)} related items",
                "x": sum(item["x"] for item in items) / len(items),
                "y": sum(item["y"] for item in items) / len(items),
                "node_count": len(items),
                "edge_count": 0,
                "dominant_kind": kinds.most_common(1)[0][0],
                "node_ids": [item["node"]["id"] for item in items[:64]],
            })
            for item in items:
                node_to_visible[item["node"]["id"]] = cluster_id
        aggregated = {}
        for edge in edges:
            source = node_to_visible.get(edge["source_node_id"])
            target = node_to_visible.get(edge["target_node_id"])
            if not source or not target or source == target:
                continue
            key = (source, target, edge["relation"])
            value = aggregated.setdefault(key, {"id": f"aggregate:{hashlib.sha1(str(key).encode()).hexdigest()[:16]}", "source_id": source, "target_id": target, "relation": edge["relation"], "weight": edge.get("weight"), "count": 0, "edge": None})
            value["count"] += 1
        cluster_by_id = {cluster["id"]: cluster for cluster in clusters}
        for edge in aggregated.values():
            if edge["source_id"] in cluster_by_id:
                cluster_by_id[edge["source_id"]]["edge_count"] += edge["count"]
            if edge["target_id"] in cluster_by_id:
                cluster_by_id[edge["target_id"]]["edge_count"] += edge["count"]
        return nodes_out, clusters, list(aggregated.values())[:max_edges]

    def _deterministic_position(self, node_id: str) -> dict:
        digest = hashlib.sha256(node_id.encode()).digest()
        x = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF * 2 - 1
        y = int.from_bytes(digest[4:8], "big") / 0xFFFFFFFF * 2 - 1
        z = int.from_bytes(digest[8:12], "big") / 0xFFFFFFFF * 2 - 1
        return {"x": x, "y": y, "z": z}
