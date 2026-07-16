from __future__ import annotations

from fastapi import Depends

from graphview_api.api_v1.upload_service import UploadService
from graphview_api.jobs.repository import JobRepository
from graphview_api.repository import GraphRepository


def create_upload_service_provider(repo_provider, object_store, settings):
    def provide(repository: GraphRepository = Depends(repo_provider)) -> UploadService:
        return UploadService(JobRepository(repository.engine), object_store=object_store, settings=settings)

    return provide
