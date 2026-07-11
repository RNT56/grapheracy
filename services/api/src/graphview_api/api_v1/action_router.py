from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from graphview_api.api_v1.action_service import V1ActionService
from graphview_api.auth import OPERATE_PERMISSION, CurrentUser, ensure_project_access, require_permission
from graphview_api.jobs.schemas import JobOut
from graphview_api.schemas import OutcomeCreate


def create_v1_action_router(service_provider) -> APIRouter:
    router = APIRouter()

    @router.post("/action-proposals/{action_proposal_id}/run", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_action_run(
        action_proposal_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        action_service: V1ActionService = Depends(service_provider),
    ):
        proposal = action_service.proposal(action_proposal_id)
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        ensure_project_access(user, proposal["project_id"])
        if proposal["status"] != "approved":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action proposal must be approved")
        return action_service.enqueue_run(proposal, actor_id=user.id)

    @router.post("/action-runs/{action_run_id}/callback", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def action_outcome_callback(
        action_run_id: str,
        request: Request,
        x_graphview_event_id: str | None = Header(default=None, alias="X-Graphview-Event-Id"),
        x_graphview_timestamp: str | None = Header(default=None, alias="X-Graphview-Timestamp"),
        x_graphview_signature: str | None = Header(default=None, alias="X-Graphview-Signature"),
        action_service: V1ActionService = Depends(service_provider),
    ):
        body = await request.body()
        if not body or len(body) > 1_048_576:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Invalid outcome callback size")
        action_run = action_service.action_run(action_run_id)
        if action_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action run not found")
        try:
            callback_secret = action_service.callback_secret(action_run)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if not callback_secret:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action callback secret is not configured")
        if not x_graphview_event_id or len(x_graphview_event_id) > 200:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Outcome callback event ID is required")
        try:
            signed_at = int(x_graphview_timestamp or "")
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid outcome callback timestamp") from error
        if abs(int(time.time()) - signed_at) > 300:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired outcome callback timestamp")
        expected = "v1=" + hmac.new(callback_secret.encode(), f"{signed_at}.".encode() + body, hashlib.sha256).hexdigest()
        if not x_graphview_signature or not hmac.compare_digest(expected, x_graphview_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid outcome callback signature")
        try:
            outcome = OutcomeCreate.model_validate_json(body)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid outcome callback") from error
        return action_service.enqueue_outcome(action_run, action_run_id, x_graphview_event_id, outcome)

    return router
