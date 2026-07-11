from __future__ import annotations

from graphview_api.connector_repository import ConnectorRepositoryPort
from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.connectors import connector_descriptors
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.schemas import (
    ConnectorAccountCreate,
    ConnectorCredentialUpdate,
    ConnectorSyncCreate,
    ConnectorTargetCreate,
    ConnectorTargetUpdate,
)
from graphview_api.settings import Settings


class ConnectorService:
    def __init__(
        self,
        repository: ConnectorRepositoryPort,
        settings: Settings,
        *,
        llm_provider_factory,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.llm_provider_factory = llm_provider_factory

    def descriptors(self) -> dict[str, list[dict[str, object]]]:
        return {"connectors": connector_descriptors()}

    def accounts(self) -> dict[str, list[dict]]:
        return {"connector_accounts": self.repository.list_connector_accounts()}

    def create_account(self, payload: ConnectorAccountCreate, *, actor_id: str) -> dict:
        return self.repository.create_connector_account(payload, actor_id)

    def update_credentials(self, account_id: str, payload: ConnectorCredentialUpdate) -> dict:
        return self.repository.update_connector_account_tokens(
            account_id,
            payload.token_json,
            project_id="project-default",
        )

    def delete_credentials(self, account_id: str) -> dict:
        return self.repository.clear_connector_account_tokens(account_id, project_id="project-default")

    def targets(self) -> dict[str, list[dict]]:
        return {"connector_targets": self.repository.list_connector_targets()}

    def create_target(self, payload: ConnectorTargetCreate) -> dict:
        return self.repository.create_connector_target(payload)

    def update_target(self, target_id: str, payload: ConnectorTargetUpdate) -> dict:
        target = self.repository.update_connector_target(target_id, payload)
        if target is None:
            raise KeyError(target_id)
        return target

    def sync_runs(self) -> dict[str, list[dict]]:
        return {"connector_sync_runs": self.repository.list_connector_sync_runs()}

    def sync_run(self, sync_run_id: str) -> dict:
        value = self.repository.get_connector_sync_run(sync_run_id)
        if value is None:
            raise KeyError(sync_run_id)
        return value

    async def create_sync(self, payload: ConnectorSyncCreate, *, actor_id: str) -> tuple[bool, dict]:
        if self.settings.environment in {"local", "test", "development"}:
            result = await GraphJobExecutor(
                self.repository,
                self.settings,
                llm_provider_factory=self.llm_provider_factory,
            ).connector_sync(
                payload.target_id,
                actor_id=actor_id,
                worker_id="api-development-compatibility",
                retry_attempt=1,
            )
            return False, result
        bundle = self.repository.connector_target_bundle(payload.target_id)
        if bundle is None:
            raise KeyError(payload.target_id)
        _, target, _ = bundle
        ConnectorStateRepository(self.repository.engine).mark_queued(payload.target_id)
        job = JobRepository(self.repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"connector-sync:{payload.target_id}:{target.get('updated_at')}",
                payload={"project_id": target["project_id"], "target_id": payload.target_id, "actor_id": actor_id},
            ),
            project_id=target["project_id"],
        )
        return True, job
