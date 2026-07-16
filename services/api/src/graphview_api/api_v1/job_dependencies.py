from __future__ import annotations

from fastapi import Depends

from graphview_api.api_v1.job_service import JobService
from graphview_api.jobs.repository import JobRepository
from graphview_api.repository import GraphRepository


def create_job_service_provider(repo_provider):
    def provide(repository: GraphRepository = Depends(repo_provider)) -> JobService:
        return JobService(JobRepository(repository.engine), repository)

    return provide
