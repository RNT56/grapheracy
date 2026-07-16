from __future__ import annotations

import hashlib
import hmac
import json

from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository


class V1ConnectorError(RuntimeError):
    pass


class ConnectorNotFoundError(V1ConnectorError):
    pass


class ConnectorConflictError(V1ConnectorError):
    pass


class ConnectorAuthenticationError(V1ConnectorError):
    pass


class ConnectorValidationError(V1ConnectorError):
    pass


class ConnectorPayloadTooLargeError(V1ConnectorError):
    pass


class V1ConnectorService:
    def __init__(self, legacy: GraphRepository, state: ConnectorStateRepository, jobs: JobRepository):
        self.legacy = legacy
        self.state = state
        self.jobs = jobs

    def sync_project_id(self, target_id: str) -> str:
        _, target, _ = self._bundle(target_id)
        return target["project_id"]

    def enqueue_sync(self, target_id: str, *, actor_id: str) -> dict:
        _, target, _ = self._bundle(target_id)
        revision = target.get("updated_at") or target.get("last_synced_at") or "initial"
        self.state.mark_queued(target_id)
        return self._enqueue(
            target_id,
            project_id=target["project_id"],
            idempotency_key=f"connector-sync:{target_id}:{revision}",
            actor_id=actor_id,
        )

    def health(self, target_id: str) -> tuple[str, dict]:
        health = self.state.get(target_id)
        project_id = self.state.project_id(target_id)
        if health is None or project_id is None:
            raise ConnectorNotFoundError("Connector target not found")
        return project_id, health

    def github_webhook(
        self,
        target_id: str,
        body: bytes,
        *,
        signature: str | None,
        delivery_id: str | None,
        event: str | None,
    ) -> dict:
        account, target, credentials = self._bundle(target_id)
        if account["kind"] != "repository" or not credentials or not credentials.get("webhook_secret"):
            raise ConnectorConflictError("GitHub webhook secret is not configured")
        expected = "sha256=" + hmac.new(str(credentials["webhook_secret"]).encode(), body, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature):
            raise ConnectorAuthenticationError("Invalid GitHub webhook signature")
        if not delivery_id or event not in {"push", "issues", "pull_request", "installation", "installation_repositories"}:
            raise ConnectorValidationError("Unsupported GitHub webhook event")
        return self._enqueue(
            target_id,
            project_id=target["project_id"],
            idempotency_key=f"github-webhook:{target_id}:{delivery_id}",
            actor_id="github-webhook",
            extra={"delivery_id": delivery_id, "event": event},
        )

    def google_webhook(
        self,
        target_id: str,
        *,
        channel_id: str | None,
        channel_token: str | None,
        resource_id: str | None,
        resource_state: str | None,
        message_number: str | None,
    ) -> dict:
        account, target, credentials = self._bundle(target_id)
        watch = credentials.get("drive_watch") if credentials and isinstance(credentials.get("drive_watch"), dict) else None
        if account["kind"] != "google-workspace" or not watch:
            raise ConnectorConflictError("Google Drive watch channel is not configured")
        supplied = (channel_id, channel_token, resource_id)
        expected = (watch.get("channel_id"), watch.get("channel_token"), watch.get("resource_id"))
        if any(value is None for value in supplied) or not all(
            hmac.compare_digest(str(actual), str(required)) for actual, required in zip(supplied, expected, strict=True)
        ):
            raise ConnectorAuthenticationError("Invalid Google Drive watch channel")
        if not resource_state or len(resource_state) > 80:
            raise ConnectorValidationError("Google Drive resource state is required")
        if not message_number or not message_number.isdigit():
            raise ConnectorValidationError("Google Drive message number is required")
        return self._enqueue(
            target_id,
            project_id=target["project_id"],
            idempotency_key=f"google-webhook:{target_id}:{channel_id}:{message_number}",
            actor_id="google-drive-webhook",
            extra={"message_number": message_number, "resource_state": resource_state},
        )

    def notion_webhook(self, target_id: str, body: bytes, *, signature: str | None) -> tuple[bool, dict]:
        if not body or len(body) > 1_048_576:
            raise ConnectorPayloadTooLargeError("Invalid Notion webhook payload size")
        try:
            event = json.loads(body)
        except json.JSONDecodeError as error:
            raise ConnectorValidationError("Invalid Notion webhook JSON") from error
        if not isinstance(event, dict):
            raise ConnectorValidationError("Invalid Notion webhook event")
        account, target, credentials = self._bundle(target_id)
        if account["kind"] != "notion":
            raise ConnectorConflictError("Connector target is not a Notion target")
        credentials = credentials or {}
        configured_token = str(credentials.get("notion_webhook_verification_token") or "")
        verification_token = str(event.get("verification_token") or "")
        if verification_token:
            if configured_token and not hmac.compare_digest(configured_token, verification_token):
                raise ConnectorAuthenticationError("Unexpected Notion verification token")
            if not configured_token:
                if target.get("sync_settings", {}).get("webhook_verification_pending") is not True:
                    raise ConnectorConflictError("Notion webhook verification is not armed for this target")
                credentials["notion_webhook_verification_token"] = verification_token
                self.legacy.update_connector_account_tokens(account["id"], credentials, project_id=target["project_id"])
            return True, {"status": "verification_token_stored"}
        if not configured_token:
            raise ConnectorConflictError("Notion webhook verification token is not configured")
        expected = "sha256=" + hmac.new(configured_token.encode(), body, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature):
            raise ConnectorAuthenticationError("Invalid Notion webhook signature")
        event_id = str(event.get("id") or "").strip()
        event_type = str(event.get("type") or "").strip()
        if not event_id or len(event_id) > 200 or not event_type or len(event_type) > 160:
            raise ConnectorValidationError("Invalid Notion webhook identity")
        if credentials.get("workspace_id") and not hmac.compare_digest(str(credentials["workspace_id"]), str(event.get("workspace_id") or "")):
            raise ConnectorAuthenticationError("Unexpected Notion workspace")
        if credentials.get("integration_id") and not hmac.compare_digest(str(credentials["integration_id"]), str(event.get("integration_id") or "")):
            raise ConnectorAuthenticationError("Unexpected Notion integration")
        entity = event.get("entity") if isinstance(event.get("entity"), dict) else {}
        job = self._enqueue(
            target_id,
            project_id=target["project_id"],
            idempotency_key=f"notion-webhook:{target_id}:{event_id}",
            actor_id="notion-webhook",
            extra={
                "webhook_event": {
                    "id": event_id,
                    "type": event_type,
                    "timestamp": event.get("timestamp"),
                    "attempt_number": event.get("attempt_number"),
                    "entity_id": entity.get("id"),
                    "entity_type": entity.get("type"),
                }
            },
        )
        return False, job

    def _bundle(self, target_id: str) -> tuple[dict, dict, dict | None]:
        bundle = self.legacy.connector_target_bundle(target_id)
        if bundle is None:
            raise ConnectorNotFoundError("Connector target not found")
        return bundle

    def _enqueue(
        self,
        target_id: str,
        *,
        project_id: str,
        idempotency_key: str,
        actor_id: str,
        extra: dict | None = None,
    ) -> dict:
        payload = {"project_id": project_id, "target_id": target_id, "actor_id": actor_id, **(extra or {})}
        return self.jobs.enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=idempotency_key,
                payload=payload,
            ),
            project_id=project_id,
        )
