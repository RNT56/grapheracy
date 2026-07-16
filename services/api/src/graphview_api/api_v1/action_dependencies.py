from __future__ import annotations

from fastapi import Depends

from graphview_api.api_v1.action_service import V1ActionService
from graphview_api.jobs.repository import JobRepository
from graphview_api.repository import GraphRepository


def create_v1_action_service_provider(repo_provider):
    def provide(repository: GraphRepository = Depends(repo_provider)) -> V1ActionService:
        return V1ActionService(repository, JobRepository(repository.engine))

    return provide
