from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Query

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission
from graphview_api.operations.service import DataOperationsService
from graphview_api.schemas import BackupBundle, ExportBundle, ImportBundle


def create_data_operations_router(service_provider: Callable[[], DataOperationsService]) -> APIRouter:
    router = APIRouter()

    @router.get("/search")
    async def search(
        q: str = Query(min_length=1),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        service: DataOperationsService = Depends(service_provider),
    ) -> dict[str, list[object]]:
        return service.search(query=q, graph_id=graph_id)

    @router.get("/export", response_model=ExportBundle)
    async def export(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: DataOperationsService = Depends(service_provider),
    ) -> dict:
        return service.export(graph_id=graph_id)

    @router.get("/backup", response_model=BackupBundle)
    async def backup(
        include_agent_context_content: bool = Query(default=False),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: DataOperationsService = Depends(service_provider),
    ) -> dict:
        return service.backup(
            actor_id=user.id,
            include_agent_context_content=include_agent_context_content,
        )

    @router.post("/restore", response_model=ExportBundle)
    async def restore(
        payload: BackupBundle,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: DataOperationsService = Depends(service_provider),
    ) -> dict:
        return service.restore(payload, actor_id=user.id)

    @router.post("/import", response_model=ExportBundle)
    async def import_bundle(
        payload: ImportBundle,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        service: DataOperationsService = Depends(service_provider),
    ) -> dict:
        return service.import_bundle(payload, actor_id=user.id)

    return router
