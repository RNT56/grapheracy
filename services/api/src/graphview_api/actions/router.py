from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    ActionProposalCreate,
    ActionProposalDecision,
    ActionProposalOut,
    ActionRunCreate,
    ActionRunOut,
    DecisionRecordCreate,
    DecisionRecordOut,
    FeedbackEventCreate,
    FeedbackEventOut,
    OutcomeCreate,
    OutcomeOut,
)


def create_actions_router(repo_provider: Callable[[], GraphRepository]) -> APIRouter:
    router = APIRouter()

    @router.get("/decision-records")
    async def decision_records(
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[DecisionRecordOut]]:
        return {"decision_records": repository.list_decision_records(limit=limit)}

    @router.post("/decision-records", response_model=DecisionRecordOut, status_code=status.HTTP_201_CREATED)
    async def create_decision_record(
        payload: DecisionRecordCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_decision_record(payload, user.id)

    @router.get("/action-proposals")
    async def action_proposals(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ActionProposalOut]]:
        return {"action_proposals": repository.list_action_proposals(status=status_filter, limit=limit)}

    @router.post("/action-proposals", response_model=ActionProposalOut, status_code=status.HTTP_201_CREATED)
    async def create_action_proposal(
        payload: ActionProposalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_action_proposal(payload, user.id)

    @router.post("/action-proposals/{action_proposal_id}/approve", response_model=ActionProposalOut)
    async def approve_action_proposal(
        action_proposal_id: str,
        payload: ActionProposalDecision,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            item = repository.decide_action_proposal(action_proposal_id, "approved", payload, user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        return item

    @router.post("/action-proposals/{action_proposal_id}/reject", response_model=ActionProposalOut)
    async def reject_action_proposal(
        action_proposal_id: str,
        payload: ActionProposalDecision,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            item = repository.decide_action_proposal(action_proposal_id, "rejected", payload, user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        return item

    @router.get("/action-runs")
    async def action_runs(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ActionRunOut]]:
        return {"action_runs": repository.list_action_runs(status=status_filter, limit=limit)}

    @router.post("/action-runs", response_model=ActionRunOut, status_code=status.HTTP_201_CREATED)
    async def create_action_run(
        payload: ActionRunCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.create_action_run(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @router.get("/outcomes")
    async def outcomes(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[OutcomeOut]]:
        return {"outcomes": repository.list_outcomes(status=status_filter, limit=limit)}

    @router.post("/action-runs/{action_run_id}/outcome", response_model=OutcomeOut, status_code=status.HTTP_201_CREATED)
    async def create_action_run_outcome(
        action_run_id: str,
        payload: OutcomeCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.create_outcome(payload, user.id, action_run_id=action_run_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action run not found") from error

    @router.post("/feedback-events", response_model=FeedbackEventOut, status_code=status.HTTP_201_CREATED)
    async def create_feedback_event(
        payload: FeedbackEventCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_feedback_event(payload, user.id)

    @router.get("/feedback-events")
    async def feedback_events(
        kind: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[FeedbackEventOut]]:
        return {"feedback_events": repository.list_feedback_events(kind=kind, limit=limit)}

    return router
