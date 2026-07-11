from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.jobs.schemas import JobOut
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
from graphview_api.sources.service import SourcesService


def create_sources_router(service_provider: Callable[[], SourcesService]) -> APIRouter:
    router = APIRouter()

    @router.get("/source-chunks")
    async def source_chunks(
        source_id: str | None = Query(default=None),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> dict[str, list[SourceChunkOut]]:
        return service.source_chunks(source_id=source_id, graph_id=graph_id)

    @router.get("/lineage/{entity_kind}/{entity_id}", response_model=LineageTraceOut)
    async def lineage(
        entity_kind: str,
        entity_id: str,
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> dict:
        try:
            return service.lineage(entity_kind=entity_kind, entity_id=entity_id, graph_id=graph_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineage entity not found") from error

    @router.get("/sources")
    async def sources(
        q: str | None = Query(default=None),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> dict[str, list[SourceOut]]:
        return service.sources(query=q, graph_id=graph_id)

    @router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
    async def create_source(
        payload: SourceCreate,
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> dict:
        return service.create_source(payload, graph_id=graph_id)

    @router.patch("/sources/{source_id}", response_model=SourceOut)
    async def update_source(
        source_id: str,
        payload: SourceUpdate,
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> dict:
        try:
            return service.update_source(source_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error

    @router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_source(
        source_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> None:
        try:
            service.delete_source(source_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error

    @router.get("/ingestion-runs")
    async def ingestion_runs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> dict[str, list[IngestionRunOut]]:
        return service.ingestion_runs()

    @router.post("/ingestion-runs", response_model=IngestionResultOut | JobOut, status_code=status.HTTP_201_CREATED)
    async def create_ingestion_run(
        payload: IngestionCreate,
        response: Response,
        graph_id: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: SourcesService = Depends(service_provider),
    ) -> dict:
        try:
            accepted, result = await service.create_ingestion(payload, actor_id=user.id, graph_id=graph_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        if accepted:
            response.status_code = status.HTTP_202_ACCEPTED
        return result

    return router
