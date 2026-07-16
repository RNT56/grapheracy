from __future__ import annotations

import hashlib
import json

from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.schemas import IngestionCreate, SourceCreate, SourceUpdate
from graphview_api.settings import Settings
from graphview_api.sources.repository import SourcesRepositoryPort


class SourcesService:
    def __init__(self, repository: SourcesRepositoryPort, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def source_chunks(self, *, source_id: str | None, graph_id: str | None) -> dict[str, list[dict]]:
        return {"source_chunks": self.repository.list_source_chunks(source_id, graph_id)}

    def lineage(self, *, entity_kind: str, entity_id: str, graph_id: str | None) -> dict:
        if entity_kind not in {"source", "proposal", "node", "edge"}:
            raise KeyError((entity_kind, entity_id))
        trace = self.repository.lineage(entity_kind, entity_id, graph_id)
        if trace is None:
            raise KeyError((entity_kind, entity_id))
        return trace

    def sources(self, *, query: str | None, graph_id: str | None) -> dict[str, list[dict]]:
        return {"sources": self.repository.list_sources(query, graph_id)}

    def create_source(self, payload: SourceCreate, *, graph_id: str | None) -> dict:
        return self.repository.create_source(payload, graph_id)

    def update_source(self, source_id: str, payload: SourceUpdate) -> dict:
        source = self.repository.update_source(source_id, payload)
        if source is None:
            raise KeyError(source_id)
        return source

    def delete_source(self, source_id: str) -> None:
        if not self.repository.delete_source(source_id):
            raise KeyError(source_id)

    def ingestion_runs(self) -> dict[str, list[dict]]:
        return {"ingestion_runs": self.repository.list_ingestion_runs()}

    async def create_ingestion(
        self,
        payload: IngestionCreate,
        *,
        actor_id: str,
        graph_id: str | None,
    ) -> tuple[bool, dict]:
        if self.settings.environment in {"local", "test", "development"}:
            result = await GraphJobExecutor(self.repository, self.settings).ingestion(
                payload,
                actor_id=actor_id,
                graph_id=graph_id,
            )
            return False, result
        project_id = (graph_id or "project-default").split(":", 1)[0]
        serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        job = JobRepository(self.repository.engine).enqueue(
            JobCreate(
                kind="ingestion.run",
                queue="ingestion",
                idempotency_key=f"ingestion:{project_id}:{hashlib.sha256(serialized.encode()).hexdigest()}",
                payload={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "actor_id": actor_id,
                    "ingestion": payload.model_dump(mode="json"),
                },
            ),
            project_id=project_id,
        )
        return True, job
