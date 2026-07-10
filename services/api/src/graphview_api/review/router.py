from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.lenses import normalize_graph_lens
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    ProposalCreate,
    ProposalOut,
    ReviewActivityOut,
    ReviewDashboardOut,
    ReviewDecisionCreate,
    ReviewDecisionOut,
    ReviewQueueOut,
    SourceReviewCoverageOut,
)


def create_review_router(repo_provider: Callable[[], GraphRepository]) -> APIRouter:
    router = APIRouter()

    @router.get("/proposals")
    async def proposals(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ProposalOut]]:
        return {"proposals": repository.list_proposals(graph_id, lens=normalize_graph_lens(lens))}

    @router.get("/review-queue", response_model=ReviewQueueOut)
    async def review_queue(
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        return repository.review_queue(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    @router.get("/review-dashboard", response_model=ReviewDashboardOut)
    async def review_dashboard(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        return repository.review_dashboard(graph_id, normalize_graph_lens(lens))

    @router.get("/review-activity", response_model=ReviewActivityOut)
    async def review_activity(
        limit: int = Query(default=10, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        return repository.review_activity(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    @router.get("/review-sources", response_model=SourceReviewCoverageOut)
    async def review_sources(
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, object]:
        return repository.source_review_coverage(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    @router.post("/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
    async def create_proposal(
        payload: ProposalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.create_proposal(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error

    @router.get("/review-decisions")
    async def review_decisions(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ReviewDecisionOut]]:
        return {"review_decisions": repository.list_review_decisions(graph_id)}

    @router.post("/review-decisions", response_model=ReviewDecisionOut, status_code=status.HTTP_201_CREATED)
    async def create_review_decision(
        payload: ReviewDecisionCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.review(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    return router
