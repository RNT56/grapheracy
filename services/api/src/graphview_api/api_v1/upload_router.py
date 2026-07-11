from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from graphview_api.api_v1.schemas import UploadAccepted
from graphview_api.api_v1.upload_service import UploadService, UploadUnavailableError, UploadValidationError
from graphview_api.auth import OPERATE_PERMISSION, CurrentUser, ensure_project_access, require_permission


def create_v1_upload_router(service_provider) -> APIRouter:
    router = APIRouter()

    @router.post("/uploads", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
    async def upload_source(
        file: UploadFile = File(),
        title: str | None = Form(default=None),
        graph_id: str | None = Form(default=None),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        upload_service: UploadService = Depends(service_provider),
    ):
        ensure_project_access(user, upload_service.project_id(graph_id))
        try:
            return await upload_service.accept(file, title=title, graph_id=graph_id, actor_id=user.id)
        except UploadUnavailableError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except UploadValidationError as error:
            code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if error.too_large else status.HTTP_422_UNPROCESSABLE_ENTITY
            raise HTTPException(status_code=code, detail=str(error)) from error

    return router
