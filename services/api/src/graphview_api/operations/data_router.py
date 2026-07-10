from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Query

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission
from graphview_api.repository import GraphRepository
from graphview_api.schemas import BackupBundle, ExportBundle, ImportBundle


def create_data_operations_router(repo_provider: Callable[[], GraphRepository]) -> APIRouter:
    router = APIRouter()

    @router.get("/search")
    async def search(
        q: str = Query(min_length=1),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[object]]:
        return repository.search(q, graph_id)

    @router.get("/export", response_model=ExportBundle)
    async def export(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.export_bundle(graph_id)

    @router.get("/backup", response_model=BackupBundle)
    async def backup(
        include_agent_context_content: bool = Query(default=False),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.backup_bundle(
            actor_id=user.id,
            include_agent_context_content=include_agent_context_content,
        )

    @router.post("/restore", response_model=ExportBundle)
    async def restore(
        payload: BackupBundle,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.restore_bundle(payload.bundle, actor_id=user.id)

    @router.post("/import", response_model=ExportBundle)
    async def import_bundle(
        payload: ImportBundle,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        for source in payload.sources:
            repository.create_source(source)
        for proposal in payload.proposals:
            repository.create_proposal(proposal, user.id)
        return repository.export_bundle()

    return router
