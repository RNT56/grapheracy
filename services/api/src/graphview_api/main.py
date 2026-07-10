import json
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from graphview_api.agent_context import create_agent_context_router
from graphview_api.actions import create_actions_router
from graphview_api.ai import create_agent_tools_router, create_planning_router, create_retrieval_router
from graphview_api.attention import create_attention_router
from graphview_api.api_v1 import create_v1_router
from graphview_api.auth import (
    OPERATE_PERMISSION,
    READ_PERMISSION,
    CurrentUser,
    require_permission,
)
from graphview_api.connector_routes import create_connector_router
from graphview_api.db import create_app_engine
from graphview_api.identity import IdentityService
from graphview_api.identity.router import create_identity_router
from graphview_api.http_middleware import install_http_middleware
from graphview_api.lenses import EXTRACTION_LENS_DESCRIPTORS, GRAPH_LENS_DESCRIPTORS, normalize_graph_lens
from graphview_api.llm import build_llm_provider, build_provider_registry
from graphview_api.observability import RequestMetrics, configure_telemetry, observe_sse_stream
from graphview_api.object_store import build_object_store
from graphview_api.operations import create_health_router, create_operations_router
from graphview_api.repository import GraphRepository
from graphview_api.review import create_review_router
from graphview_api.schemas import (
    BackupBundle,
    ExportBundle,
    GraphActivityOut,
    GraphSettingsOut,
    GraphSettingsUpdate,
    GraphInsightsOut,
    GraphLensOut,
    GraphNeighborhoodOut,
    GraphOut,
    GraphPathOut,
    GraphViewOut,
    ImportBundle,
    ExtractionLensOut,
)
from graphview_api.settings import Settings, get_settings
from graphview_api.secret_store import build_secret_store
from graphview_api.sources import create_sources_router
from graphview_api.version import VERSION


def _activity_event_matches_agent_run(event: dict[str, object], agent_run_id: str) -> bool:
    payload = event.get("payload")
    if isinstance(payload, dict) and payload.get("agent_run_id") == agent_run_id:
        return True
    refs = event.get("object_refs")
    if not isinstance(refs, list):
        return False
    return any(
        isinstance(ref, dict) and ref.get("kind") == "agent_run" and ref.get("id") == agent_run_id
        for ref in refs
)


def configured_provider_registry(settings: Settings, repository: GraphRepository):
    return build_provider_registry(
        settings,
        provider_api_keys=repository.ai_provider_api_keys(),
        default_provider=repository.ai_default_provider(),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Graphview API", version=VERSION)
    app.dependency_overrides[get_settings] = lambda: settings
    object_store = build_object_store(settings)
    repository = GraphRepository(
        create_app_engine(settings.database_url),
        secret_key=settings.secret_key,
        auto_commit_threshold=settings.auto_commit_threshold,
        safe_action_types=settings.safe_action_types,
        agent_context_max_blob_bytes=settings.agent_context_max_blob_bytes,
        agent_context_retention_days=settings.agent_context_retention_days,
        secret_store=build_secret_store(settings),
        object_store=object_store,
    )
    is_development = settings.environment in {"local", "test", "development"}
    repository.initialize(create_schema=is_development)
    if is_development:
        from graphview_api.demo_seed import seed_development_demo

        seed_development_demo(repository)
    app.state.repository = repository
    app.state.metrics = RequestMetrics()
    app.state.identity = IdentityService(settings)
    app.state.object_store = object_store

    @app.exception_handler(HTTPException)
    async def problem_details_handler(request: Request, error: HTTPException):
        detail = error.detail if isinstance(error.detail, str) else "Request could not be completed"
        return JSONResponse(
            status_code=error.status_code,
            content={
                "type": f"https://graphview.local/problems/http-{error.status_code}",
                "title": detail,
                "status": error.status_code,
                "detail": detail,
                "instance": request.url.path,
            },
            headers=error.headers,
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_problem_handler(request: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "type": "https://graphview.local/problems/validation",
                "title": "Request validation failed",
                "status": 422,
                "detail": "One or more request fields are invalid.",
                "instance": request.url.path,
                "errors": json.loads(json.dumps(error.errors(), default=str)),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(Exception)
    async def internal_problem_handler(request: Request, _error: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "https://graphview.local/problems/internal",
                "title": "Internal server error",
                "status": 500,
                "detail": "The request could not be completed.",
                "instance": request.url.path,
            },
            media_type="application/problem+json",
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_http_middleware(app, settings)
    app.state.telemetry = configure_telemetry(app, repository.engine, settings)

    def repo() -> GraphRepository:
        return app.state.repository

    app.include_router(
        create_health_router(
            repo,
            identity=app.state.identity,
            object_store=app.state.object_store,
        )
    )
    app.include_router(create_identity_router(app.state.identity, settings))
    app.include_router(
        create_operations_router(
            repo,
            identity=app.state.identity,
            object_store=app.state.object_store,
            request_metrics=app.state.metrics,
            environment=settings.environment,
            service_version=VERSION,
        )
    )

    @app.get("/graph", response_model=GraphOut)
    async def graph(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        project, nodes, edges = repository.graph(graph_id, normalize_graph_lens(lens))
        return {"project": project, "nodes": nodes, "edges": edges, "user": user.id}

    @app.get("/graphs", response_model=list[GraphViewOut])
    async def graphs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> list[dict[str, object]]:
        return repository.list_graph_views()

    @app.get("/graph/activity", response_model=GraphActivityOut)
    async def graph_activity(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        limit: int = Query(default=50, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        events = repository.list_graph_activity_events(
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
            limit=limit,
            since=since,
        )
        return {"generated_at": datetime.now(timezone.utc), "returned_count": len(events), "events": events}

    @app.get("/agent-runs/{agent_run_id}/activity", response_model=GraphActivityOut)
    async def agent_run_activity(
        agent_run_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        events = [
            event
            for event in repository.list_graph_activity_events(limit=100, since=since)
            if _activity_event_matches_agent_run(event, agent_run_id)
        ][:limit]
        return {"generated_at": datetime.now(timezone.utc), "returned_count": len(events), "events": events}

    @app.get(
        "/graph/activity/stream",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    )
    async def graph_activity_stream(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        limit: int = Query(default=25, ge=1, le=100),
        since: datetime | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> StreamingResponse:
        events = repository.list_graph_activity_events(
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
            limit=limit,
            since=since,
        )

        async def event_stream():
            yield ": heartbeat\n\n"
            for event in events:
                yield f"id: {event['id']}\n"
                yield "event: graph.activity\n"
                yield f"data: {json.dumps(event, sort_keys=True, default=str)}\n\n"

        return StreamingResponse(
            observe_sse_stream(event_stream(), app.state.telemetry, stream_kind="graph.activity.compatibility"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    app.include_router(create_attention_router(repo))

    app.include_router(create_actions_router(repo))

    @app.get("/insights", response_model=GraphInsightsOut)
    async def insights(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        return repository.insights(graph_id, normalize_graph_lens(lens))

    @app.get("/graph/neighborhood/{node_id}", response_model=GraphNeighborhoodOut)
    async def graph_neighborhood(
        node_id: str,
        depth: int = Query(default=1, ge=1, le=2),
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        neighborhood = repository.neighborhood(node_id, depth=depth, limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))
        if neighborhood is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        return neighborhood

    @app.get("/graph/path", response_model=GraphPathOut)
    async def graph_path(
        source_node_id: str = Query(min_length=1),
        target_node_id: str = Query(min_length=1),
        max_depth: int = Query(default=4, ge=1, le=6),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        path = repository.path(source_node_id, target_node_id, max_depth=max_depth, graph_id=graph_id, lens=normalize_graph_lens(lens))
        if path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source or target node not found")
        return path

    @app.get("/extraction-lenses")
    async def extraction_lenses(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
    ) -> dict[str, list[ExtractionLensOut]]:
        return {"extraction_lenses": EXTRACTION_LENS_DESCRIPTORS}

    @app.get("/graph-lenses")
    async def graph_lenses(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
    ) -> dict[str, list[GraphLensOut]]:
        return {"graph_lenses": GRAPH_LENS_DESCRIPTORS}

    @app.get("/graph/settings", response_model=GraphSettingsOut)
    async def graph_settings(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.graph_settings()

    @app.patch("/graph/settings", response_model=GraphSettingsOut)
    async def update_graph_settings(
        payload: GraphSettingsUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.update_graph_settings(payload)

    app.include_router(create_planning_router(repo, provider_registry_factory=configured_provider_registry))

    app.include_router(create_agent_context_router(repo, telemetry=app.state.telemetry))

    app.include_router(create_agent_tools_router(repo))

    app.include_router(create_retrieval_router(repo, provider_registry_factory=configured_provider_registry))

    app.include_router(create_connector_router(repo, llm_provider_factory=build_llm_provider))

    app.include_router(create_sources_router(repo))

    app.include_router(create_review_router(repo))

    @app.get("/search")
    async def search(
        q: str = Query(min_length=1),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[object]]:
        return repository.search(q, graph_id)

    @app.get("/export", response_model=ExportBundle)
    async def export(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.export_bundle(graph_id)

    @app.get("/backup", response_model=BackupBundle)
    async def backup(
        include_agent_context_content: bool = Query(default=False),
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.backup_bundle(actor_id=user.id, include_agent_context_content=include_agent_context_content)

    @app.post("/restore", response_model=ExportBundle)
    async def restore(
        payload: BackupBundle,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.restore_bundle(payload.bundle, actor_id=user.id)

    @app.post("/import", response_model=ExportBundle)
    async def import_bundle(
        payload: ImportBundle,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        for source in payload.sources:
            repository.create_source(source)
        for proposal in payload.proposals:
            repository.create_proposal(proposal, user.id)
        return repository.export_bundle()

    app.include_router(create_v1_router(repo, object_store=app.state.object_store, settings=settings))
    legacy_routes = [
        route
        for route in list(app.routes)
        if isinstance(route, APIRoute)
        and not route.path.startswith("/api/v1")
        and route.path not in {"/health", "/version"}
    ]
    for route in legacy_routes:
        app.add_api_route(
            f"/api/v1{route.path}",
            route.endpoint,
            methods=route.methods,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=["Graphview V1 Compatibility"],
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            deprecated=False,
            name=f"v1-{route.name}",
        )

    return app


app = create_app()
