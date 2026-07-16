from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.actions.service import ActionsService
from graphview_api.schemas import (
    ActionCredentialKind,
    ActionCredentialOut,
    ActionCredentialUpdate,
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


def create_actions_router(service_provider: Callable[[], ActionsService]) -> APIRouter:
    router = APIRouter()

    @router.get("/action-credentials")
    async def action_credentials(
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict[str, list[ActionCredentialOut]]:
        return service.credentials()

    @router.put("/action-credentials/{credential_kind}", response_model=ActionCredentialOut)
    async def update_action_credential(
        credential_kind: ActionCredentialKind,
        payload: ActionCredentialUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> ActionCredentialOut:
        try:
            return service.update_credential(credential_kind, payload.credentials)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    @router.delete("/action-credentials/{credential_kind}", response_model=ActionCredentialOut)
    async def delete_action_credential(
        credential_kind: ActionCredentialKind,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> ActionCredentialOut:
        return service.delete_credential(credential_kind)

    @router.get("/decision-records")
    async def decision_records(
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict[str, list[DecisionRecordOut]]:
        return service.decisions(limit=limit)

    @router.post("/decision-records", response_model=DecisionRecordOut, status_code=status.HTTP_201_CREATED)
    async def create_decision_record(
        payload: DecisionRecordCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict:
        return service.create_decision(payload, actor_id=user.id)

    @router.get("/action-proposals")
    async def action_proposals(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict[str, list[ActionProposalOut]]:
        return service.proposals(status_filter=status_filter, limit=limit)

    @router.post("/action-proposals", response_model=ActionProposalOut, status_code=status.HTTP_201_CREATED)
    async def create_action_proposal(
        payload: ActionProposalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict:
        try:
            return service.create_proposal(payload, actor_id=user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    @router.post("/action-proposals/{action_proposal_id}/approve", response_model=ActionProposalOut)
    async def approve_action_proposal(
        action_proposal_id: str,
        payload: ActionProposalDecision,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict:
        try:
            return service.decide_proposal(
                action_proposal_id,
                "approved",
                payload,
                actor_id=user.id,
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found") from error

    @router.post("/action-proposals/{action_proposal_id}/reject", response_model=ActionProposalOut)
    async def reject_action_proposal(
        action_proposal_id: str,
        payload: ActionProposalDecision,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict:
        try:
            return service.decide_proposal(
                action_proposal_id,
                "rejected",
                payload,
                actor_id=user.id,
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found") from error

    @router.get("/action-runs")
    async def action_runs(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict[str, list[ActionRunOut]]:
        return service.runs(status_filter=status_filter, limit=limit)

    @router.post("/action-runs", response_model=ActionRunOut, status_code=status.HTTP_201_CREATED)
    async def create_action_run(
        payload: ActionRunCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict:
        try:
            return service.create_run(payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @router.get("/outcomes")
    async def outcomes(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict[str, list[OutcomeOut]]:
        return service.outcomes(status_filter=status_filter, limit=limit)

    @router.post("/action-runs/{action_run_id}/outcome", response_model=OutcomeOut, status_code=status.HTTP_201_CREATED)
    async def create_action_run_outcome(
        action_run_id: str,
        payload: OutcomeCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict:
        try:
            return service.create_outcome(action_run_id, payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action run not found") from error

    @router.post("/feedback-events", response_model=FeedbackEventOut, status_code=status.HTTP_201_CREATED)
    async def create_feedback_event(
        payload: FeedbackEventCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict:
        return service.create_feedback(payload, actor_id=user.id)

    @router.get("/feedback-events")
    async def feedback_events(
        kind: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ActionsService = Depends(service_provider),
    ) -> dict[str, list[FeedbackEventOut]]:
        return service.feedback(kind=kind, limit=limit)

    return router
