from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission
from graphview_api.observability import observe_sse_stream
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    AgentContextBlobContentOut,
    AgentContextClientCreate,
    AgentContextClientCreateOut,
    AgentContextEventBatchCreate,
    AgentContextEventBatchOut,
    AgentContextEventOut,
    AgentContextGraphOut,
    AgentContextRetentionOut,
    AgentContextSessionCreate,
    AgentContextSessionOut,
    AgentContextSessionUpdate,
)


def create_agent_context_router(
    repo_provider: Callable[[], GraphRepository],
    *,
    telemetry,
) -> APIRouter:
    router = APIRouter(prefix="/agent-context", tags=["Agent context"])

    async def capture_client(
        request: Request,
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        authorization = request.headers.get("authorization") or ""
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent context bearer token required")
        client = repository.authenticate_agent_context_token(token.strip())
        if client is None or "context:capture" not in client.get("scopes", []):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent context token")
        return client

    @router.post("/clients", response_model=AgentContextClientCreateOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_context_client(
        payload: AgentContextClientCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_agent_context_client(payload, actor_id=user.id)

    @router.post("/sessions", response_model=AgentContextSessionOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_context_session(
        payload: AgentContextSessionCreate,
        client: dict = Depends(capture_client),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_agent_context_session(payload, client=client)

    @router.patch("/sessions/{session_id}", response_model=AgentContextSessionOut)
    async def update_agent_context_session(
        session_id: str,
        payload: AgentContextSessionUpdate,
        client: dict = Depends(capture_client),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.update_agent_context_session(session_id, payload, client=client)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context session not found") from error

    @router.post("/events/batch", response_model=AgentContextEventBatchOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_context_event_batch(
        payload: AgentContextEventBatchCreate,
        client: dict = Depends(capture_client),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.ingest_agent_context_events(payload, client=client)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context session not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error

    @router.get("/sessions", response_model=dict[str, list[AgentContextSessionOut]])
    async def agent_context_sessions(
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[dict]]:
        return {"sessions": repository.list_agent_context_sessions(limit=limit)}

    @router.get("/sessions/{session_id}", response_model=AgentContextSessionOut)
    async def agent_context_session(
        session_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        item = repository.get_agent_context_session(session_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context session not found")
        return item

    @router.get("/sessions/{session_id}/events", response_model=dict[str, list[AgentContextEventOut]])
    async def agent_context_events(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=500),
        since_sequence: int | None = Query(default=None, ge=0),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[dict]]:
        if repository.get_agent_context_session(session_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context session not found")
        return {"events": repository.list_agent_context_events(session_id, limit=limit, since_sequence=since_sequence)}

    @router.get("/sessions/{session_id}/graph", response_model=AgentContextGraphOut)
    async def agent_context_graph(
        session_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.agent_context_graph(session_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context session not found") from error

    @router.get("/artifacts/{artifact_id}/content", response_model=AgentContextBlobContentOut)
    async def agent_context_artifact_content(
        artifact_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        content = repository.agent_context_artifact_content(artifact_id)
        if content is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context content not found")
        return content

    @router.get("/sessions/{session_id}/stream")
    async def agent_context_stream(
        session_id: str,
        limit: int = Query(default=25, ge=1, le=100),
        since_sequence: int | None = Query(default=None, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> StreamingResponse:
        if repository.get_agent_context_session(session_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context session not found")
        if last_event_id:
            replay_sequence = repository.agent_context_event_sequence(session_id, last_event_id)
            if replay_sequence is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent context replay cursor is no longer available")
            since_sequence = max(since_sequence or 0, replay_sequence)
        captured_events = repository.list_agent_context_events(
            session_id,
            limit=limit,
            since_sequence=since_sequence,
        )

        async def event_stream():
            yield ": heartbeat\n\n"
            for event in captured_events:
                yield f"id: {event['id']}\n"
                yield "event: agent-context.event\n"
                yield f"data: {json.dumps(event, default=str)}\n\n"

        return StreamingResponse(
            observe_sse_stream(event_stream(), telemetry, stream_kind="agent-context.compatibility"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/retention/run", response_model=AgentContextRetentionOut)
    async def run_agent_context_retention(
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.run_agent_context_retention()

    return router
