from __future__ import annotations

from typing import Protocol

from sqlalchemy import Engine

from graphview_api.schemas import ConnectorAccountCreate, ConnectorTargetCreate, ConnectorTargetUpdate


class ConnectorRepositoryPort(Protocol):
    engine: Engine

    def list_connector_accounts(self, *, project_id: str = "project-default") -> list[dict]: ...

    def create_connector_account(
        self,
        payload: ConnectorAccountCreate,
        actor_id: str,
        *,
        project_id: str = "project-default",
    ) -> dict: ...

    def update_connector_account_tokens(self, account_id: str, token_json: dict, *, project_id: str) -> dict: ...

    def clear_connector_account_tokens(self, account_id: str, *, project_id: str) -> dict: ...

    def list_connector_targets(self, *, project_id: str | None = "project-default") -> list[dict]: ...

    def create_connector_target(self, payload: ConnectorTargetCreate, *, project_id: str = "project-default") -> dict: ...

    def update_connector_target(
        self,
        target_id: str,
        payload: ConnectorTargetUpdate,
        *,
        project_id: str = "project-default",
    ) -> dict | None: ...

    def list_connector_sync_runs(self, *, project_id: str = "project-default") -> list[dict]: ...

    def get_connector_sync_run(self, sync_run_id: str, *, project_id: str = "project-default") -> dict | None: ...

    def connector_target_bundle(
        self,
        target_id: str,
        *,
        project_id: str | None = None,
    ) -> tuple[dict, dict, dict | None] | None: ...
