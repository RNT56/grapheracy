import pytest

from graphview_api.connector_service import ConnectorService
from graphview_api.schemas import ConnectorAccountCreate, ConnectorCredentialUpdate, ConnectorTargetUpdate
from graphview_api.settings import Settings


class RecordingConnectorRepository:
    engine = None

    def __init__(self) -> None:
        self.target_value = {"id": "target-1", "title": "Updated"}
        self.sync_run_value = {"id": "sync-1", "status": "succeeded"}

    def list_connector_accounts(self):
        return [{"id": "account-1"}]

    def create_connector_account(self, payload, actor_id):
        return {"id": "account-1", "kind": payload.kind, "created_by": actor_id}

    def update_connector_account_tokens(self, account_id, token_json, *, project_id):
        return {"id": account_id, "project_id": project_id, "token_count": len(token_json)}

    def clear_connector_account_tokens(self, account_id, *, project_id):
        return {"id": account_id, "project_id": project_id, "status": "credentials_missing"}

    def list_connector_targets(self):
        return [{"id": "target-1"}]

    def create_connector_target(self, payload):
        return {"id": "target-1", "title": payload.title}

    def update_connector_target(self, target_id, payload):
        return self.target_value

    def list_connector_sync_runs(self):
        return [self.sync_run_value]

    def get_connector_sync_run(self, sync_run_id):
        return self.sync_run_value

    def connector_target_bundle(self, target_id):
        return None


def service(repository: RecordingConnectorRepository | None = None) -> ConnectorService:
    return ConnectorService(
        repository or RecordingConnectorRepository(),
        Settings(database_url="sqlite://"),
        llm_provider_factory=lambda **_kwargs: None,
    )


def test_connector_service_owns_catalog_and_account_transitions() -> None:
    value = service()

    assert {item["kind"] for item in value.descriptors()["connectors"]} >= {"upload", "repository", "notion"}
    account = value.create_account(
        ConnectorAccountCreate(kind="upload", display_name="Uploads"),
        actor_id="admin-1",
    )
    assert account == {"id": "account-1", "kind": "upload", "created_by": "admin-1"}
    updated = value.update_credentials(
        "account-1",
        ConnectorCredentialUpdate(token_json={"access_token": "secret"}),
    )
    assert updated["project_id"] == "project-default"


def test_connector_service_exposes_missing_target_as_domain_error() -> None:
    repository = RecordingConnectorRepository()
    repository.target_value = None

    with pytest.raises(KeyError):
        service(repository).update_target("missing", ConnectorTargetUpdate(title="Missing"))


def test_connector_service_exposes_missing_sync_run_as_domain_error() -> None:
    repository = RecordingConnectorRepository()
    repository.sync_run_value = None

    with pytest.raises(KeyError):
        service(repository).sync_run("missing")
