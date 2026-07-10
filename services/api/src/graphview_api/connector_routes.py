from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission
from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.connectors import connector_descriptors
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository
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
from graphview_api.settings import Settings, get_settings


def create_connector_router(
    repo_provider: Callable[[], GraphRepository],
    *,
    llm_provider_factory,
) -> APIRouter:
    router = APIRouter()

    @router.get("/connectors")
    async def connectors(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
    ) -> dict[str, list[dict[str, object]]]:
        return {"connectors": connector_descriptors()}

    @router.get("/connector-accounts")
    async def connector_accounts(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ConnectorAccountOut]]:
        return {"connector_accounts": repository.list_connector_accounts()}

    @router.post("/connector-accounts", response_model=ConnectorAccountOut, status_code=status.HTTP_201_CREATED)
    async def create_connector_account(
        payload: ConnectorAccountCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_connector_account(payload, user.id)

    @router.patch("/connector-accounts/{account_id}/credentials", response_model=ConnectorAccountOut)
    async def update_connector_account_credentials(
        account_id: str,
        payload: ConnectorCredentialUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.update_connector_account_tokens(
                account_id,
                payload.token_json,
                project_id="project-default",
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @router.delete("/connector-accounts/{account_id}/credentials", response_model=ConnectorAccountOut)
    async def delete_connector_account_credentials(
        account_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.clear_connector_account_tokens(account_id, project_id="project-default")
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @router.get("/connector-targets")
    async def connector_targets(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ConnectorTargetOut]]:
        return {"connector_targets": repository.list_connector_targets()}

    @router.post("/connector-targets", response_model=ConnectorTargetOut, status_code=status.HTTP_201_CREATED)
    async def create_connector_target(
        payload: ConnectorTargetCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.create_connector_target(payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @router.patch("/connector-targets/{target_id}", response_model=ConnectorTargetOut)
    async def update_connector_target(
        target_id: str,
        payload: ConnectorTargetUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        target = repository.update_connector_target(target_id, payload)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        return target

    @router.get("/connector-sync-runs")
    async def connector_sync_runs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[ConnectorSyncRunOut]]:
        return {"connector_sync_runs": repository.list_connector_sync_runs()}

    @router.get("/connector-sync-runs/{sync_run_id}", response_model=ConnectorSyncRunOut)
    async def connector_sync_run(
        sync_run_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        sync_run = repository.get_connector_sync_run(sync_run_id)
        if sync_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector sync run not found")
        return sync_run

    @router.post("/connector-sync-runs", status_code=status.HTTP_201_CREATED)
    async def create_connector_sync_run(
        payload: ConnectorSyncCreate,
        response: Response,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if settings.environment in {"local", "test", "development"}:
            try:
                return await GraphJobExecutor(
                    repository,
                    settings,
                    llm_provider_factory=llm_provider_factory,
                ).connector_sync(
                    payload.target_id,
                    actor_id=user.id,
                    worker_id="api-development-compatibility",
                    retry_attempt=1,
                )
            except KeyError as error:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found") from error
        bundle = repository.connector_target_bundle(payload.target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        _, target, _ = bundle
        response.status_code = status.HTTP_202_ACCEPTED
        ConnectorStateRepository(repository.engine).mark_queued(payload.target_id)
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"connector-sync:{payload.target_id}:{target.get('updated_at')}",
                payload={"project_id": target["project_id"], "target_id": payload.target_id, "actor_id": user.id},
            ),
            project_id=target["project_id"],
        )

    return router
