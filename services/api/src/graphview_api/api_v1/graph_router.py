from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from graphview_api.api_v1.schemas import GraphActivityPage, GraphBounds, GraphSearchOut, GraphSubgraphOut, GraphViewportOut
from graphview_api.api_v1.service import GraphProjectionService, event_envelope
from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, ensure_project_access, require_permission
from graphview_api.observability import observe_sse_stream
from graphview_api.schemas import GraphLayoutOut, GraphLayoutUpsert


def create_v1_graph_router(service_provider) -> APIRouter:
    router = APIRouter()

    @router.get("/graphs/{graph_id}/viewport", response_model=GraphViewportOut)
    async def graph_viewport(
        graph_id: str,
        response: Response,
        zoom: float = Query(default=0.75, ge=0, le=16),
        min_x: float = Query(default=-1),
        min_y: float = Query(default=-1),
        max_x: float = Query(default=1),
        max_y: float = Query(default=1),
        layout: str = Query(default="default", min_length=1, max_length=160),
        max_nodes: int = Query(default=2_000, ge=1, le=20_000),
        max_edges: int = Query(default=8_000, ge=1, le=50_000),
        if_none_match: str | None = Header(default=None),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        try:
            result = graph_service.viewport(
                graph_id,
                zoom=zoom,
                bounds=GraphBounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y),
                layout_name=layout,
                max_nodes=max_nodes,
                max_edges=max_edges,
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        response.headers["ETag"] = result["etag"]
        response.headers["Cache-Control"] = "private, no-cache"
        if if_none_match == result["etag"]:
            response.status_code = status.HTTP_304_NOT_MODIFIED
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))
        return result

    @router.get("/graphs/{graph_id}/subgraph", response_model=GraphSubgraphOut)
    async def graph_subgraph(
        graph_id: str,
        focus_node_id: str | None = Query(default=None),
        depth: int = Query(default=1, ge=1, le=2),
        max_nodes: int = Query(default=100, ge=1, le=2_000),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        result = graph_service.subgraph(graph_id, focus_node_id=focus_node_id, depth=depth, max_nodes=max_nodes)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Focus node not found")
        return result

    @router.get("/graphs/{graph_id}/search", response_model=GraphSearchOut)
    async def graph_search(
        graph_id: str,
        q: str = Query(min_length=1, max_length=500),
        limit: int = Query(default=25, ge=1, le=100),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        return graph_service.search(graph_id, q, limit=limit, actor_id=user.id)

    @router.get("/graphs/{graph_id}/layouts", response_model=list[GraphLayoutOut])
    async def list_layouts(
        graph_id: str,
        include_positions: bool = Query(default=False),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        return graph_service.list_layouts(graph_id, include_positions=include_positions)

    @router.put("/graphs/{graph_id}/layouts/{layout_name}", response_model=GraphLayoutOut)
    async def put_layout(
        graph_id: str,
        layout_name: str,
        payload: GraphLayoutUpsert,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        try:
            return graph_service.put_layout(graph_id, layout_name, payload, actor_id=user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @router.get("/graphs/{graph_id}/activity", response_model=GraphActivityPage)
    async def graph_activity_page(
        graph_id: str,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        return graph_service.activity_page(graph_id, cursor=cursor, limit=limit)

    @router.get("/graphs/{graph_id}/stream", response_class=StreamingResponse)
    async def graph_activity_stream(
        graph_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        limit: int = Query(default=100, ge=1, le=200),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])

        async def stream():
            cursor = last_event_id
            while not await request.is_disconnected():
                events = graph_service.activity_events(graph_id, cursor=cursor, limit=limit)
                if events:
                    for event in events:
                        envelope = event_envelope(event, graph_id)
                        cursor = envelope["id"]
                        yield f"id: {cursor}\nevent: {envelope['event_type']}\ndata: {json.dumps(envelope, sort_keys=True, default=str)}\n\n"
                else:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(10)

        return StreamingResponse(
            observe_sse_stream(stream(), request.app.state.telemetry, stream_kind="graph.activity"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return router
