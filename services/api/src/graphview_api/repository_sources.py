from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, delete, insert, or_, select, update

from graphview_api import db
from graphview_api.json_compat import normalize_json_row
from graphview_api.schemas import SourceCreate, SourceUpdate

DEFAULT_PROJECT_ID = "project-default"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


class SourceCatalogRepositoryMixin:
    """Project-scoped source catalog, chunk, and ingestion-run persistence."""

    def list_sources(self, query: str | None = None, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        statement = select(db.sources).where(db.sources.c.project_id == spec.project_id)
        if spec.source_ids:
            statement = statement.where(db.sources.c.id.in_(spec.source_ids))
        if query:
            like = f"%{query}%"
            statement = statement.where(or_(db.sources.c.title.like(like), db.sources.c.uri.like(like)))
        statement = statement.order_by(db.sources.c.created_at.desc())
        with self.engine.begin() as connection:
            return [self._source_from_row(row) for row in connection.execute(statement).mappings()]

    def create_source(self, payload: SourceCreate, graph_id: str | None = None) -> dict:
        spec = self._graph_view_spec(graph_id)
        timestamp = _now()
        source = {
            "id": _new_id("src"),
            "project_id": spec.project_id,
            **self._source_values_from_payload(payload),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as connection:
            connection.execute(insert(db.sources).values(**source))
            self._record_activity_event(
                connection,
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
        values["updated_at"] = _now()
        with self.engine.begin() as connection:
            result = connection.execute(
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
        with self.engine.begin() as connection:
            row = connection.execute(select(db.sources).where(and_(*conditions))).mappings().first()
            return self._source_from_row(row) if row else None

    def delete_source(self, source_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(db.sources).where(
                    and_(db.sources.c.id == source_id, db.sources.c.project_id == DEFAULT_PROJECT_ID)
                )
            )
            return result.rowcount > 0

    def list_source_chunks(self, source_id: str | None = None, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        statement = select(db.source_chunks).where(db.source_chunks.c.project_id == spec.project_id)
        if spec.source_ids:
            statement = statement.where(db.source_chunks.c.source_id.in_(spec.source_ids))
        if source_id:
            statement = statement.where(db.source_chunks.c.source_id == source_id)
        statement = statement.order_by(db.source_chunks.c.source_id, db.source_chunks.c.ordinal, db.source_chunks.c.id)
        with self.engine.begin() as connection:
            return [self._source_chunk_from_row(row) for row in connection.execute(statement).mappings()]

    def list_ingestion_runs(self) -> list[dict]:
        with self.engine.begin() as connection:
            return [
                normalize_json_row(row)
                for row in connection.execute(
                    select(db.ingestion_runs)
                    .where(db.ingestion_runs.c.project_id == DEFAULT_PROJECT_ID)
                    .order_by(db.ingestion_runs.c.started_at.desc())
                ).mappings()
            ]

    def lineage(self, entity_kind: str, entity_id: str, graph_id: str | None = None) -> dict | None:
        project_id = self._graph_view_spec(graph_id).project_id
        with self.engine.begin() as connection:
            if entity_kind == "source":
                return self._lineage_for_source(connection, entity_id, project_id)
            if entity_kind == "proposal":
                return self._lineage_for_proposal(connection, entity_id, project_id)
            if entity_kind == "node":
                return self._lineage_for_node(connection, entity_id, project_id)
            if entity_kind == "edge":
                return self._lineage_for_edge(connection, entity_id, project_id)
        return None

    def _lineage_for_source(self, connection, source_id: str, project_id: str) -> dict | None:
        source_row = connection.execute(
            select(db.sources).where(and_(db.sources.c.id == source_id, db.sources.c.project_id == project_id))
        ).mappings().first()
        if source_row is None:
            return None
        runs = [
            normalize_json_row(row)
            for row in connection.execute(
                select(db.ingestion_runs)
                .where(and_(db.ingestion_runs.c.source_id == source_id, db.ingestion_runs.c.project_id == project_id))
                .order_by(db.ingestion_runs.c.started_at.desc())
            ).mappings()
        ]
        proposals = self._proposals_for_run_ids(connection, [run["id"] for run in runs], project_id)
        return {
            "entity_kind": "source",
            "entity_id": source_id,
            "source": self._source_from_row(source_row),
            "ingestion_runs": runs,
            "proposals": proposals,
            "review_decisions": self._decisions_for_proposal_ids(
                connection,
                [proposal["id"] for proposal in proposals],
                project_id,
            ),
            "nodes": self._nodes_for_source(connection, source_id, project_id),
            "edges": self._edges_for_source(connection, source_id, project_id),
            "provenance": self._provenance_from_items(proposals),
        }

    def _lineage_for_proposal(self, connection, proposal_id: str, project_id: str) -> dict | None:
        proposal_row = connection.execute(
            select(db.extraction_proposals).where(
                and_(db.extraction_proposals.c.id == proposal_id, db.extraction_proposals.c.project_id == project_id)
            )
        ).mappings().first()
        if proposal_row is None:
            return None
        proposal = self._proposal_from_row(proposal_row)
        run = self._run_by_id(connection, proposal["ingestion_run_id"], project_id)
        source = self._source_by_id(connection, run["source_id"], project_id) if run else None
        return {
            "entity_kind": "proposal",
            "entity_id": proposal_id,
            "source": source,
            "ingestion_runs": [run] if run else [],
            "proposals": [proposal],
            "review_decisions": self._decisions_for_proposal_ids(connection, [proposal_id], project_id),
            "nodes": self._nodes_for_proposal(connection, proposal, project_id),
            "edges": self._edges_for_proposal(connection, proposal, project_id),
            "provenance": proposal["provenance"],
        }

    def _lineage_for_node(self, connection, node_id: str, project_id: str) -> dict | None:
        row = connection.execute(
            select(db.content_nodes).where(
                and_(db.content_nodes.c.id == node_id, db.content_nodes.c.project_id == project_id)
            )
        ).mappings().first()
        if row is None:
            return None
        node = self._node_from_row(row)
        provenance = node["provenance"]
        proposal = self._proposal_for_node(connection, node_id, project_id)
        proposals = [proposal] if proposal else []
        run = self._run_from_provenance(connection, provenance, project_id)
        source = self._source_from_provenance(connection, provenance, project_id)
        return {
            "entity_kind": "node",
            "entity_id": node_id,
            "source": source,
            "ingestion_runs": [run] if run else [],
            "proposals": proposals,
            "review_decisions": self._decisions_for_proposal_ids(
                connection,
                [item["id"] for item in proposals],
                project_id,
            ),
            "nodes": [node],
            "edges": self._edges_for_node(connection, node_id, project_id),
            "provenance": provenance,
        }

    def _lineage_for_edge(self, connection, edge_id: str, project_id: str) -> dict | None:
        row = connection.execute(
            select(db.semantic_edges).where(
                and_(db.semantic_edges.c.id == edge_id, db.semantic_edges.c.project_id == project_id)
            )
        ).mappings().first()
        if row is None:
            return None
        edge = self._edge_from_row(row)
        provenance = edge["provenance"]
        proposal = self._proposal_for_edge(connection, edge, project_id)
        proposals = [proposal] if proposal else []
        run = self._run_from_provenance(connection, provenance, project_id)
        source = self._source_from_provenance(connection, provenance, project_id)
        endpoint_nodes = [
            node
            for node_id in [edge["source_node_id"], edge["target_node_id"]]
            if (node := self._node_by_id(connection, node_id, project_id)) is not None
        ]
        return {
            "entity_kind": "edge",
            "entity_id": edge_id,
            "source": source,
            "ingestion_runs": [run] if run else [],
            "proposals": proposals,
            "review_decisions": self._decisions_for_proposal_ids(
                connection,
                [item["id"] for item in proposals],
                project_id,
            ),
            "nodes": endpoint_nodes,
            "edges": [edge],
            "provenance": provenance,
        }
