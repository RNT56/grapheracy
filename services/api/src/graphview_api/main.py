import json

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from graphview_api.agent_context import create_agent_context_router
from graphview_api.actions import create_actions_router
from graphview_api.actions.service import ActionsService
from graphview_api.ai import create_agent_tools_router, create_planning_router, create_retrieval_router
from graphview_api.attention import create_attention_router
from graphview_api.attention.service import AttentionService
from graphview_api.api_v1 import create_v1_router
from graphview_api.connector_routes import create_connector_router
from graphview_api.connector_service import ConnectorService
from graphview_api.db import create_app_engine
from graphview_api.graph import create_graph_activity_router, create_graph_exploration_router
from graphview_api.graph.service import GraphService
from graphview_api.identity import IdentityService
from graphview_api.identity.router import create_identity_router
from graphview_api.http_middleware import install_http_middleware
from graphview_api.llm import build_llm_provider, build_provider_registry
from graphview_api.observability import RequestMetrics, configure_telemetry
from graphview_api.object_store import build_object_store
from graphview_api.operations import create_data_operations_router, create_health_router, create_operations_router
from graphview_api.repository import GraphRepository
from graphview_api.review import create_review_router
from graphview_api.review.service import ReviewService
from graphview_api.settings import Settings, get_settings
from graphview_api.secret_store import build_secret_store
from graphview_api.sources import create_sources_router
from graphview_api.sources.service import SourcesService
from graphview_api.version import VERSION


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

    def graph_service() -> GraphService:
        return GraphService(repo())

    def sources_service() -> SourcesService:
        return SourcesService(repo(), settings)

    def connector_service() -> ConnectorService:
        return ConnectorService(repo(), settings, llm_provider_factory=build_llm_provider)

    def review_service() -> ReviewService:
        return ReviewService(repo())

    def actions_service() -> ActionsService:
        return ActionsService(repo())

    def attention_service() -> AttentionService:
        return AttentionService(repo())

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

    app.include_router(create_graph_activity_router(graph_service, telemetry=app.state.telemetry))

    app.include_router(create_attention_router(attention_service))

    app.include_router(create_actions_router(actions_service))

    app.include_router(create_graph_exploration_router(graph_service))

    app.include_router(create_planning_router(repo, provider_registry_factory=configured_provider_registry))

    app.include_router(create_agent_context_router(repo, telemetry=app.state.telemetry))

    app.include_router(create_agent_tools_router(repo))

    app.include_router(create_retrieval_router(repo, provider_registry_factory=configured_provider_registry))

    app.include_router(create_connector_router(connector_service))

    app.include_router(create_sources_router(sources_service))

    app.include_router(create_review_router(review_service))

    app.include_router(create_data_operations_router(repo))

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
