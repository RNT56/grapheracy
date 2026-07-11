from __future__ import annotations

from fastapi import APIRouter

from graphview_api.api_v1.action_dependencies import create_v1_action_service_provider
from graphview_api.api_v1.action_router import create_v1_action_router
from graphview_api.api_v1.connector_dependencies import create_v1_connector_service_provider
from graphview_api.api_v1.connector_router import create_v1_connector_router
from graphview_api.api_v1.graph_dependencies import create_graph_projection_service_provider
from graphview_api.api_v1.graph_router import create_v1_graph_router
from graphview_api.api_v1.job_dependencies import create_job_service_provider
from graphview_api.api_v1.job_router import create_v1_job_command_router, create_v1_job_lifecycle_router
from graphview_api.api_v1.upload_dependencies import create_upload_service_provider
from graphview_api.api_v1.upload_router import create_v1_upload_router
from graphview_api.resumable_uploads import create_resumable_upload_router


def create_v1_router(repo_provider, *, object_store=None, settings=None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Graphview V1"])
    if object_store is not None and settings is not None:
        router.include_router(create_resumable_upload_router(repo_provider, object_store, settings))
    router.include_router(create_v1_upload_router(create_upload_service_provider(repo_provider, object_store, settings)))
    router.include_router(create_v1_graph_router(create_graph_projection_service_provider(repo_provider)))

    job_service_provider = create_job_service_provider(repo_provider)
    router.include_router(create_v1_job_command_router(job_service_provider))
    router.include_router(create_v1_connector_router(create_v1_connector_service_provider(repo_provider)))
    router.include_router(create_v1_action_router(create_v1_action_service_provider(repo_provider)))
    router.include_router(create_v1_job_lifecycle_router(job_service_provider))
    return router
