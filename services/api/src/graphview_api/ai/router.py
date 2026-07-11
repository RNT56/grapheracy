from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.ai.service import PlanningService
from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.schemas import (
    AgentRunCreate,
    AgentRunOut,
    GraphBuildSpecCreate,
    GraphBuildSpecOut,
    PlanningMessageCreate,
    PlanningSessionCreate,
    PlanningSessionOut,
    ProviderCredentialUpdate,
    ProviderDescriptorOut,
)


def create_planning_router(service_provider: Callable[[], PlanningService]) -> APIRouter:
    router = APIRouter()

    @router.get("/providers")
    async def providers(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        return service.providers()

    @router.patch("/providers/{provider_id}/credentials")
    async def update_provider_credentials(
        provider_id: str,
        payload: ProviderCredentialUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        try:
            return service.update_provider(provider_id, payload)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    @router.delete("/providers/{provider_id}/credentials")
    async def delete_provider_credentials(
        provider_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        try:
            return service.delete_provider(provider_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    @router.post("/planning-sessions", response_model=PlanningSessionOut, status_code=status.HTTP_201_CREATED)
    async def create_planning_session(
        payload: PlanningSessionCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict:
        return service.create_session(payload, actor_id=user.id)

    @router.get("/planning-sessions")
    async def planning_sessions(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict[str, list[PlanningSessionOut]]:
        return service.sessions(graph_id=graph_id)

    @router.get("/planning-sessions/{session_id}", response_model=PlanningSessionOut)
    async def planning_session(
        session_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict:
        try:
            return service.session(session_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found") from error

    @router.post("/planning-sessions/{session_id}/messages", response_model=PlanningSessionOut)
    async def create_planning_message(
        session_id: str,
        payload: PlanningMessageCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict:
        try:
            return await service.create_message(session_id, payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    @router.post("/planning-sessions/{session_id}/build-spec", response_model=GraphBuildSpecOut)
    async def create_graph_build_spec(
        session_id: str,
        payload: GraphBuildSpecCreate,
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict:
        try:
            return service.create_build_spec(session_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found") from error

    @router.post("/agent-runs", response_model=AgentRunOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_run(
        payload: AgentRunCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict:
        try:
            return await service.create_agent_run(payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    @router.get("/agent-runs/{agent_run_id}", response_model=AgentRunOut)
    async def agent_run(
        agent_run_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict:
        try:
            return service.agent_run(agent_run_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found") from error

    @router.get("/agent-tools")
    async def agent_tools(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: PlanningService = Depends(service_provider),
    ) -> dict[str, list[dict[str, object]]]:
        return service.tools()

    return router
