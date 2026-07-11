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
