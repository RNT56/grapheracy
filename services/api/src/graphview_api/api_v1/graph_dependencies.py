from __future__ import annotations

from fastapi import Depends

from graphview_api.api_v1.repository import GraphProjectionRepository
from graphview_api.api_v1.service import GraphProjectionService
from graphview_api.repository import GraphRepository


def create_graph_projection_service_provider(repo_provider):
    def provide(repository: GraphRepository = Depends(repo_provider)) -> GraphProjectionService:
        return GraphProjectionService(GraphProjectionRepository(repository), repository)

    return provide
