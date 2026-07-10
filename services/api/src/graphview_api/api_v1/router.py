from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse

from graphview_api.api_v1.repository import GraphProjectionRepository
from graphview_api.api_v1.schemas import (
    GraphActivityPage,
    GraphBounds,
    GraphLayoutOut,
    GraphLayoutUpsert,
    GraphSearchOut,
    GraphSubgraphOut,
    GraphViewportOut,
    ConnectorHealthOut,
    UploadAccepted,
)
from graphview_api.api_v1.service import GraphProjectionService
from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, WRITE_PERMISSION, CurrentUser, ensure_project_access, require_permission
from graphview_api.jobs.repository import JobRepository
from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.jobs.schemas import JobCreate, JobOut, JobPage
from graphview_api.malware import scan_with_clamd
from graphview_api.repository import GraphRepository
from graphview_api.schemas import AgentRunCreate, GraphQueryCreate, GraphResearchCreate, IngestionCreate, PlanningMessageCreate
from graphview_api.resumable_uploads import create_resumable_upload_router

SUPPORTED_DURABLE_JOBS = {
    "ingestion.run": "ingestion",
    "upload.ingest": "ingestion",
    "connector.sync": "connectors",
    "action.run": "actions",
    "agent_context.retention": "maintenance",
    "ai.planning": "agents",
    "ai.query": "agents",
    "ai.research": "agents",
    "ai.agent": "agents",
}


def create_v1_router(repo_provider, *, object_store=None, settings=None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Graphview V1"])
    if object_store is not None and settings is not None:
        router.include_router(create_resumable_upload_router(repo_provider, object_store, settings))

    def service(repository: GraphRepository = Depends(repo_provider)) -> GraphProjectionService:
        return GraphProjectionService(GraphProjectionRepository(repository), repository)

    @router.post("/uploads", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
    async def upload_source(
        file: UploadFile = File(),
        title: str | None = Form(default=None),
        graph_id: str | None = Form(default=None),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        if object_store is None or settings is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Object storage is unavailable")
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(file.filename or "upload.bin").name).strip(".-") or "upload.bin"
        digest = hashlib.sha256()
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(prefix="graphview-upload-")
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.upload_max_bytes:
                        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds configured size limit")
                    digest.update(chunk)
                    temporary.write(chunk)
            if size == 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Upload is empty")
            content_type = file.content_type or "application/octet-stream"
            if settings.malware_scan_url:
                async with httpx.AsyncClient(timeout=60) as client:
                    with open(temporary_name, "rb") as upload_stream:
                        scan = await client.post(
                            settings.malware_scan_url,
                            files={"file": (filename, upload_stream, content_type)},
                        )
                    scan.raise_for_status()
                    if not bool(scan.json().get("clean")):
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Upload failed malware screening")
            elif settings.malware_scan_clamd_host:
                try:
                    await scan_with_clamd(
                        Path(temporary_name),
                        settings.malware_scan_clamd_host,
                        settings.malware_scan_clamd_port,
                    )
                except ValueError as error:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
            checksum = digest.hexdigest()
            project_id = (graph_id or "project-default").split(":", 1)[0]
            ensure_project_access(user, project_id)
            object_key = f"{project_id}/uploads/{uuid4().hex}/{filename}"
            object_store.put_file(object_key, Path(temporary_name), content_type=content_type, checksum=checksum)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
            await file.close()
        job = JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="upload.ingest",
                queue="ingestion",
                idempotency_key=f"upload:{project_id}:{checksum}",
                payload={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "actor_id": user.id,
                    "object_key": object_key,
                    "filename": filename,
                    "title": title or filename,
                    "content_type": content_type,
                    "checksum": checksum,
                },
            ),
            project_id=project_id,
        )
        return {
            "object_key": object_key,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size,
            "checksum": checksum,
            "job_id": job["id"],
        }

    def event_envelope(event: dict, graph_id: str) -> dict:
        return {
            "id": event["id"],
            "event_type": event["event_type"],
            "schema_version": 1,
            "project_id": event["project_id"],
            "graph_id": graph_id,
            "trace_id": event.get("payload", {}).get("trace_id") or f"activity:{event['id']}",
            "actor": {"id": event.get("actor_id"), "authority": event.get("payload", {}).get("authority", "graphview")},
            "occurred_at": event["occurred_at"],
            "received_at": event["occurred_at"],
            "replay_cursor": event["id"],
            "payload": event.get("payload", {}),
            "object_refs": event.get("object_refs", []),
        }

    @router.get("/graphs/{graph_id}/viewport", response_model=GraphViewportOut)
    async def graph_viewport(
        graph_id: str,
        response: Response,
        zoom: float = Query(default=0.75, ge=0, le=16),
        min_x: float = Query(default=-1),
        min_y: float = Query(default=-1),
        max_x: float = Query(default=1),
        max_y: float = Query(default=1),
        layout: str = Query(default="default", min_length=1, max_length=160),
        max_nodes: int = Query(default=2_000, ge=1, le=20_000),
        max_edges: int = Query(default=8_000, ge=1, le=50_000),
        if_none_match: str | None = Header(default=None),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        try:
            result = graph_service.viewport(
                graph_id,
                zoom=zoom,
                bounds=GraphBounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y),
                layout_name=layout,
                max_nodes=max_nodes,
                max_edges=max_edges,
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        response.headers["ETag"] = result["etag"]
        response.headers["Cache-Control"] = "private, no-cache"
        if if_none_match == result["etag"]:
            response.status_code = status.HTTP_304_NOT_MODIFIED
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))
        return result

    @router.get("/graphs/{graph_id}/subgraph", response_model=GraphSubgraphOut)
    async def graph_subgraph(
        graph_id: str,
        focus_node_id: str | None = Query(default=None),
        depth: int = Query(default=1, ge=1, le=2),
        max_nodes: int = Query(default=100, ge=1, le=2_000),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        result = graph_service.subgraph(graph_id, focus_node_id=focus_node_id, depth=depth, max_nodes=max_nodes)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Focus node not found")
        return result

    @router.get("/graphs/{graph_id}/search", response_model=GraphSearchOut)
    async def graph_search(
        graph_id: str,
        q: str = Query(min_length=1, max_length=500),
        limit: int = Query(default=25, ge=1, le=100),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        graph_service: GraphProjectionService = Depends(service),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        return graph_service.search(graph_id, q, limit=limit, actor_id=user.id)

    @router.get("/graphs/{graph_id}/layouts", response_model=list[GraphLayoutOut])
    async def list_layouts(
        graph_id: str,
        include_positions: bool = Query(default=False),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        projection = GraphProjectionRepository(repository)
        return projection.list_layouts(graph_id.split(":", 1)[0], include_positions=include_positions)

    @router.put("/graphs/{graph_id}/layouts/{layout_name}", response_model=GraphLayoutOut)
    async def put_layout(
        graph_id: str,
        layout_name: str,
        payload: GraphLayoutUpsert,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        if payload.name != layout_name:
            payload = payload.model_copy(update={"name": layout_name})
        try:
            return GraphProjectionRepository(repository).upsert_layout(graph_id.split(":", 1)[0], payload, actor_id=user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @router.get("/graphs/{graph_id}/activity", response_model=GraphActivityPage)
    async def graph_activity_page(
        graph_id: str,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        raw_events = (
            repository.list_graph_activity_events_after(graph_id=graph_id, cursor=cursor, limit=limit)
            if cursor
            else list(reversed(repository.list_graph_activity_events(graph_id=graph_id, limit=limit)))
        )
        events = [event_envelope(event, graph_id) for event in raw_events]
        next_cursor = events[-1]["id"] if len(events) == limit else None
        return {
            "graph_id": graph_id,
            "events": events,
            "page": {"next_cursor": next_cursor, "returned_count": len(events), "total_count": None},
        }

    @router.get("/graphs/{graph_id}/stream", response_class=StreamingResponse)
    async def graph_activity_stream(
        graph_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        limit: int = Query(default=100, ge=1, le=200),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        ensure_project_access(user, graph_id.split(":", 1)[0])
        async def stream():
            cursor = last_event_id
            while not await request.is_disconnected():
                events = (
                    repository.list_graph_activity_events_after(graph_id=graph_id, cursor=cursor, limit=limit)
                    if cursor
                    else list(reversed(repository.list_graph_activity_events(graph_id=graph_id, limit=limit)))
                )
                if events:
                    for event in events:
                        envelope = event_envelope(event, graph_id)
                        cursor = envelope["id"]
                        yield f"id: {cursor}\nevent: {envelope['event_type']}\ndata: {json.dumps(envelope, sort_keys=True, default=str)}\n\n"
                else:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(10)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @router.post("/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def create_job(
        payload: JobCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        expected_queue = SUPPORTED_DURABLE_JOBS.get(payload.kind)
        if expected_queue is None or payload.queue != expected_queue:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported durable job kind or queue",
            )
        project_id = str(payload.payload.get("project_id") or "project-default")
        ensure_project_access(user, project_id)
        job = JobRepository(repository.engine).enqueue(payload, project_id=project_id)
        return job

    @router.post("/ingestions", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ingestion(
        payload: IngestionCreate,
        graph_id: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        project_id = (graph_id or "project-default").split(":", 1)[0]
        ensure_project_access(user, project_id)
        canonical_payload = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        payload_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        idempotency_key = f"ingestion:{project_id}:{payload_digest}"
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="ingestion.run",
                queue="ingestion",
                idempotency_key=idempotency_key,
                payload={"project_id": project_id, "graph_id": graph_id, "actor_id": user.id, "ingestion": payload.model_dump(mode="json")},
            ),
            project_id=project_id,
        )

    @router.post("/ai/planning-sessions/{session_id}/messages", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_planning_message(
        session_id: str,
        payload: PlanningMessageCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        session = repository.get_planning_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found")
        ensure_project_access(user, session["project_id"])
        message_json = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="ai.planning",
                queue="agents",
                idempotency_key=f"ai-planning:{session_id}:{hashlib.sha256(message_json.encode()).hexdigest()}",
                payload={"project_id": session["project_id"], "actor_id": user.id, "session_id": session_id, "message": payload.model_dump(mode="json")},
            ),
            project_id=session["project_id"],
        )

    @router.post("/ai/query", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ai_query(
        payload: GraphQueryCreate,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        project_id = (payload.graph_id or "project-default").split(":", 1)[0]
        ensure_project_access(user, project_id)
        canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="ai.query",
                queue="agents",
                idempotency_key=f"ai-query:{project_id}:{hashlib.sha256(canonical.encode()).hexdigest()}",
                payload={"project_id": project_id, "actor_id": user.id, "query": payload.model_dump(mode="json")},
            ),
            project_id=project_id,
        )

    @router.post("/ai/research", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ai_research(
        payload: GraphResearchCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        project_id = (payload.graph_id or "project-default").split(":", 1)[0]
        ensure_project_access(user, project_id)
        canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="ai.research",
                queue="agents",
                idempotency_key=f"ai-research:{project_id}:{hashlib.sha256(canonical.encode()).hexdigest()}",
                payload={"project_id": project_id, "actor_id": user.id, "research": payload.model_dump(mode="json")},
            ),
            project_id=project_id,
        )

    @router.post("/ai/agent-runs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_ai_agent_run(
        payload: AgentRunCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        project_id = str(payload.input.get("project_id") or (payload.input.get("graph_id") or "project-default")).split(":", 1)[0]
        ensure_project_access(user, project_id)
        canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="ai.agent",
                queue="agents",
                idempotency_key=f"ai-agent:{project_id}:{hashlib.sha256(canonical.encode()).hexdigest()}",
                payload={"project_id": project_id, "actor_id": user.id, "agent_run": payload.model_dump(mode="json")},
            ),
            project_id=project_id,
        )

    @router.post("/connectors/{target_id}/sync", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_connector_sync(
        target_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        _, target, _ = bundle
        project_id = target["project_id"]
        ensure_project_access(user, project_id)
        sync_revision = target.get("updated_at") or target.get("last_synced_at") or "initial"
        ConnectorStateRepository(repository.engine).mark_queued(target_id)
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"connector-sync:{target_id}:{sync_revision}",
                payload={"project_id": project_id, "target_id": target_id, "actor_id": user.id},
            ),
            project_id=project_id,
        )

    @router.get("/connectors/{target_id}/health", response_model=ConnectorHealthOut)
    async def connector_health(
        target_id: str,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        health = ConnectorStateRepository(repository.engine).get(target_id)
        if health is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        project_id = ConnectorStateRepository(repository.engine).project_id(target_id)
        if project_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        ensure_project_access(user, project_id)
        return health

    @router.post("/connectors/github/{target_id}/webhook", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def github_connector_webhook(
        target_id: str,
        request: Request,
        x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
        x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
        x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
        repository: GraphRepository = Depends(repo_provider),
    ):
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        account, target, credentials = bundle
        if account["kind"] != "repository" or not credentials or not credentials.get("webhook_secret"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GitHub webhook secret is not configured")
        body = await request.body()
        expected = "sha256=" + hmac.new(str(credentials["webhook_secret"]).encode(), body, hashlib.sha256).hexdigest()
        if not x_hub_signature_256 or not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub webhook signature")
        if not x_github_delivery or x_github_event not in {"push", "issues", "pull_request", "installation", "installation_repositories"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported GitHub webhook event")
        project_id = target["project_id"]
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"github-webhook:{target_id}:{x_github_delivery}",
                payload={
                    "project_id": project_id,
                    "target_id": target_id,
                    "actor_id": "github-webhook",
                    "delivery_id": x_github_delivery,
                    "event": x_github_event,
                },
            ),
            project_id=project_id,
        )

    @router.post("/connectors/google/{target_id}/webhook", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def google_connector_webhook(
        target_id: str,
        x_goog_channel_id: str | None = Header(default=None, alias="X-Goog-Channel-ID"),
        x_goog_channel_token: str | None = Header(default=None, alias="X-Goog-Channel-Token"),
        x_goog_resource_id: str | None = Header(default=None, alias="X-Goog-Resource-ID"),
        x_goog_resource_state: str | None = Header(default=None, alias="X-Goog-Resource-State"),
        x_goog_message_number: str | None = Header(default=None, alias="X-Goog-Message-Number"),
        repository: GraphRepository = Depends(repo_provider),
    ):
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        account, target, credentials = bundle
        watch = credentials.get("drive_watch") if credentials and isinstance(credentials.get("drive_watch"), dict) else None
        if account["kind"] != "google-workspace" or not watch:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Google Drive watch channel is not configured")
        supplied = (x_goog_channel_id, x_goog_channel_token, x_goog_resource_id)
        expected = (watch.get("channel_id"), watch.get("channel_token"), watch.get("resource_id"))
        if any(value is None for value in supplied) or not all(
            hmac.compare_digest(str(actual), str(required)) for actual, required in zip(supplied, expected, strict=True)
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google Drive watch channel")
        if not x_goog_resource_state or len(x_goog_resource_state) > 80:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Google Drive resource state is required")
        if not x_goog_message_number or not x_goog_message_number.isdigit():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Google Drive message number is required")
        project_id = target["project_id"]
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"google-webhook:{target_id}:{x_goog_channel_id}:{x_goog_message_number}",
                payload={
                    "project_id": project_id,
                    "target_id": target_id,
                    "actor_id": "google-drive-webhook",
                    "message_number": x_goog_message_number,
                    "resource_state": x_goog_resource_state,
                },
            ),
            project_id=project_id,
        )

    @router.post("/connectors/notion/{target_id}/webhook", status_code=status.HTTP_202_ACCEPTED)
    async def notion_connector_webhook(
        target_id: str,
        request: Request,
        x_notion_signature: str | None = Header(default=None, alias="X-Notion-Signature"),
        repository: GraphRepository = Depends(repo_provider),
    ):
        body = await request.body()
        if not body or len(body) > 1_048_576:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Invalid Notion webhook payload size")
        try:
            event = json.loads(body)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid Notion webhook JSON") from error
        if not isinstance(event, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid Notion webhook event")
        bundle = repository.connector_target_bundle(target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        account, target, credentials = bundle
        if account["kind"] != "notion":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Connector target is not a Notion target")
        credentials = credentials or {}
        configured_token = str(credentials.get("notion_webhook_verification_token") or "")
        verification_token = str(event.get("verification_token") or "")
        if verification_token:
            if configured_token and not hmac.compare_digest(configured_token, verification_token):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected Notion verification token")
            if not configured_token:
                if target.get("sync_settings", {}).get("webhook_verification_pending") is not True:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Notion webhook verification is not armed for this target",
                    )
                credentials["notion_webhook_verification_token"] = verification_token
                repository.update_connector_account_tokens(
                    account["id"],
                    credentials,
                    project_id=target["project_id"],
                )
            return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "verification_token_stored"})
        if not configured_token:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Notion webhook verification token is not configured")
        expected = "sha256=" + hmac.new(configured_token.encode(), body, hashlib.sha256).hexdigest()
        if not x_notion_signature or not hmac.compare_digest(expected, x_notion_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Notion webhook signature")
        event_id = str(event.get("id") or "").strip()
        event_type = str(event.get("type") or "").strip()
        if not event_id or len(event_id) > 200 or not event_type or len(event_type) > 160:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid Notion webhook identity")
        workspace_id = str(event.get("workspace_id") or "")
        integration_id = str(event.get("integration_id") or "")
        if credentials.get("workspace_id") and not hmac.compare_digest(str(credentials["workspace_id"]), workspace_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected Notion workspace")
        if credentials.get("integration_id") and not hmac.compare_digest(str(credentials["integration_id"]), integration_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected Notion integration")
        entity = event.get("entity") if isinstance(event.get("entity"), dict) else {}
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"notion-webhook:{target_id}:{event_id}",
                payload={
                    "project_id": target["project_id"],
                    "target_id": target_id,
                    "actor_id": "notion-webhook",
                    "webhook_event": {
                        "id": event_id,
                        "type": event_type,
                        "timestamp": event.get("timestamp"),
                        "attempt_number": event.get("attempt_number"),
                        "entity_id": entity.get("id"),
                        "entity_type": entity.get("type"),
                    },
                },
            ),
            project_id=target["project_id"],
        )

    @router.post("/action-proposals/{action_proposal_id}/run", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
    async def enqueue_action_run(
        action_proposal_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        proposal = repository.get_action_proposal(action_proposal_id)
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        ensure_project_access(user, proposal["project_id"])
        if proposal["status"] != "approved":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action proposal must be approved")
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="action.run",
                queue="actions",
                idempotency_key=f"action-run:{action_proposal_id}",
                payload={"project_id": proposal["project_id"], "action_proposal_id": action_proposal_id, "actor_id": user.id},
            ),
            project_id=proposal["project_id"],
        )

    @router.get("/jobs", response_model=JobPage)
    async def list_jobs(
        project_id: str = Query(default="project-default"),
        status_filter: str | None = Query(default=None, alias="status"),
        cursor: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        ensure_project_access(user, project_id)
        jobs = JobRepository(repository.engine).list(project_id=project_id, status=status_filter, cursor=cursor, limit=limit)
        return {"jobs": jobs, "next_cursor": jobs[-1]["id"] if len(jobs) == limit else None}

    @router.get("/jobs/{job_id}", response_model=JobOut)
    async def get_job(
        job_id: str,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        job = JobRepository(repository.engine).get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, job["project_id"])
        return job

    @router.get("/jobs/{job_id}/stream", response_class=StreamingResponse)
    async def stream_job(
        job_id: str,
        request: Request,
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        initial = JobRepository(repository.engine).get(job_id)
        if initial is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, initial["project_id"])

        async def stream():
            previous = None
            while not await request.is_disconnected():
                job = JobRepository(repository.engine).get(job_id, project_id=initial["project_id"])
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

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.post("/jobs/{job_id}/cancel", response_model=JobOut)
    async def cancel_job(
        job_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        current = JobRepository(repository.engine).get(job_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, current["project_id"])
        job = JobRepository(repository.engine).cancel(job_id, project_id=current["project_id"])
        if job is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only queued, retrying, or running jobs can be cancelled")
        return job

    @router.post("/jobs/{job_id}/retry", response_model=JobOut)
    async def retry_job(
        job_id: str,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ):
        current = JobRepository(repository.engine).get(job_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        ensure_project_access(user, current["project_id"])
        job = JobRepository(repository.engine).retry(job_id, project_id=current["project_id"])
        if job is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed or cancelled jobs can be retried")
        return job

    return router
