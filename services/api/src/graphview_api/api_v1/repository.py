from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, delete, func, insert, select, text, update

from graphview_api import db
from graphview_api.repository import GraphRepository, dump_json, load_json
from graphview_api.ingestion import embed_text
from graphview_api.json_compat import normalize_json_row


class GraphProjectionRepository:
    """Persistence boundary for viewport projection, graph versions, and saved layouts."""

    def __init__(self, legacy: GraphRepository):
        self.legacy = legacy
        self.engine = legacy.engine

    def graph_version(self, project_id: str) -> dict:
        with self.engine.begin() as conn:
            if self.engine.dialect.name == "postgresql":
                persisted = conn.execute(
                    select(db.graph_versions).where(db.graph_versions.c.project_id == project_id)
                ).mappings().first()
                if persisted is not None:
                    return dict(persisted)
            counts = conn.execute(
                select(
                    select(func.count()).select_from(db.content_nodes).where(db.content_nodes.c.project_id == project_id).scalar_subquery(),
                    select(func.count()).select_from(db.semantic_edges).where(db.semantic_edges.c.project_id == project_id).scalar_subquery(),
                )
            ).one()
            node_count, edge_count = int(counts[0]), int(counts[1])
            row = conn.execute(select(db.graph_versions).where(db.graph_versions.c.project_id == project_id)).mappings().first()
            timestamp = datetime.now(tz=UTC)
            if row is None:
                values = {
                    "project_id": project_id,
                    "version": 1,
                    "node_count": node_count,
                    "edge_count": edge_count,
                    "updated_at": timestamp,
                }
                conn.execute(insert(db.graph_versions).values(**values))
                return values
            version = int(row["version"])
            if row["node_count"] != node_count or row["edge_count"] != edge_count:
                version += 1
                conn.execute(
                    update(db.graph_versions)
                    .where(db.graph_versions.c.project_id == project_id)
                    .values(version=version, node_count=node_count, edge_count=edge_count, updated_at=timestamp)
                )
            return {
                "project_id": project_id,
                "version": version,
                "node_count": node_count,
                "edge_count": edge_count,
                "updated_at": row["updated_at"] if version == row["version"] else timestamp,
            }

    def graph_rows(self, project_id: str) -> tuple[list[dict], list[dict]]:
        with self.engine.begin() as conn:
            nodes = [self.legacy._node_from_row(row) for row in conn.execute(select(db.content_nodes).where(db.content_nodes.c.project_id == project_id)).mappings()]
            edges = [self.legacy._edge_from_row(row) for row in conn.execute(select(db.semantic_edges).where(db.semantic_edges.c.project_id == project_id)).mappings()]
        return nodes, edges

    def list_layouts(self, project_id: str, *, include_positions: bool = False) -> list[dict]:
        with self.engine.begin() as conn:
            layouts = list(
                conn.execute(
                    select(db.graph_layouts)
                    .where(db.graph_layouts.c.project_id == project_id)
                    .order_by(db.graph_layouts.c.updated_at.desc(), db.graph_layouts.c.name.asc())
                ).mappings()
            )
            return [self._layout_from_row(conn, row, include_positions=include_positions) for row in layouts]

    def get_layout(self, project_id: str, name: str, *, include_positions: bool = True) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_layouts).where(and_(db.graph_layouts.c.project_id == project_id, db.graph_layouts.c.name == name))
            ).mappings().first()
            return self._layout_from_row(conn, row, include_positions=include_positions) if row else None

    def upsert_layout(self, project_id: str, payload, *, actor_id: str) -> dict:
        timestamp = datetime.now(tz=UTC)
        graph_version = payload.graph_version or self.graph_version(project_id)["version"]
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(db.graph_layouts).where(and_(db.graph_layouts.c.project_id == project_id, db.graph_layouts.c.name == payload.name))
            ).mappings().first()
            if existing:
                layout_id = existing["id"]
                conn.execute(
                    update(db.graph_layouts)
                    .where(db.graph_layouts.c.id == layout_id)
                    .values(
                        algorithm=payload.algorithm,
                        graph_version=graph_version,
                        settings_json=dump_json(payload.settings),
                        updated_at=timestamp,
                    )
                )
                conn.execute(delete(db.graph_layout_positions).where(db.graph_layout_positions.c.layout_id == layout_id))
            else:
                layout_id = f"layout_{uuid4().hex[:20]}"
                conn.execute(
                    insert(db.graph_layouts).values(
                        id=layout_id,
                        project_id=project_id,
                        name=payload.name,
                        algorithm=payload.algorithm,
                        graph_version=graph_version,
                        settings_json=dump_json(payload.settings),
                        created_by=actor_id,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            node_ids = set(
                conn.execute(select(db.content_nodes.c.id).where(db.content_nodes.c.project_id == project_id)).scalars()
            )
            unknown = sorted({position.node_id for position in payload.positions} - node_ids)
            if unknown:
                raise ValueError(f"Layout contains unknown project nodes: {', '.join(unknown[:5])}")
            conn.execute(
                insert(db.graph_layout_positions),
                [
                    {
                        "layout_id": layout_id,
                        "node_id": position.node_id,
                        "x": position.x,
                        "y": position.y,
                        "z": position.z,
                        "cluster_key": position.cluster_key,
                    }
                    for position in payload.positions
                ],
            )
            row = conn.execute(select(db.graph_layouts).where(db.graph_layouts.c.id == layout_id)).mappings().one()
            return self._layout_from_row(conn, row, include_positions=True)

    def projected_viewport(
        self,
        project_id: str,
        *,
        layout_name: str,
        bounds,
        zoom: float,
        max_nodes: int,
        max_edges: int,
    ) -> dict | None:
        if self.engine.dialect.name != "postgresql":
            return None
        with self.engine.begin() as conn:
            layout_id = conn.execute(
                select(db.graph_layouts.c.id).where(
                    and_(db.graph_layouts.c.project_id == project_id, db.graph_layouts.c.name == layout_name)
                )
            ).scalar_one_or_none()
            if layout_id is None:
                return None
            parameters = {
                "project_id": project_id,
                "layout_id": layout_id,
                "min_x": bounds.min_x,
                "min_y": bounds.min_y,
                "max_x": bounds.max_x,
                "max_y": bounds.max_y,
                "max_nodes": max_nodes,
                "max_edges": max_edges,
                "edge_scan_limit": min(40_000, max(16_000, max_edges * 2)),
            }
            total_nodes = int(conn.execute(text("""
                SELECT count(*) FROM graph_layout_positions p JOIN content_nodes n ON n.id=p.node_id
                WHERE p.layout_id=:layout_id AND n.project_id=:project_id
                  AND p.x BETWEEN :min_x AND :max_x AND p.y BETWEEN :min_y AND :max_y
            """), parameters).scalar_one())
            if zoom < 1.75 or total_nodes > max_nodes:
                parameters["cell"] = max(0.04, min(0.8, 0.65 / (2 ** max(0.0, zoom))))
                clusters = [dict(row) for row in conn.execute(text("""
                    SELECT concat('cluster:', floor(p.x/:cell)::bigint, ':', floor(p.y/:cell)::bigint) AS id,
                      concat(count(*), ' related items') AS label, avg(p.x) AS x, avg(p.y) AS y,
                      count(*) AS node_count, 0 AS edge_count, mode() WITHIN GROUP (ORDER BY n.kind) AS dominant_kind
                    FROM graph_layout_positions p JOIN content_nodes n ON n.id=p.node_id
                    WHERE p.layout_id=:layout_id AND n.project_id=:project_id
                      AND p.x BETWEEN :min_x AND :max_x AND p.y BETWEEN :min_y AND :max_y
                    GROUP BY floor(p.x/:cell), floor(p.y/:cell)
                    ORDER BY count(*) DESC LIMIT :max_nodes
                """), parameters).mappings()]
                edges = [dict(row) for row in conn.execute(text("""
                    WITH positioned AS MATERIALIZED (
                      SELECT n.id, floor(p.x/:cell)::bigint gx, floor(p.y/:cell)::bigint gy
                      FROM graph_layout_positions p JOIN content_nodes n ON n.id=p.node_id
                      WHERE p.layout_id=:layout_id AND n.project_id=:project_id
                        AND p.x BETWEEN :min_x AND :max_x AND p.y BETWEEN :min_y AND :max_y
                    ), edge_sample AS MATERIALIZED (
                      SELECT id, source_node_id, target_node_id, relation, weight
                      FROM semantic_edges WHERE project_id=:project_id LIMIT :edge_scan_limit
                    )
                    SELECT concat('aggregate:', s.gx, ':', s.gy, ':', t.gx, ':', t.gy, ':', e.relation) AS id,
                      concat('cluster:', s.gx, ':', s.gy) source_id, concat('cluster:', t.gx, ':', t.gy) target_id,
                      e.relation, avg(e.weight) weight, count(*) count
                    FROM edge_sample e JOIN positioned s ON s.id=e.source_node_id JOIN positioned t ON t.id=e.target_node_id
                    WHERE (s.gx,s.gy)<>(t.gx,t.gy)
                    GROUP BY s.gx,s.gy,t.gx,t.gy,e.relation ORDER BY count(*) DESC LIMIT :max_edges
                """), parameters).mappings()]
                return {"nodes": [], "clusters": clusters, "edges": [{**edge, "edge": None} for edge in edges], "total_nodes": total_nodes}
            node_rows = [dict(row) for row in conn.execute(text("""
                SELECT n.*, p.x AS projection_x, p.y AS projection_y, p.z AS projection_z
                FROM graph_layout_positions p JOIN content_nodes n ON n.id=p.node_id
                WHERE p.layout_id=:layout_id AND n.project_id=:project_id
                  AND p.x BETWEEN :min_x AND :max_x AND p.y BETWEEN :min_y AND :max_y
                ORDER BY n.id LIMIT :max_nodes
            """), parameters).mappings()]
            node_ids = [row["id"] for row in node_rows]
            if not node_ids:
                return {"nodes": [], "clusters": [], "edges": [], "total_nodes": total_nodes}
            edge_rows = conn.execute(
                select(db.semantic_edges).where(
                    and_(
                        db.semantic_edges.c.project_id == project_id,
                        db.semantic_edges.c.source_node_id.in_(node_ids),
                        db.semantic_edges.c.target_node_id.in_(node_ids),
                    )
                ).limit(max_edges)
            ).mappings()
            edges = []
            for row in edge_rows:
                edge = self.legacy._edge_from_row(row)
                edges.append({"id": edge["id"], "source_id": edge["source_node_id"], "target_id": edge["target_node_id"], "relation": edge["relation"], "weight": edge.get("weight"), "count": 1, "edge": edge})
            return {
                "nodes": [{"node": self.legacy._node_from_row(row), "x": row["projection_x"], "y": row["projection_y"], "z": row["projection_z"]} for row in node_rows],
                "clusters": [],
                "edges": edges,
                "total_nodes": total_nodes,
            }

    def hybrid_search(self, graph_id: str, query: str, *, limit: int, actor_id: str) -> list[dict] | None:
        if self.engine.dialect.name != "postgresql":
            return None
        project_id = self.legacy._graph_view_spec(graph_id).project_id
        embedding = "[" + ",".join(str(value) for value in embed_text(query)) + "]"
        statement = text("""
            WITH node_matches AS (
              SELECT n.id, 'node' AS kind, n.label, n.summary,
                ts_rank_cd(to_tsvector('english', coalesce(n.label, '') || ' ' || coalesce(n.summary, '')), plainto_tsquery('english', :query)) * 0.65
                + coalesce((1 - (e.vector_native <=> CAST(:embedding AS vector))) * 0.35, 0) AS score
              FROM content_nodes n
              LEFT JOIN content_embeddings e ON e.content_node_id = n.id AND e.vector_native IS NOT NULL
              WHERE n.project_id = :project_id
            ), source_matches AS (
              SELECT s.id, 'source' AS kind, s.title AS label, NULL AS summary,
                ts_rank_cd(to_tsvector('english', coalesce(s.title, '') || ' ' || coalesce(s.uri, '')), plainto_tsquery('english', :query)) * 0.65 AS score
              FROM sources s WHERE s.project_id = :project_id
            )
            SELECT id, kind, label, summary, score FROM (
              SELECT * FROM node_matches UNION ALL SELECT * FROM source_matches
            ) ranked WHERE score > 0 ORDER BY score DESC, label ASC LIMIT :limit
        """)
        timestamp = datetime.now(tz=UTC)
        with self.engine.begin() as conn:
            rows = [dict(row) for row in conn.execute(
                statement,
                {"query": query, "embedding": embedding, "project_id": project_id, "limit": limit},
            ).mappings()]
            conn.execute(
                insert(db.audit_events).values(
                    id=f"audit_{uuid4().hex[:20]}",
                    project_id=project_id,
                    actor_id=actor_id,
                    action="graph.search",
                    resource_type="graph",
                    resource_id=graph_id,
                    outcome="succeeded",
                    summary=f"Hybrid retrieval returned {len(rows)} anchors.",
                    metadata_json=dump_json({"query_sha256": hashlib.sha256(query.encode()).hexdigest(), "limit": limit}),
                    trace_id=f"trace_{uuid4().hex[:20]}",
                    occurred_at=timestamp,
                )
            )
        return [
            {
                **row,
                "score": float(row["score"]),
                "node_id": row["id"] if row["kind"] == "node" else None,
                "source_id": row["id"] if row["kind"] == "source" else None,
            }
            for row in rows
        ]

    def _layout_from_row(self, conn, row, *, include_positions: bool) -> dict:
        positions = []
        position_count = conn.execute(
            select(func.count()).select_from(db.graph_layout_positions).where(db.graph_layout_positions.c.layout_id == row["id"])
        ).scalar_one()
        if include_positions:
            positions = [
                dict(position)
                for position in conn.execute(
                    select(
                        db.graph_layout_positions.c.node_id,
                        db.graph_layout_positions.c.x,
                        db.graph_layout_positions.c.y,
                        db.graph_layout_positions.c.z,
                        db.graph_layout_positions.c.cluster_key,
                    )
                    .where(db.graph_layout_positions.c.layout_id == row["id"])
                    .order_by(db.graph_layout_positions.c.node_id)
                ).mappings()
            ]
        data = normalize_json_row(row)
        data["settings"] = load_json(data.pop("settings_json"), {})
        data["position_count"] = int(position_count)
        data["positions"] = positions
        return data
