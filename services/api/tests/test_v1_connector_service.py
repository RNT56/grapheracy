import hashlib
import hmac
import json

import pytest

from graphview_api.api_v1.connector_service import (
    ConnectorAuthenticationError,
    ConnectorValidationError,
    V1ConnectorService,
)


class RecordingLegacy:
    def __init__(self) -> None:
        self.updated_tokens = None
        self.account = {"id": "account-1", "kind": "repository"}
        self.target = {
            "id": "target-1",
            "project_id": "project-1",
            "updated_at": "2026-07-11T10:00:00Z",
            "sync_settings": {"webhook_verification_pending": True},
        }
        self.credentials = {"webhook_secret": "github-secret"}

    def connector_target_bundle(self, target_id: str):
        if target_id == "missing":
            return None
        return self.account, self.target, self.credentials

    def update_connector_account_tokens(self, account_id: str, credentials: dict, *, project_id: str):
        self.updated_tokens = (account_id, credentials.copy(), project_id)


class RecordingState:
    def __init__(self) -> None:
        self.queued = []

    def mark_queued(self, target_id: str):
        self.queued.append(target_id)

    def get(self, target_id: str):
        return {"target_id": target_id, "status": "healthy"}

    def project_id(self, _target_id: str):
        return "project-1"


class RecordingJobs:
    def __init__(self) -> None:
        self.calls = []

    def enqueue(self, payload, *, project_id: str):
        self.calls.append((payload.idempotency_key, payload.payload, project_id))
        return {"id": "job-1", "project_id": project_id, "kind": payload.kind}


def service():
    legacy = RecordingLegacy()
    state = RecordingState()
    jobs = RecordingJobs()
    return V1ConnectorService(legacy, state, jobs), legacy, state, jobs


def test_v1_connector_service_owns_sync_health_and_revision_idempotency() -> None:
    connector, _legacy, state, jobs = service()

    assert connector.sync_project_id("target-1") == "project-1"
    assert connector.enqueue_sync("target-1", actor_id="user-1")["id"] == "job-1"
    assert connector.health("target-1")[0] == "project-1"
    assert state.queued == ["target-1"]
    assert jobs.calls[0][0] == "connector-sync:target-1:2026-07-11T10:00:00Z"


def test_v1_connector_service_verifies_github_and_google_delivery_identity() -> None:
    connector, legacy, _state, jobs = service()
    body = b'{"ref":"refs/heads/main"}'
    signature = "sha256=" + hmac.new(b"github-secret", body, hashlib.sha256).hexdigest()

    connector.github_webhook(
        "target-1",
        body,
        signature=signature,
        delivery_id="delivery-1",
        event="push",
    )
    with pytest.raises(ConnectorAuthenticationError):
        connector.github_webhook("target-1", body, signature="bad", delivery_id="delivery-2", event="push")

    legacy.account["kind"] = "google-workspace"
    legacy.credentials = {
        "drive_watch": {"channel_id": "channel-1", "channel_token": "token-1", "resource_id": "resource-1"}
    }
    connector.google_webhook(
        "target-1",
        channel_id="channel-1",
        channel_token="token-1",
        resource_id="resource-1",
        resource_state="change",
        message_number="42",
    )
    with pytest.raises(ConnectorValidationError):
        connector.google_webhook(
            "target-1",
            channel_id="channel-1",
            channel_token="token-1",
            resource_id="resource-1",
            resource_state="change",
            message_number="not-a-number",
        )
    assert [call[0] for call in jobs.calls] == [
        "github-webhook:target-1:delivery-1",
        "google-webhook:target-1:channel-1:42",
    ]


def test_v1_connector_service_arms_notion_then_replay_keys_signed_events() -> None:
    connector, legacy, _state, jobs = service()
    legacy.account["kind"] = "notion"
    legacy.credentials = {}
    verified, response = connector.notion_webhook(
        "target-1",
        json.dumps({"verification_token": "notion-secret"}).encode(),
        signature=None,
    )
    assert verified is True
    assert response == {"status": "verification_token_stored"}
    assert legacy.updated_tokens[1]["notion_webhook_verification_token"] == "notion-secret"

    legacy.credentials = {"notion_webhook_verification_token": "notion-secret"}
    body = json.dumps({"id": "event-1", "type": "page.content_updated", "entity": {"id": "page-1", "type": "page"}}).encode()
    signature = "sha256=" + hmac.new(b"notion-secret", body, hashlib.sha256).hexdigest()
    verified, job = connector.notion_webhook("target-1", body, signature=signature)
    assert verified is False
    assert job["id"] == "job-1"
    assert jobs.calls[-1][0] == "notion-webhook:target-1:event-1"
