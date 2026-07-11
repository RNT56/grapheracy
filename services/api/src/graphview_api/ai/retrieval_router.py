from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.ai.retrieval_service import RetrievalService
from graphview_api.auth import READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.schemas import (
    AgentActionApprovalCreate,
    AgentActionProposalOut,
    GraphQueryAnswerOut,
    GraphQueryCreate,
    GraphResearchCreate,
    GraphResearchOut,
)


def create_retrieval_router(service_provider: Callable[[], RetrievalService]) -> APIRouter:
    router = APIRouter()

    @router.post("/agent-runs/{agent_run_id}/approve-action", response_model=AgentActionProposalOut)
    async def approve_agent_action(
        agent_run_id: str,
        payload: AgentActionApprovalCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: RetrievalService = Depends(service_provider),
    ) -> dict:
        try:
            return service.approve_action(agent_run_id, payload, reviewer_id=user.id)
        except KeyError as error:
            detail = "Agent run not found" if error.args == ("agent_run",) else "Action proposal not found"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from error

    @router.post("/graph/query", response_model=GraphQueryAnswerOut)
    async def graph_query(
        payload: GraphQueryCreate,
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: RetrievalService = Depends(service_provider),
    ) -> dict:
        try:
            return await service.query(payload, graph_id=graph_id, lens=lens, actor_id=user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    @router.post("/graph/research", response_model=GraphResearchOut, status_code=status.HTTP_201_CREATED)
    async def graph_research(
        payload: GraphResearchCreate,
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: RetrievalService = Depends(service_provider),
    ) -> dict:
        try:
            return await service.research(payload, graph_id=graph_id, lens=lens, actor_id=user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return router
