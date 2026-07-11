from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from graphview_api.api_v1.graph_dependencies import create_graph_projection_service_provider
from graphview_api.api_v1.graph_router import create_v1_graph_router
from graphview_api.api_v1.job_dependencies import create_job_service_provider
from graphview_api.api_v1.job_router import create_v1_job_command_router, create_v1_job_lifecycle_router
from graphview_api.api_v1.schemas import ConnectorHealthOut
from graphview_api.api_v1.upload_dependencies import create_upload_service_provider
from graphview_api.api_v1.upload_router import create_v1_upload_router
from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, ensure_project_access, require_permission
from graphview_api.jobs.repository import JobRepository
from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.jobs.schemas import JobCreate, JobOut
from graphview_api.repository import GraphRepository
from graphview_api.schemas import OutcomeCreate
from graphview_api.resumable_uploads import create_resumable_upload_router


def create_v1_router(repo_provider, *, object_store=None, settings=None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Graphview V1"])
    if object_store is not None and settings is not None:
        router.include_router(create_resumable_upload_router(repo_provider, object_store, settings))
    router.include_router(create_v1_upload_router(create_upload_service_provider(repo_provider, object_store, settings)))

    router.include_router(create_v1_graph_router(create_graph_projection_service_provider(repo_provider)))

    job_service_provider = create_job_service_provider(repo_provider)
    router.include_router(create_v1_job_command_router(job_service_provider))

    @router.post("/connectors/{target_id}/sync", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_connector_sync(
        target_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        _, target, _ = bundle
        project_id = target["project_id"]
        ensure_project_access(user, project_id)
        sync_revision = target.get("updated_at") or target.get("last_synced_at") or "initial"
        ConnectorStateRepository(repository.engine).mark_queued(target_id)
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"connector-sync:{target_id}:{sync_revision}",
                payload={"project_id": project_id, "target_id": target_id, "actor_id": user.id},
            ),
            project_id=project_id,
        )

    @router.get("/connectors/{target_id}/health", response_model=ConnectorHealthOut)
    async def connector_health(
        target_id: str,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        health = ConnectorStateRepository(repository.engine).get(target_id)
        if health is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        project_id = ConnectorStateRepository(repository.engine).project_id(target_id)
        if project_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        ensure_project_access(user, project_id)
        return health

    @router.post("/connectors/github/{target_id}/webhook", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def github_connector_webhook(
        target_id: str,
        request: Request,
        x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
        x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
        x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
        repository: GraphRepository = Depends(repo_provider),
    ):
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        account, target, credentials = bundle
        if account["kind"] != "repository" or not credentials or not credentials.get("webhook_secret"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GitHub webhook secret is not configured")
        body = await request.body()
        expected = "sha256=" + hmac.new(str(credentials["webhook_secret"]).encode(), body, hashlib.sha256).hexdigest()
        if not x_hub_signature_256 or not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub webhook signature")
        if not x_github_delivery or x_github_event not in {"push", "issues", "pull_request", "installation", "installation_repositories"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported GitHub webhook event")
        project_id = target["project_id"]
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"github-webhook:{target_id}:{x_github_delivery}",
                payload={
                    "project_id": project_id,
                    "target_id": target_id,
                    "actor_id": "github-webhook",
                    "delivery_id": x_github_delivery,
                    "event": x_github_event,
                },
            ),
            project_id=project_id,
        )

    @router.post("/connectors/google/{target_id}/webhook", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def google_connector_webhook(
        target_id: str,
        x_goog_channel_id: str | None = Header(default=None, alias="X-Goog-Channel-ID"),
        x_goog_channel_token: str | None = Header(default=None, alias="X-Goog-Channel-Token"),
        x_goog_resource_id: str | None = Header(default=None, alias="X-Goog-Resource-ID"),
        x_goog_resource_state: str | None = Header(default=None, alias="X-Goog-Resource-State"),
        x_goog_message_number: str | None = Header(default=None, alias="X-Goog-Message-Number"),
        repository: GraphRepository = Depends(repo_provider),
    ):
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        account, target, credentials = bundle
        watch = credentials.get("drive_watch") if credentials and isinstance(credentials.get("drive_watch"), dict) else None
        if account["kind"] != "google-workspace" or not watch:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Google Drive watch channel is not configured")
        supplied = (x_goog_channel_id, x_goog_channel_token, x_goog_resource_id)
        expected = (watch.get("channel_id"), watch.get("channel_token"), watch.get("resource_id"))
        if any(value is None for value in supplied) or not all(
            hmac.compare_digest(str(actual), str(required)) for actual, required in zip(supplied, expected, strict=True)
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google Drive watch channel")
        if not x_goog_resource_state or len(x_goog_resource_state) > 80:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Google Drive resource state is required")
        if not x_goog_message_number or not x_goog_message_number.isdigit():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Google Drive message number is required")
        project_id = target["project_id"]
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"google-webhook:{target_id}:{x_goog_channel_id}:{x_goog_message_number}",
                payload={
                    "project_id": project_id,
                    "target_id": target_id,
                    "actor_id": "google-drive-webhook",
                    "message_number": x_goog_message_number,
                    "resource_state": x_goog_resource_state,
                },
            ),
            project_id=project_id,
        )

    @router.post("/connectors/notion/{target_id}/webhook", status_code=status.HTTP_202_ACCEPTED)
    async def notion_connector_webhook(
        target_id: str,
        request: Request,
        x_notion_signature: str | None = Header(default=None, alias="X-Notion-Signature"),
        repository: GraphRepository = Depends(repo_provider),
    ):
        body = await request.body()
        if not body or len(body) > 1_048_576:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Invalid Notion webhook payload size")
        try:
            event = json.loads(body)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid Notion webhook JSON") from error
        if not isinstance(event, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid Notion webhook event")
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        account, target, credentials = bundle
        if account["kind"] != "notion":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Connector target is not a Notion target")
        credentials = credentials or {}
        configured_token = str(credentials.get("notion_webhook_verification_token") or "")
        verification_token = str(event.get("verification_token") or "")
        if verification_token:
            if configured_token and not hmac.compare_digest(configured_token, verification_token):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected Notion verification token")
            if not configured_token:
                if target.get("sync_settings", {}).get("webhook_verification_pending") is not True:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Notion webhook verification is not armed for this target",
                    )
                credentials["notion_webhook_verification_token"] = verification_token
                repository.update_connector_account_tokens(
                    account["id"],
                    credentials,
                    project_id=target["project_id"],
                )
            return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "verification_token_stored"})
        if not configured_token:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Notion webhook verification token is not configured")
        expected = "sha256=" + hmac.new(configured_token.encode(), body, hashlib.sha256).hexdigest()
        if not x_notion_signature or not hmac.compare_digest(expected, x_notion_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Notion webhook signature")
        event_id = str(event.get("id") or "").strip()
        event_type = str(event.get("type") or "").strip()
        if not event_id or len(event_id) > 200 or not event_type or len(event_type) > 160:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid Notion webhook identity")
        workspace_id = str(event.get("workspace_id") or "")
        integration_id = str(event.get("integration_id") or "")
        if credentials.get("workspace_id") and not hmac.compare_digest(str(credentials["workspace_id"]), workspace_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected Notion workspace")
        if credentials.get("integration_id") and not hmac.compare_digest(str(credentials["integration_id"]), integration_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected Notion integration")
        entity = event.get("entity") if isinstance(event.get("entity"), dict) else {}
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"notion-webhook:{target_id}:{event_id}",
                payload={
                    "project_id": target["project_id"],
                    "target_id": target_id,
                    "actor_id": "notion-webhook",
                    "webhook_event": {
                        "id": event_id,
                        "type": event_type,
                        "timestamp": event.get("timestamp"),
                        "attempt_number": event.get("attempt_number"),
                        "entity_id": entity.get("id"),
                        "entity_type": entity.get("type"),
                    },
                },
            ),
            project_id=target["project_id"],
        )

    @router.post("/action-proposals/{action_proposal_id}/run", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_action_run(
        action_proposal_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        proposal = repository.get_action_proposal(action_proposal_id)
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        ensure_project_access(user, proposal["project_id"])
        if proposal["status"] != "approved":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action proposal must be approved")
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="action.run",
                queue="actions",
                idempotency_key=f"action-run:{action_proposal_id}",
                payload={"project_id": proposal["project_id"], "action_proposal_id": action_proposal_id, "actor_id": user.id},
            ),
            project_id=proposal["project_id"],
        )

    @router.post("/action-runs/{action_run_id}/callback", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def action_outcome_callback(
        action_run_id: str,
        request: Request,
        x_graphview_event_id: str | None = Header(default=None, alias="X-Graphview-Event-Id"),
        x_graphview_timestamp: str | None = Header(default=None, alias="X-Graphview-Timestamp"),
        x_graphview_signature: str | None = Header(default=None, alias="X-Graphview-Signature"),
        repository: GraphRepository = Depends(repo_provider),
    ):
        body = await request.body()
        if not body or len(body) > 1_048_576:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Invalid outcome callback size")
        action_run = repository.get_action_run(action_run_id)
        if action_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action run not found")
        bundle = repository.action_proposal_execution_bundle(
            action_run["action_proposal_id"],
            project_id=action_run["project_id"],
        )
        if bundle is None or bundle[0]["action_type"] != "trigger_workflow":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action run does not accept workflow callbacks")
        _, action_payload = bundle
        credential_ref = str(action_payload.get("credential_ref") or "")
        if not credential_ref or repository.secret_store is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action callback secret is not configured")
        credential = repository.secret_store.get(credential_ref)
        callback_secret = str(credential.get("callback_secret") or credential.get("secret") or "")
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
        expected = "v1=" + hmac.new(
            callback_secret.encode(),
            f"{signed_at}.".encode() + body,
            hashlib.sha256,
        ).hexdigest()
        if not x_graphview_signature or not hmac.compare_digest(expected, x_graphview_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid outcome callback signature")
        try:
            outcome = OutcomeCreate.model_validate_json(body)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid outcome callback") from error
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="outcome.record",
                queue="outcomes",
                idempotency_key=f"action-outcome:{action_run_id}:{x_graphview_event_id}",
                payload={
                    "project_id": action_run["project_id"],
                    "action_run_id": action_run_id,
                    "actor_id": "workflow-callback",
                    "outcome": outcome.model_dump(mode="json"),
                    "callback_event_id": x_graphview_event_id,
                },
            ),
            project_id=action_run["project_id"],
        )

    router.include_router(create_v1_job_lifecycle_router(job_service_provider))

    return router
