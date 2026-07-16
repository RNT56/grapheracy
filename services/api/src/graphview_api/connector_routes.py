from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission
from graphview_api.connector_service import ConnectorService
from graphview_api.schemas import (
    ConnectorAccountCreate,
    ConnectorAccountOut,
    ConnectorCredentialUpdate,
    ConnectorSyncCreate,
    ConnectorSyncRunOut,
    ConnectorTargetCreate,
    ConnectorTargetOut,
    ConnectorTargetUpdate,
)


def create_connector_router(service_provider: Callable[[], ConnectorService]) -> APIRouter:
    router = APIRouter()

    @router.get("/connectors")
    async def connectors(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict[str, list[dict[str, object]]]:
        return service.descriptors()

    @router.get("/connector-accounts")
    async def connector_accounts(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict[str, list[ConnectorAccountOut]]:
        return service.accounts()

    @router.post("/connector-accounts", response_model=ConnectorAccountOut, status_code=status.HTTP_201_CREATED)
    async def create_connector_account(
        payload: ConnectorAccountCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict:
        return service.create_account(payload, actor_id=user.id)

    @router.patch("/connector-accounts/{account_id}/credentials", response_model=ConnectorAccountOut)
    async def update_connector_account_credentials(
        account_id: str,
        payload: ConnectorCredentialUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict:
        try:
            return service.update_credentials(account_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @router.delete("/connector-accounts/{account_id}/credentials", response_model=ConnectorAccountOut)
    async def delete_connector_account_credentials(
        account_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict:
        try:
            return service.delete_credentials(account_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @router.get("/connector-targets")
    async def connector_targets(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict[str, list[ConnectorTargetOut]]:
        return service.targets()

    @router.post("/connector-targets", response_model=ConnectorTargetOut, status_code=status.HTTP_201_CREATED)
    async def create_connector_target(
        payload: ConnectorTargetCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict:
        try:
            return service.create_target(payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @router.patch("/connector-targets/{target_id}", response_model=ConnectorTargetOut)
    async def update_connector_target(
        target_id: str,
        payload: ConnectorTargetUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict:
        try:
            return service.update_target(target_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found") from error

    @router.get("/connector-sync-runs")
    async def connector_sync_runs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict[str, list[ConnectorSyncRunOut]]:
        return service.sync_runs()

    @router.get("/connector-sync-runs/{sync_run_id}", response_model=ConnectorSyncRunOut)
    async def connector_sync_run(
        sync_run_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict:
        try:
            return service.sync_run(sync_run_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector sync run not found") from error

    @router.post("/connector-sync-runs", status_code=status.HTTP_201_CREATED)
    async def create_connector_sync_run(
        payload: ConnectorSyncCreate,
        response: Response,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: ConnectorService = Depends(service_provider),
    ) -> dict:
        try:
            accepted, result = await service.create_sync(payload, actor_id=user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found") from error
        if accepted:
            response.status_code = status.HTTP_202_ACCEPTED
        return result

    return router
