from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import UploadFile

from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.malware import scan_with_clamd


class UploadUnavailableError(RuntimeError):
    pass


class UploadValidationError(ValueError):
    def __init__(self, message: str, *, too_large: bool = False):
        super().__init__(message)
        self.too_large = too_large


class UploadService:
    def __init__(self, jobs: JobRepository, *, object_store=None, settings=None):
        self.jobs = jobs
        self.object_store = object_store
        self.settings = settings

    @staticmethod
    def project_id(graph_id: str | None) -> str:
        return (graph_id or "project-default").split(":", 1)[0]

    async def accept(self, file: UploadFile, *, title: str | None, graph_id: str | None, actor_id: str) -> dict:
        if self.object_store is None or self.settings is None:
            raise UploadUnavailableError("Object storage is unavailable")
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(file.filename or "upload.bin").name).strip(".-") or "upload.bin"
        digest = hashlib.sha256()
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(prefix="graphview-upload-")
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.upload_max_bytes:
                        raise UploadValidationError("Upload exceeds configured size limit", too_large=True)
                    digest.update(chunk)
                    temporary.write(chunk)
            if size == 0:
                raise UploadValidationError("Upload is empty")
            content_type = file.content_type or "application/octet-stream"
            await self._scan(Path(temporary_name), filename=filename, content_type=content_type)
            checksum = digest.hexdigest()
            project_id = self.project_id(graph_id)
            object_key = f"{project_id}/uploads/{uuid4().hex}/{filename}"
            self.object_store.put_file(object_key, Path(temporary_name), content_type=content_type, checksum=checksum)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
            await file.close()
        job = self.jobs.enqueue(
            JobCreate(
                kind="upload.ingest",
                queue="ingestion",
                idempotency_key=f"upload:{project_id}:{checksum}",
                payload={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "actor_id": actor_id,
                    "object_key": object_key,
                    "filename": filename,
                    "title": title or filename,
                    "content_type": content_type,
                    "checksum": checksum,
                },
            ),
            project_id=project_id,
        )
        return {
            "object_key": object_key,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size,
            "checksum": checksum,
            "job_id": job["id"],
        }

    async def _scan(self, path: Path, *, filename: str, content_type: str) -> None:
        if self.settings.malware_scan_url:
            async with httpx.AsyncClient(timeout=60) as client:
                with path.open("rb") as upload_stream:
                    scan = await client.post(
                        self.settings.malware_scan_url,
                        files={"file": (filename, upload_stream, content_type)},
                    )
                scan.raise_for_status()
                if not bool(scan.json().get("clean")):
                    raise UploadValidationError("Upload failed malware screening")
        elif self.settings.malware_scan_clamd_host:
            try:
                await scan_with_clamd(path, self.settings.malware_scan_clamd_host, self.settings.malware_scan_clamd_port)
            except ValueError as error:
                raise UploadValidationError(str(error)) from error
