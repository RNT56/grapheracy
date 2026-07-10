from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    AlertAssign,
    AlertOut,
    AttentionOut,
    AttentionTransition,
    ObservationCreate,
    ObservationOut,
    OwnerCreate,
    OwnerOut,
    OwnerUpdate,
    RoutingPolicyCreate,
    RoutingPolicyOut,
    RoutingPolicyUpdate,
    SignalCreate,
    SignalOut,
)


def create_attention_router(repo_provider: Callable[[], GraphRepository]) -> APIRouter:
    router = APIRouter()

    @router.get("/signals")
    async def signals(
        kind: str | None = Query(default=None),
        status: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[SignalOut]]:
        return {"signals": repository.list_signals(kind=kind, status=status, limit=limit)}

    @router.get("/signals/{signal_id}", response_model=SignalOut)
    async def signal(
        signal_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        item = repository.get_signal(signal_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
        return item

    @router.post("/signals", response_model=SignalOut, status_code=status.HTTP_201_CREATED)
    async def create_signal(
        payload: SignalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_signal(payload, user.id)

    @router.get("/observations")
    async def observations(
        signal_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ObservationOut]]:
        return {"observations": repository.list_observations(signal_id=signal_id, limit=limit)}

    @router.post("/observations", response_model=ObservationOut, status_code=status.HTTP_201_CREATED)
    async def create_observation(
        payload: ObservationCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_observation(payload, user.id)

    @router.get("/alerts")
    async def alerts(
        status_filter: str | None = Query(default=None, alias="status"),
        severity: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[AlertOut]]:
        return {"alerts": repository.list_alerts(status=status_filter, severity=severity, limit=limit)}

    @router.post("/alerts/{alert_id}/assign", response_model=AlertOut)
    async def assign_alert(
        alert_id: str,
        payload: AlertAssign,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        item = repository.assign_alert(alert_id, payload, user.id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return item

    @router.get("/attention", response_model=AttentionOut)
    async def attention(
        status_filter: str | None = Query(default=None, alias="status"),
        severity: str | None = Query(default=None),
        owner_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.list_attention(status=status_filter, severity=severity, owner_id=owner_id, limit=limit)

    @router.post("/attention/{attention_item_id}/transition", response_model=AttentionOut)
    async def transition_attention(
        attention_item_id: str,
        payload: AttentionTransition,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        item = repository.transition_attention(attention_item_id, payload, user.id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attention item not found")
        return {"generated_at": datetime.now(timezone.utc), "returned_count": 1, "items": [item]}

    @router.get("/owners")
    async def owners(
        scope_kind: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[OwnerOut]]:
        return {"owners": repository.list_owners(scope_kind=scope_kind, limit=limit)}

    @router.post("/owners", response_model=OwnerOut, status_code=status.HTTP_201_CREATED)
    async def create_owner(
        payload: OwnerCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_owner(payload)

    @router.patch("/owners/{owner_id}", response_model=OwnerOut)
    async def update_owner(
        owner_id: str,
        payload: OwnerUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        owner = repository.update_owner(owner_id, payload)
        if owner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
        return owner

    @router.get("/routing-policies")
    async def routing_policies(
        enabled: bool | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[RoutingPolicyOut]]:
        return {"routing_policies": repository.list_routing_policies(enabled=enabled, limit=limit)}

    @router.post("/routing-policies", response_model=RoutingPolicyOut, status_code=status.HTTP_201_CREATED)
    async def create_routing_policy(
        payload: RoutingPolicyCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_routing_policy(payload)

    @router.patch("/routing-policies/{policy_id}", response_model=RoutingPolicyOut)
    async def update_routing_policy(
        policy_id: str,
        payload: RoutingPolicyUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        policy = repository.update_routing_policy(policy_id, payload)
        if policy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing policy not found")
        return policy

    return router
