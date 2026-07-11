from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from graphview_api.api_v1.connector_service import (
    ConnectorAuthenticationError,
    ConnectorConflictError,
    ConnectorNotFoundError,
    ConnectorPayloadTooLargeError,
    V1ConnectorError,
    V1ConnectorService,
)
from graphview_api.api_v1.schemas import ConnectorHealthOut
from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, ensure_project_access, require_permission
from graphview_api.jobs.schemas import JobOut


def _http_error(error: V1ConnectorError) -> HTTPException:
    if isinstance(error, ConnectorNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, ConnectorConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(error, ConnectorAuthenticationError):
        code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(error, ConnectorPayloadTooLargeError):
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(error))


def create_v1_connector_router(service_provider) -> APIRouter:
    router = APIRouter()

    @router.post("/connectors/{target_id}/sync", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_connector_sync(
        target_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        connector_service: V1ConnectorService = Depends(service_provider),
    ):
        try:
            project_id = connector_service.sync_project_id(target_id)
        except V1ConnectorError as error:
            raise _http_error(error) from error
        ensure_project_access(user, project_id)
        return connector_service.enqueue_sync(target_id, actor_id=user.id)

    @router.get("/connectors/{target_id}/health", response_model=ConnectorHealthOut)
    async def connector_health(
        target_id: str,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        connector_service: V1ConnectorService = Depends(service_provider),
    ):
        try:
            project_id, health = connector_service.health(target_id)
        except V1ConnectorError as error:
            raise _http_error(error) from error
        ensure_project_access(user, project_id)
        return health

    @router.post("/connectors/github/{target_id}/webhook", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def github_connector_webhook(
        target_id: str,
        request: Request,
        x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
        x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
        x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
        connector_service: V1ConnectorService = Depends(service_provider),
    ):
        try:
            return connector_service.github_webhook(
                target_id,
                await request.body(),
                signature=x_hub_signature_256,
                delivery_id=x_github_delivery,
                event=x_github_event,
            )
        except V1ConnectorError as error:
            raise _http_error(error) from error

    @router.post("/connectors/google/{target_id}/webhook", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def google_connector_webhook(
        target_id: str,
        x_goog_channel_id: str | None = Header(default=None, alias="X-Goog-Channel-ID"),
        x_goog_channel_token: str | None = Header(default=None, alias="X-Goog-Channel-Token"),
        x_goog_resource_id: str | None = Header(default=None, alias="X-Goog-Resource-ID"),
        x_goog_resource_state: str | None = Header(default=None, alias="X-Goog-Resource-State"),
        x_goog_message_number: str | None = Header(default=None, alias="X-Goog-Message-Number"),
        connector_service: V1ConnectorService = Depends(service_provider),
    ):
        try:
            return connector_service.google_webhook(
                target_id,
                channel_id=x_goog_channel_id,
                channel_token=x_goog_channel_token,
                resource_id=x_goog_resource_id,
                resource_state=x_goog_resource_state,
                message_number=x_goog_message_number,
            )
        except V1ConnectorError as error:
            raise _http_error(error) from error

    @router.post("/connectors/notion/{target_id}/webhook", status_code=status.HTTP_202_ACCEPTED)
    async def notion_connector_webhook(
        target_id: str,
        request: Request,
        x_notion_signature: str | None = Header(default=None, alias="X-Notion-Signature"),
        connector_service: V1ConnectorService = Depends(service_provider),
    ):
        try:
            verified, result = connector_service.notion_webhook(
                target_id,
                await request.body(),
                signature=x_notion_signature,
            )
        except V1ConnectorError as error:
            raise _http_error(error) from error
        if verified:
            return JSONResponse(status_code=status.HTTP_200_OK, content=result)
        return result

    return router
