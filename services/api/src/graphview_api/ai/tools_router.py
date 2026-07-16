from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, status

from graphview_api.ai.tools_service import AgentToolsService
from graphview_api.auth import WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.schemas import AgentToolCallCreate, AgentToolCallOut


def create_agent_tools_router(service_provider: Callable[[], AgentToolsService]) -> APIRouter:
    router = APIRouter()

    @router.post("/agent-tool-calls", response_model=AgentToolCallOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_tool_call(
        payload: AgentToolCallCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: AgentToolsService = Depends(service_provider),
    ) -> dict:
        return service.execute(payload, actor_id=user.id)

    return router
