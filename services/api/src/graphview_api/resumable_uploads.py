from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, ensure_project_access, require_permission
from graphview_api.repository import GraphRepository
from graphview_api.repository_uploads import ResumableUploadRepository


class ResumableUploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    content_type: str = Field(min_length=1, max_length=160)
    expected_bytes: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=240)
    graph_id: str | None = Field(default=None, max_length=160)


class ResumableUploadOut(BaseModel):
    id: str
    project_id: str
    object_key: str
    filename: str
    content_type: str
    expected_bytes: int
    received_bytes: int
    status: str
    job_id: str | None = None


def create_resumable_upload_router(repo_provider, object_store, settings) -> APIRouter:
    router = APIRouter(prefix="/uploads/resumable", tags=["Resumable uploads"])

    def uploads(repository: GraphRepository) -> ResumableUploadRepository:
        return ResumableUploadRepository(repository.engine, object_store)

    @router.post("", response_model=ResumableUploadOut, status_code=status.HTTP_201_CREATED)
    async def create_upload(
        payload: ResumableUploadCreate,
        response: Response,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        if payload.expected_bytes > settings.upload_max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds configured size limit")
        project_id = (payload.graph_id or "project-default").split(":", 1)[0]
        ensure_project_access(user, project_id)
        if not any(view["project_id"] == project_id for view in repository.list_graph_views()):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph project not found")
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(payload.filename).name).strip(".-") or "upload.bin"
        created = uploads(repository).create(
            project_id=project_id,
            graph_id=payload.graph_id,
            filename=filename,
            title=payload.title or filename,
            content_type=payload.content_type,
            expected_bytes=payload.expected_bytes,
            actor_id=user.id,
        )
        response.headers["Location"] = f"/api/v1/uploads/resumable/{created['id']}"
        response.headers["Upload-Offset"] = "0"
        return created

    @router.head("/{upload_id}")
    async def upload_status(
        upload_id: str,
        response: Response,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        upload = uploads(repository).get(upload_id)
        if upload is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")
        ensure_project_access(user, upload["project_id"])
        response.headers["Upload-Offset"] = str(upload["received_bytes"])
        response.headers["Upload-Length"] = str(upload["expected_bytes"])
        response.headers["Upload-Status"] = upload["status"]

    @router.patch("/{upload_id}", response_model=ResumableUploadOut)
    async def append_upload(
        upload_id: str,
        request: Request,
        response: Response,
        upload_offset: int = Header(alias="Upload-Offset", ge=0),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > 16 * 1024 * 1024:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload part exceeds 16 MiB")
        current = uploads(repository).get(upload_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")
        ensure_project_access(user, current["project_id"])
        if upload_offset + len(payload) < current["expected_bytes"] and len(payload) < 5 * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Non-final upload parts must be at least 5 MiB")
        try:
            result = uploads(repository).append(upload_id, offset=upload_offset, payload=bytes(payload))
        except RuntimeError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        response.headers["Upload-Offset"] = str(result["received_bytes"])
        return result

    @router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def abort_upload(
        upload_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        current = uploads(repository).get(upload_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")
        ensure_project_access(user, current["project_id"])
        try:
            uploads(repository).abort(upload_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found") from error

    return router
