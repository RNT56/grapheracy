from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from graphview_api.api_v1.job_service import JobService
from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, WRITE_PERMISSION, CurrentUser, ensure_project_access, require_permission
from graphview_api.jobs.schemas import JobCreate, JobOut, JobPage
from graphview_api.observability import observe_sse_stream
from graphview_api.schemas import AgentRunCreate, GraphQueryCreate, GraphResearchCreate, IngestionCreate, PlanningMessageCreate


def create_v1_job_command_router(service_provider) -> APIRouter:
    router = APIRouter()

    @router.post("/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def create_job(
        payload: JobCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        try:
            project_id = job_service.project_for_create(payload)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        ensure_project_access(user, project_id)
        return job_service.create(payload, project_id=project_id)

    @router.post("/ingestions", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ingestion(
        payload: IngestionCreate,
        graph_id: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        project_id = job_service.project_id(graph_id)
        ensure_project_access(user, project_id)
        return job_service.enqueue_ingestion(payload, graph_id, actor_id=user.id)

    @router.post("/ai/planning-sessions/{session_id}/messages", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_planning_message(
        session_id: str,
        payload: PlanningMessageCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        project_id = job_service.planning_project_id(session_id)
        if project_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found")
        ensure_project_access(user, project_id)
        return job_service.enqueue_planning(session_id, project_id, payload, actor_id=user.id)

    @router.post("/ai/query", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ai_query(
        payload: GraphQueryCreate,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        project_id = job_service.project_id(payload.graph_id)
        ensure_project_access(user, project_id)
        return job_service.enqueue_query(payload, actor_id=user.id)

    @router.post("/ai/research", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ai_research(
        payload: GraphResearchCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        project_id = job_service.project_id(payload.graph_id)
        ensure_project_access(user, project_id)
        return job_service.enqueue_research(payload, actor_id=user.id)

    @router.post("/ai/agent-runs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ai_agent_run(
        payload: AgentRunCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        graph_id = str(payload.input.get("project_id") or payload.input.get("graph_id") or "project-default")
        project_id = job_service.project_id(graph_id)
        ensure_project_access(user, project_id)
        return job_service.enqueue_agent(payload, actor_id=user.id)

    return router


def create_v1_job_lifecycle_router(service_provider) -> APIRouter:
    router = APIRouter()

    @router.get("/jobs", response_model=JobPage)
    async def list_jobs(
        project_id: str = Query(default="project-default"),
        status_filter: str | None = Query(default=None, alias="status"),
        cursor: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        ensure_project_access(user, project_id)
        jobs = job_service.list(project_id=project_id, status=status_filter, cursor=cursor, limit=limit)
        return {"jobs": jobs, "next_cursor": jobs[-1]["id"] if len(jobs) == limit else None}

    @router.get("/jobs/{job_id}", response_model=JobOut)
    async def get_job(
        job_id: str,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        job = job_service.get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, job["project_id"])
        return job

    @router.get("/jobs/{job_id}/stream", response_class=StreamingResponse)
    async def stream_job(
        job_id: str,
        request: Request,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        initial = job_service.get(job_id)
        if initial is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, initial["project_id"])

        async def stream():
            previous = None
            while not await request.is_disconnected():
                job = job_service.get(job_id, project_id=initial["project_id"])
                if job is None:
                    break
                signature = (job["status"], job["attempt"], job.get("updated_at"))
                if signature != previous:
                    previous = signature
                    yield f"id: {job['id']}:{job['attempt']}\nevent: job.{job['status']}\ndata: {json.dumps(job, default=str, sort_keys=True)}\n\n"
                else:
                    yield ": heartbeat\n\n"
                if job["status"] in {"succeeded", "failed", "cancelled"}:
                    break
                await asyncio.sleep(1)

        return StreamingResponse(
            observe_sse_stream(stream(), request.app.state.telemetry, stream_kind="job.status"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/jobs/{job_id}/cancel", response_model=JobOut)
    async def cancel_job(
        job_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        current = job_service.get(job_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, current["project_id"])
        job = job_service.cancel(job_id, project_id=current["project_id"])
        if job is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only queued, retrying, or running jobs can be cancelled")
        return job

    @router.post("/jobs/{job_id}/retry", response_model=JobOut)
    async def retry_job(
        job_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        job_service: JobService = Depends(service_provider),
    ):
        current = job_service.get(job_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, current["project_id"])
        job = job_service.retry(job_id, project_id=current["project_id"])
        if job is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed or cancelled jobs can be retried")
        return job

    return router
