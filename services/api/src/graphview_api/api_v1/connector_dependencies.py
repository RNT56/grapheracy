from __future__ import annotations

from fastapi import Depends

from graphview_api.api_v1.connector_service import V1ConnectorService
from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.jobs.repository import JobRepository
from graphview_api.repository import GraphRepository


def create_v1_connector_service_provider(repo_provider):
    def provide(repository: GraphRepository = Depends(repo_provider)) -> V1ConnectorService:
        return V1ConnectorService(
            repository,
            ConnectorStateRepository(repository.engine),
            JobRepository(repository.engine),
        )

    return provide
