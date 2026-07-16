from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission
from graphview_api.graph.service import GraphService
from graphview_api.observability import observe_sse_stream
from graphview_api.schemas import (
    ExtractionLensOut,
    GraphActivityOut,
    GraphInsightsOut,
    GraphLensOut,
    GraphNeighborhoodOut,
    GraphOut,
    GraphPathOut,
    GraphSettingsOut,
    GraphSettingsUpdate,
    GraphViewOut,
)


def create_graph_activity_router(
    service_provider: Callable[[], GraphService],
    *,
    telemetry,
) -> APIRouter:
    router = APIRouter()

    @router.get("/graph", response_model=GraphOut)
    async def graph(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.graph(graph_id=graph_id, lens=lens, user_id=user.id)

    @router.get("/graphs", response_model=list[GraphViewOut])
    async def graphs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> list[dict[str, object]]:
        return service.graphs()

    @router.get("/graph/activity", response_model=GraphActivityOut)
    async def graph_activity(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        limit: int = Query(default=50, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.activity(
            graph_id=graph_id,
            lens=lens,
            limit=limit,
            since=since,
        )

    @router.get("/agent-runs/{agent_run_id}/activity", response_model=GraphActivityOut)
    async def agent_run_activity(
        agent_run_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.agent_run_activity(agent_run_id=agent_run_id, limit=limit, since=since)

    @router.get(
        "/graph/activity/stream",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    )
    async def graph_activity_stream(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        limit: int = Query(default=25, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> StreamingResponse:
        events = service.activity_events(
            graph_id=graph_id,
            lens=lens,
            limit=limit,
            since=since,
        )

        async def event_stream():
            yield ": heartbeat\n\n"
            for event in events:
                yield f"id: {event['id']}\n"
                yield "event: graph.activity\n"
                yield f"data: {json.dumps(event, sort_keys=True, default=str)}\n\n"

        return StreamingResponse(
            observe_sse_stream(event_stream(), telemetry, stream_kind="graph.activity.compatibility"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return router


def create_graph_exploration_router(service_provider: Callable[[], GraphService]) -> APIRouter:
    router = APIRouter()

    @router.get("/insights", response_model=GraphInsightsOut)
    async def insights(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.insights(graph_id=graph_id, lens=lens)

    @router.get("/graph/neighborhood/{node_id}", response_model=GraphNeighborhoodOut)
    async def graph_neighborhood(
        node_id: str,
        depth: int = Query(default=1, ge=1, le=2),
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, object]:
        try:
            return service.neighborhood(
                node_id=node_id,
                depth=depth,
                limit=limit,
                graph_id=graph_id,
                lens=lens,
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found") from error

    @router.get("/graph/path", response_model=GraphPathOut)
    async def graph_path(
        source_node_id: str = Query(min_length=1),
        target_node_id: str = Query(min_length=1),
        max_depth: int = Query(default=4, ge=1, le=6),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, object]:
        try:
            return service.path(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                max_depth=max_depth,
                graph_id=graph_id,
                lens=lens,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source or target node not found",
            ) from error

    @router.get("/extraction-lenses")
    async def extraction_lenses(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, list[ExtractionLensOut]]:
        return service.extraction_lenses()

    @router.get("/graph-lenses")
    async def graph_lenses(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict[str, list[GraphLensOut]]:
        return service.graph_lenses()

    @router.get("/graph/settings", response_model=GraphSettingsOut)
    async def graph_settings(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict:
        return service.settings()

    @router.patch("/graph/settings", response_model=GraphSettingsOut)
    async def update_graph_settings(
        payload: GraphSettingsUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: GraphService = Depends(service_provider),
    ) -> dict:
        return service.update_settings(payload)

    return router
