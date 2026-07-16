from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, CurrentUser, require_permission


async def dependency_readiness(repository, identity, object_store) -> tuple[dict[str, str], bool]:
    checks = {"status": "ready", "service": "graphview-api"}
    ready = True
    try:
        repository.project()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        ready = False
    try:
        checks["session_store"] = await identity.ready()
    except Exception:
        checks["session_store"] = "error"
        ready = False
    try:
        checks["object_store"] = await asyncio.to_thread(object_store.ready)
    except Exception:
        checks["object_store"] = "error"
        ready = False
    if not ready:
        checks["status"] = "not_ready"
    return checks, ready


def create_health_router(repo_provider, *, identity, object_store) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "graphview-api"}

    @router.get("/ready", response_model=dict[str, str])
    async def readiness(repository=Depends(repo_provider)):
        checks, ready = await dependency_readiness(repository, identity, object_store)
        return checks if ready else JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=checks)

    return router


def create_operations_router(
    repo_provider,
    *,
    identity,
    object_store,
    request_metrics,
    environment: str,
    service_version: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/version")
    async def version() -> dict[str, str]:
        return {"service": "graphview-api", "version": service_version, "environment": environment}

    @router.get("/observability/ready")
    async def ready(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository=Depends(repo_provider),
    ):
        checks, ready = await dependency_readiness(repository, identity, object_store)
        checks.update({"environment": environment, "version": service_version})
        return checks if ready else JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=checks)

    @router.get("/observability/metrics")
    async def metrics(
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
    ) -> dict[str, object]:
        return request_metrics.snapshot()

    return router
