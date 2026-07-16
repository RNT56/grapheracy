from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.review.service import ReviewService
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


def create_review_router(service_provider: Callable[[], ReviewService]) -> APIRouter:
    router = APIRouter()

    @router.get("/proposals")
    async def proposals(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict[str, list[ProposalOut]]:
        return service.proposals(graph_id=graph_id, lens=lens)

    @router.get("/review-queue", response_model=ReviewQueueOut)
    async def review_queue(
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.queue(limit=limit, graph_id=graph_id, lens=lens)

    @router.get("/review-dashboard", response_model=ReviewDashboardOut)
    async def review_dashboard(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.dashboard(graph_id=graph_id, lens=lens)

    @router.get("/review-activity", response_model=ReviewActivityOut)
    async def review_activity(
        limit: int = Query(default=10, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.activity(limit=limit, graph_id=graph_id, lens=lens)

    @router.get("/review-sources", response_model=SourceReviewCoverageOut)
    async def review_sources(
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict[str, object]:
        return service.source_coverage(limit=limit, graph_id=graph_id, lens=lens)

    @router.post("/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
    async def create_proposal(
        payload: ProposalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict:
        try:
            return service.create_proposal(payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error

    @router.get("/review-decisions")
    async def review_decisions(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict[str, list[ReviewDecisionOut]]:
        return service.decisions(graph_id=graph_id)

    @router.post("/review-decisions", response_model=ReviewDecisionOut, status_code=status.HTTP_201_CREATED)
    async def create_review_decision(
        payload: ReviewDecisionCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: ReviewService = Depends(service_provider),
    ) -> dict:
        try:
            return service.decide(payload, reviewer_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    return router
