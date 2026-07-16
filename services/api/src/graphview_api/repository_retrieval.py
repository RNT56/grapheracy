from __future__ import annotations

import re

from sqlalchemy import select, text

from graphview_api import db
from graphview_api.ingestion import embed_text
from graphview_api.schemas import GraphQueryCreate


class RetrievalMatcher:
    """Bounded text/vector candidate retrieval behind the graph repository boundary."""

    def __init__(self, legacy_repository) -> None:
        self.legacy = legacy_repository

    def postgres(self, conn, *, spec, payload: GraphQueryCreate) -> list[dict]:
        parameters: dict = {
            "project_id": spec.project_id,
            "query": payload.question,
            "embedding": "[" + ",".join(str(value) for value in embed_text(payload.question)) + "]",
            "node_id": payload.node_id,
            "source_id": payload.source_id,
            "source_chunk_id": payload.source_chunk_id,
            "limit": 24,
        }
        source_clause = ""
        chunk_source_clause = ""
        node_source_clause = ""
        if spec.source_ids:
            parameters["view_source_ids"] = list(spec.source_ids)
            source_clause = " AND s.id = ANY(CAST(:view_source_ids AS varchar[]))"
            chunk_source_clause = " AND c.source_id = ANY(CAST(:view_source_ids AS varchar[]))"
            node_source_clause = """
              AND EXISTS (
                SELECT 1 FROM jsonb_array_elements(coalesce(n.provenance_json__jsonb, '[]'::jsonb)) AS provenance
                WHERE provenance->>'sourceId' = ANY(CAST(:view_source_ids AS varchar[]))
              )
            """
        statement = text(
            f"""
            WITH query_value AS (
              SELECT websearch_to_tsquery('english', :query) AS tsquery
            ), node_matches AS (
              SELECT n.id, 'node' AS kind, n.id AS node_id, NULL::varchar AS source_id,
                NULL::varchar AS source_chunk_id,
                ts_rank_cd(
                  to_tsvector('english', coalesce(n.label, '') || ' ' || coalesce(n.summary, '')),
                  query_value.tsquery
                ) * 0.65
                + CASE
                    WHEN embedding.vector_native IS NOT NULL
                      AND 1 - (embedding.vector_native <=> CAST(:embedding AS vector)) >= 0.72
                    THEN (1 - (embedding.vector_native <=> CAST(:embedding AS vector))) * 0.35
                    ELSE 0
                  END AS score
              FROM content_nodes n
              CROSS JOIN query_value
              LEFT JOIN LATERAL (
                SELECT e.vector_native FROM content_embeddings e
                WHERE e.content_node_id = n.id AND e.vector_native IS NOT NULL
                ORDER BY e.created_at DESC LIMIT 1
              ) embedding ON true
              WHERE n.project_id = :project_id
                AND (CAST(:node_id AS varchar) IS NULL OR n.id = CAST(:node_id AS varchar))
                {node_source_clause}
            ), source_matches AS (
              SELECT s.id, 'source' AS kind, NULL::varchar AS node_id, s.id AS source_id,
                NULL::varchar AS source_chunk_id,
                ts_rank_cd(
                  to_tsvector('english', coalesce(s.title, '') || ' ' || coalesce(s.uri, '')),
                  query_value.tsquery
                ) * 0.65 AS score
              FROM sources s CROSS JOIN query_value
              WHERE s.project_id = :project_id
                AND (CAST(:source_id AS varchar) IS NULL OR s.id = CAST(:source_id AS varchar))
                {source_clause}
            ), chunk_matches AS (
              SELECT c.id, 'chunk' AS kind, NULL::varchar AS node_id, c.source_id AS source_id,
                c.id AS source_chunk_id,
                ts_rank_cd(to_tsvector('english', c.text), query_value.tsquery) * 0.85 AS score
              FROM source_chunks c CROSS JOIN query_value
              WHERE c.project_id = :project_id
                AND (CAST(:source_id AS varchar) IS NULL OR c.source_id = CAST(:source_id AS varchar))
                AND (CAST(:source_chunk_id AS varchar) IS NULL OR c.id = CAST(:source_chunk_id AS varchar))
                {chunk_source_clause}
            )
            SELECT id, kind, node_id, source_id, source_chunk_id, score
            FROM (
              SELECT * FROM node_matches
              UNION ALL SELECT * FROM source_matches
              UNION ALL SELECT * FROM chunk_matches
            ) ranked
            WHERE score > 0
            ORDER BY score DESC, kind, id
            LIMIT :limit
            """
        )
        return [dict(row) for row in conn.execute(statement, parameters).mappings()]

    def portable(self, conn, *, spec, payload: GraphQueryCreate) -> list[dict]:
        terms = {
            term
            for term in re.findall(r"[a-z0-9]+", payload.question.lower())
            if len(term) >= 3 and term not in {"the", "and", "for", "from", "what", "when", "where", "which", "with"}
        }
        allowed_sources = set(spec.source_ids) if spec.source_ids else None
        matches: list[dict] = []

        def score(value: str) -> float:
            lowered = value.lower()
            return float(sum(1 for term in terms if term in lowered)) / max(1, len(terms))

        node_stmt = select(db.content_nodes).where(db.content_nodes.c.project_id == spec.project_id)
        if payload.node_id:
            node_stmt = node_stmt.where(db.content_nodes.c.id == payload.node_id)
        for row in conn.execute(node_stmt).mappings():
            node = self.legacy._node_from_row(row)
            provenance_sources = {item.get("sourceId") for item in node.get("provenance", [])}
            if allowed_sources is not None and not provenance_sources.intersection(allowed_sources):
                continue
            value_score = score(f"{node['label']} {node.get('summary') or ''}")
            if value_score > 0:
                matches.append({"id": node["id"], "kind": "node", "node_id": node["id"], "source_id": None, "source_chunk_id": None, "score": value_score})

        source_stmt = select(db.sources).where(db.sources.c.project_id == spec.project_id)
        if payload.source_id:
            source_stmt = source_stmt.where(db.sources.c.id == payload.source_id)
        for row in conn.execute(source_stmt).mappings():
            if allowed_sources is not None and row["id"] not in allowed_sources:
                continue
            value_score = score(f"{row['title']} {row['uri'] or ''}")
            if value_score > 0:
                matches.append({"id": row["id"], "kind": "source", "node_id": None, "source_id": row["id"], "source_chunk_id": None, "score": value_score})

        chunk_stmt = select(db.source_chunks).where(db.source_chunks.c.project_id == spec.project_id)
        if payload.source_id:
            chunk_stmt = chunk_stmt.where(db.source_chunks.c.source_id == payload.source_id)
        if payload.source_chunk_id:
            chunk_stmt = chunk_stmt.where(db.source_chunks.c.id == payload.source_chunk_id)
        for row in conn.execute(chunk_stmt).mappings():
            if allowed_sources is not None and row["source_id"] not in allowed_sources:
                continue
            value_score = score(row["text"])
            if value_score > 0:
                matches.append({"id": row["id"], "kind": "chunk", "node_id": None, "source_id": row["source_id"], "source_chunk_id": row["id"], "score": value_score})
        return sorted(matches, key=lambda item: (-item["score"], item["kind"], item["id"]))[:24]
