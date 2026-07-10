from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate, JobOut
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    IngestionCreate,
    IngestionResultOut,
    IngestionRunOut,
    LineageTraceOut,
    SourceChunkOut,
    SourceCreate,
    SourceOut,
    SourceUpdate,
)
from graphview_api.settings import Settings, get_settings


def create_sources_router(repo_provider: Callable[[], GraphRepository]) -> APIRouter:
    router = APIRouter()

    @router.get("/source-chunks")
    async def source_chunks(
        source_id: str | None = Query(default=None),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[SourceChunkOut]]:
        return {"source_chunks": repository.list_source_chunks(source_id, graph_id)}

    @router.get("/lineage/{entity_kind}/{entity_id}", response_model=LineageTraceOut)
    async def lineage(
        entity_kind: str,
        entity_id: str,
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        if entity_kind not in {"source", "proposal", "node", "edge"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineage entity not found")
        trace = repository.lineage(entity_kind, entity_id, graph_id)
        if trace is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineage entity not found")
        return trace

    @router.get("/sources")
    async def sources(
        q: str | None = Query(default=None),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[SourceOut]]:
        return {"sources": repository.list_sources(q, graph_id)}

    @router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
    async def create_source(
        payload: SourceCreate,
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_source(payload, graph_id)

    @router.patch("/sources/{source_id}", response_model=SourceOut)
    async def update_source(
        source_id: str,
        payload: SourceUpdate,
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        source = repository.update_source(source_id, payload)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return source

    @router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_source(
        source_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> None:
        if not repository.delete_source(source_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    @router.get("/ingestion-runs")
    async def ingestion_runs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[IngestionRunOut]]:
        return {"ingestion_runs": repository.list_ingestion_runs()}

    @router.post("/ingestion-runs", response_model=IngestionResultOut | JobOut, status_code=status.HTTP_201_CREATED)
    async def create_ingestion_run(
        payload: IngestionCreate,
        response: Response,
        graph_id: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if settings.environment in {"local", "test", "development"}:
            try:
                return await GraphJobExecutor(repository, settings).ingestion(payload, actor_id=user.id, graph_id=graph_id)
            except ValueError as error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        project_id = (graph_id or "project-default").split(":", 1)[0]
        response.status_code = status.HTTP_202_ACCEPTED
        serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="ingestion.run",
                queue="ingestion",
                idempotency_key=f"ingestion:{project_id}:{hashlib.sha256(serialized.encode()).hexdigest()}",
                payload={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "actor_id": user.id,
                    "ingestion": payload.model_dump(mode="json"),
                },
            ),
            project_id=project_id,
        )

    return router
