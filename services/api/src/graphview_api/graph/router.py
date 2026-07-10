from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission
from graphview_api.lenses import EXTRACTION_LENS_DESCRIPTORS, GRAPH_LENS_DESCRIPTORS, normalize_graph_lens
from graphview_api.observability import observe_sse_stream
from graphview_api.repository import GraphRepository
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


def _activity_event_matches_agent_run(event: dict[str, object], agent_run_id: str) -> bool:
    payload = event.get("payload")
    if isinstance(payload, dict) and payload.get("agent_run_id") == agent_run_id:
        return True
    refs = event.get("object_refs")
    if not isinstance(refs, list):
        return False
    return any(
        isinstance(ref, dict) and ref.get("kind") == "agent_run" and ref.get("id") == agent_run_id
        for ref in refs
    )


def create_graph_activity_router(
    repo_provider: Callable[[], GraphRepository],
    *,
    telemetry,
) -> APIRouter:
    router = APIRouter()

    @router.get("/graph", response_model=GraphOut)
    async def graph(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        project, nodes, edges = repository.graph(graph_id, normalize_graph_lens(lens))
        return {"project": project, "nodes": nodes, "edges": edges, "user": user.id}

    @router.get("/graphs", response_model=list[GraphViewOut])
    async def graphs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> list[dict[str, object]]:
        return repository.list_graph_views()

    @router.get("/graph/activity", response_model=GraphActivityOut)
    async def graph_activity(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        limit: int = Query(default=50, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        events = repository.list_graph_activity_events(
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
            limit=limit,
            since=since,
        )
        return {"generated_at": datetime.now(timezone.utc), "returned_count": len(events), "events": events}

    @router.get("/agent-runs/{agent_run_id}/activity", response_model=GraphActivityOut)
    async def agent_run_activity(
        agent_run_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        events = [
            event
            for event in repository.list_graph_activity_events(limit=100, since=since)
            if _activity_event_matches_agent_run(event, agent_run_id)
        ][:limit]
        return {"generated_at": datetime.now(timezone.utc), "returned_count": len(events), "events": events}

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
        repository: GraphRepository = Depends(repo_provider),
    ) -> StreamingResponse:
        events = repository.list_graph_activity_events(
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
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


def create_graph_exploration_router(repo_provider: Callable[[], GraphRepository]) -> APIRouter:
    router = APIRouter()

    @router.get("/insights", response_model=GraphInsightsOut)
    async def insights(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        return repository.insights(graph_id, normalize_graph_lens(lens))

    @router.get("/graph/neighborhood/{node_id}", response_model=GraphNeighborhoodOut)
    async def graph_neighborhood(
        node_id: str,
        depth: int = Query(default=1, ge=1, le=2),
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        neighborhood = repository.neighborhood(
            node_id,
            depth=depth,
            limit=limit,
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
        )
        if neighborhood is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        return neighborhood

    @router.get("/graph/path", response_model=GraphPathOut)
    async def graph_path(
        source_node_id: str = Query(min_length=1),
        target_node_id: str = Query(min_length=1),
        max_depth: int = Query(default=4, ge=1, le=6),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        path = repository.path(
            source_node_id,
            target_node_id,
            max_depth=max_depth,
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
        )
        if path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source or target node not found")
        return path

    @router.get("/extraction-lenses")
    async def extraction_lenses(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
    ) -> dict[str, list[ExtractionLensOut]]:
        return {"extraction_lenses": EXTRACTION_LENS_DESCRIPTORS}

    @router.get("/graph-lenses")
    async def graph_lenses(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
    ) -> dict[str, list[GraphLensOut]]:
        return {"graph_lenses": GRAPH_LENS_DESCRIPTORS}

    @router.get("/graph/settings", response_model=GraphSettingsOut)
    async def graph_settings(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.graph_settings()

    @router.patch("/graph/settings", response_model=GraphSettingsOut)
    async def update_graph_settings(
        payload: GraphSettingsUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.update_graph_settings(payload)

    return router
