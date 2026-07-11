from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, REVIEW_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.attention.service import AttentionService
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


def create_attention_router(service_provider: Callable[[], AttentionService]) -> APIRouter:
    router = APIRouter()

    @router.get("/signals")
    async def signals(
        kind: str | None = Query(default=None),
        status: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict[str, list[SignalOut]]:
        return service.signals(kind=kind, status=status, limit=limit)

    @router.get("/signals/{signal_id}", response_model=SignalOut)
    async def signal(
        signal_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        try:
            return service.signal(signal_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found") from error

    @router.post("/signals", response_model=SignalOut, status_code=status.HTTP_201_CREATED)
    async def create_signal(
        payload: SignalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        return service.create_signal(payload, actor_id=user.id)

    @router.get("/observations")
    async def observations(
        signal_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict[str, list[ObservationOut]]:
        return service.observations(signal_id=signal_id, limit=limit)

    @router.post("/observations", response_model=ObservationOut, status_code=status.HTTP_201_CREATED)
    async def create_observation(
        payload: ObservationCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        return service.create_observation(payload, actor_id=user.id)

    @router.get("/alerts")
    async def alerts(
        status_filter: str | None = Query(default=None, alias="status"),
        severity: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict[str, list[AlertOut]]:
        return service.alerts(status_filter=status_filter, severity=severity, limit=limit)

    @router.post("/alerts/{alert_id}/assign", response_model=AlertOut)
    async def assign_alert(
        alert_id: str,
        payload: AlertAssign,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        try:
            return service.assign_alert(alert_id, payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found") from error

    @router.get("/attention", response_model=AttentionOut)
    async def attention(
        status_filter: str | None = Query(default=None, alias="status"),
        severity: str | None = Query(default=None),
        owner_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        return service.attention(status_filter=status_filter, severity=severity, owner_id=owner_id, limit=limit)

    @router.post("/attention/{attention_item_id}/transition", response_model=AttentionOut)
    async def transition_attention(
        attention_item_id: str,
        payload: AttentionTransition,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        try:
            return service.transition(attention_item_id, payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attention item not found") from error

    @router.get("/owners")
    async def owners(
        scope_kind: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict[str, list[OwnerOut]]:
        return service.owners(scope_kind=scope_kind, limit=limit)

    @router.post("/owners", response_model=OwnerOut, status_code=status.HTTP_201_CREATED)
    async def create_owner(
        payload: OwnerCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        return service.create_owner(payload)

    @router.patch("/owners/{owner_id}", response_model=OwnerOut)
    async def update_owner(
        owner_id: str,
        payload: OwnerUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        try:
            return service.update_owner(owner_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found") from error

    @router.get("/routing-policies")
    async def routing_policies(
        enabled: bool | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict[str, list[RoutingPolicyOut]]:
        return service.policies(enabled=enabled, limit=limit)

    @router.post("/routing-policies", response_model=RoutingPolicyOut, status_code=status.HTTP_201_CREATED)
    async def create_routing_policy(
        payload: RoutingPolicyCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        return service.create_policy(payload)

    @router.patch("/routing-policies/{policy_id}", response_model=RoutingPolicyOut)
    async def update_routing_policy(
        policy_id: str,
        payload: RoutingPolicyUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: AttentionService = Depends(service_provider),
    ) -> dict:
        try:
            return service.update_policy(policy_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing policy not found") from error

    return router
