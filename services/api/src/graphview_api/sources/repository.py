from __future__ import annotations

from typing import Protocol

from sqlalchemy import Engine

from graphview_api.schemas import SourceCreate, SourceUpdate


class SourcesRepositoryPort(Protocol):
    engine: Engine

    def list_source_chunks(self, source_id: str | None = None, graph_id: str | None = None) -> list[dict]: ...

    def lineage(self, entity_kind: str, entity_id: str, graph_id: str | None = None) -> dict | None: ...

    def list_sources(self, query: str | None = None, graph_id: str | None = None) -> list[dict]: ...

    def create_source(self, payload: SourceCreate, graph_id: str | None = None) -> dict: ...

    def update_source(self, source_id: str, payload: SourceUpdate) -> dict | None: ...

    def delete_source(self, source_id: str) -> bool: ...

    def list_ingestion_runs(self) -> list[dict]: ...
