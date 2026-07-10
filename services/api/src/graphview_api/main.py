import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from graphview_api.agent_context import create_agent_context_router
from graphview_api.actions import create_actions_router
from graphview_api.attention import create_attention_router
from graphview_api.api_v1 import create_v1_router
from graphview_api.auth import (
    OPERATE_PERMISSION,
    READ_PERMISSION,
    REVIEW_PERMISSION,
    WRITE_PERMISSION,
    CurrentUser,
    require_permission,
)
from graphview_api.connector_routes import create_connector_router
from graphview_api.db import create_app_engine
from graphview_api.ingestion import EMBEDDING_MODEL, build_document, embed_text, generate_proposals
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
    AgentActionApprovalCreate,
    AgentActionProposalOut,
    AgentToolCallCreate,
    AgentToolCallOut,
    AgentRunCreate,
    AgentRunOut,
    BackupBundle,
    ExportBundle,
    GraphActivityOut,
    GraphBuildSpecCreate,
    GraphBuildSpecOut,
    GraphQueryAnswerOut,
    GraphQueryCreate,
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
    GraphResearchCreate,
    GraphResearchOut,
    PlanningMessageCreate,
    PlanningSessionCreate,
    PlanningSessionOut,
    ProposalCreate,
    ProviderCredentialUpdate,
    ProviderDescriptorOut,
    SourceCreate,
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

    @app.get("/providers")
    async def providers(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        return {"providers": configured_provider_registry(settings, repository).descriptors()}

    @app.patch("/providers/{provider_id}/credentials")
    async def update_provider_credentials(
        provider_id: str,
        payload: ProviderCredentialUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        try:
            repository.upsert_ai_provider_api_key(provider_id, payload.api_key, make_default=payload.make_default)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return {"providers": configured_provider_registry(settings, repository).descriptors()}

    @app.delete("/providers/{provider_id}/credentials")
    async def delete_provider_credentials(
        provider_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        try:
            repository.delete_ai_provider_api_key(provider_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return {"providers": configured_provider_registry(settings, repository).descriptors()}

    @app.post("/planning-sessions", response_model=PlanningSessionOut, status_code=status.HTTP_201_CREATED)
    async def create_planning_session(
        payload: PlanningSessionCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_planning_session(payload, user.id)

    @app.get("/planning-sessions")
    async def planning_sessions(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[PlanningSessionOut]]:
        return {"planning_sessions": repository.list_planning_sessions(graph_id)}

    @app.get("/planning-sessions/{session_id}", response_model=PlanningSessionOut)
    async def planning_session(
        session_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        session = repository.get_planning_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found")
        return session

    @app.post("/planning-sessions/{session_id}/messages", response_model=PlanningSessionOut)
    async def create_planning_message(
        session_id: str,
        payload: PlanningMessageCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        session = repository.get_planning_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found")
        registry = configured_provider_registry(settings, repository)
        try:
            provider = registry.resolve(payload.provider or session.get("provider"), payload.model or session.get("model"))
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        provider_payload = {
            "title": session["title"],
            "goal": session["goal"],
            "message": payload.content,
            "lens": session["lens"],
        }
        response = await provider.complete(
            system="Create a concise Graphview planning response and a graph build spec. Graph mutations must remain review-gated.",
            user=json.dumps(provider_payload, sort_keys=True),
            response_format="graph_build_spec",
        )
        build_spec = response.structured or {}
        updated = repository.add_planning_message(
            session_id,
            payload,
            actor_id=user.id,
            provider=response.provider,
            model=response.model,
            assistant_content=response.text,
            assistant_metadata={"buildSpec": build_spec, "confidence": response.confidence},
            agent_run_output={"message": response.text, "build_spec": build_spec, "confidence": response.confidence},
        )
        if build_spec:
            repository.upsert_graph_build_spec(
                session_id,
                GraphBuildSpecCreate(
                    title=str(build_spec.get("title") or session["title"]),
                    objective=str(build_spec.get("objective") or session["goal"]),
                    status="draft",
                    spec=build_spec,
                ),
            )
            updated = repository.get_planning_session(session_id) or updated
        return updated

    @app.post("/planning-sessions/{session_id}/build-spec", response_model=GraphBuildSpecOut)
    async def create_graph_build_spec(
        session_id: str,
        payload: GraphBuildSpecCreate,
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.upsert_graph_build_spec(session_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found") from error

    @app.post("/agent-runs", response_model=AgentRunOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_run(
        payload: AgentRunCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        try:
            provider = configured_provider_registry(settings, repository).resolve(payload.provider, payload.model)
            response = await provider.complete(
                system="Execute a Graphview agent run without direct graph mutation.",
                user=json.dumps(payload.input, sort_keys=True),
                response_format="text",
            )
            return repository.create_agent_run(
                payload,
                actor_id=user.id,
                provider=response.provider,
                model=response.model,
                output={"message": response.text, "structured": response.structured, "confidence": response.confidence},
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    @app.get("/agent-runs/{agent_run_id}", response_model=AgentRunOut)
    async def agent_run(
        agent_run_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        run = repository.get_agent_run(agent_run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
        return run

    @app.get("/agent-tools")
    async def agent_tools(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
    ) -> dict[str, list[dict[str, object]]]:
        return {
            "tools": [
                {"kind": "graph_query", "label": "Query graph", "mutates_graph": False},
                {"kind": "source_search", "label": "Search sources", "mutates_graph": False},
                {"kind": "source_open", "label": "Open source", "mutates_graph": False},
                {"kind": "research_run", "label": "Run research", "mutates_graph": False},
                {"kind": "proposal_create", "label": "Create proposal", "mutates_graph": True, "review_gated": True},
                {"kind": "review_action", "label": "Review action", "mutates_graph": True, "review_gated": True},
                {"kind": "connector_sync", "label": "Sync connector", "mutates_graph": True, "review_gated": True},
                {"kind": "graph_layout", "label": "Change graph layout", "mutates_graph": False},
            ]
        }

    app.include_router(create_agent_context_router(repo, telemetry=app.state.telemetry))

    @app.post("/agent-tool-calls", response_model=AgentToolCallOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_tool_call(
        payload: AgentToolCallCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        timestamp = datetime.now(timezone.utc)
        tool_input = payload.input
        graph_id = tool_input.get("graph_id") if isinstance(tool_input.get("graph_id"), str) else None
        lens = normalize_graph_lens(tool_input.get("lens") if isinstance(tool_input.get("lens"), str) else "all")
        citations: list[dict[str, object]] = []
        affected_graph_ids: list[str] = []
        resulting_proposal_id: str | None = None
        call_status = "succeeded"
        summary = ""

        if payload.kind == "graph_query":
            question = str(tool_input.get("question") or tool_input.get("query") or "")
            if not question.strip():
                call_status = "blocked"
                summary = "Graph query requires a question."
            else:
                context = repository.graph_query_context(
                    GraphQueryCreate(
                        question=question,
                        graph_id=graph_id,
                        lens=lens,
                        node_id=tool_input.get("node_id") if isinstance(tool_input.get("node_id"), str) else None,
                        source_id=tool_input.get("source_id") if isinstance(tool_input.get("source_id"), str) else None,
                    )
                )
                citations = context["citations"]
                affected_graph_ids = [node["id"] for node in context["nodes"]] + [source["id"] for source in context["sources"]]
                summary = f"Collected {len(citations)} citations from graph context."
        elif payload.kind == "source_search":
            query = str(tool_input.get("query") or tool_input.get("q") or "")
            found_sources = repository.list_sources(query=query or None, graph_id=graph_id)[:8]
            citations = [
                {
                    "id": f"source-{source['id']}",
                    "label": source["title"],
                    "source_id": source["id"],
                    "source_title": source["title"],
                    "url": source.get("remote_url") or source.get("uri"),
                }
                for source in found_sources
            ]
            affected_graph_ids = [source["id"] for source in found_sources]
            summary = f"Found {len(found_sources)} matching sources."
        elif payload.kind == "source_open":
            source_id = str(tool_input.get("source_id") or "")
            source = repository.get_source(source_id) if source_id else None
            if source is None:
                call_status = "blocked"
                summary = "Source not found."
            else:
                chunks = repository.list_source_chunks(source_id=source_id, graph_id=graph_id)[:8]
                citations = [
                    {
                        "id": f"chunk-{chunk['id']}",
                        "label": source["title"],
                        "source_id": source["id"],
                        "source_title": source["title"],
                        "source_chunk_id": chunk["id"],
                        "locator": chunk["locator"],
                        "quote": chunk["text"][:360],
                    }
                    for chunk in chunks
                ]
                affected_graph_ids = [source_id]
                summary = f"Opened {source['title']} with {len(chunks)} readable chunks."
        elif payload.kind == "proposal_create":
            source_id = str(tool_input.get("source_id") or "")
            proposed_value = tool_input.get("proposed_value") if isinstance(tool_input.get("proposed_value"), dict) else None
            if source_id and proposed_value:
                proposal = repository.create_proposal(
                    ProposalCreate(
                        source_id=source_id,
                        kind=tool_input.get("kind") if tool_input.get("kind") in {"content_node", "semantic_edge"} else "content_node",
                        proposed_value=proposed_value,
                        confidence=tool_input.get("confidence") if isinstance(tool_input.get("confidence"), int | float) else None,
                        locator=tool_input.get("locator") if isinstance(tool_input.get("locator"), str) else "agent tool",
                    ),
                    user.id,
                )
                call_status = "pending_review"
                resulting_proposal_id = proposal["id"]
                affected_graph_ids = [proposal["id"]]
                summary = "Created a review-gated graph proposal."
            else:
                call_status = "pending_review"
                summary = "Proposal creation is review-gated and needs source_id plus proposed_value."
        elif payload.kind in {"research_run", "review_action", "connector_sync"}:
            call_status = "pending_review"
            summary = f"{payload.kind.replace('_', ' ')} is queued for review-gated execution."
        elif payload.kind == "graph_layout":
            summary = f"Prepared {tool_input.get('layout') or 'overview'} graph layout update."

        return {
            "id": f"tool_{uuid4().hex[:20]}",
            "kind": payload.kind,
            "input": tool_input,
            "status": call_status,
            "citations": citations,
            "affected_graph_ids": affected_graph_ids,
            "resulting_proposal_id": resulting_proposal_id,
            "summary": summary,
            "started_at": timestamp,
            "finished_at": timestamp,
        }

    @app.post("/agent-runs/{agent_run_id}/approve-action", response_model=AgentActionProposalOut)
    async def approve_agent_action(
        agent_run_id: str,
        payload: AgentActionApprovalCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        run = repository.get_agent_run(agent_run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
        action = repository.get_agent_action(payload.action_proposal_id)
        if action is None or action["agent_run_id"] != agent_run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        try:
            return repository.approve_agent_action(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found") from error

    @app.post("/graph/query", response_model=GraphQueryAnswerOut)
    async def graph_query(
        payload: GraphQueryCreate,
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if graph_id or lens:
            payload = payload.model_copy(
                update={"graph_id": graph_id or payload.graph_id, "lens": lens or payload.lens}
            )
        context = repository.graph_query_context(payload)
        try:
            provider = configured_provider_registry(settings, repository).resolve(payload.provider, payload.model)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        response = await provider.complete(
            system="Answer using only the supplied Graphview graph context and citations. Do not mutate graph state.",
            user=json.dumps(
                {"question": payload.question, "citations": context["citations"], "nodes": context["nodes"], "sources": context["sources"]},
                sort_keys=True,
                default=str,
            ),
            response_format="graph_query",
        )
        output = {
            "answer": response.structured.get("answer") or response.text,
            "confidence": response.structured.get("confidence", response.confidence),
            "citations": context["citations"],
        }
        run = repository.create_agent_run(
            AgentRunCreate(kind="graph_query", input={"question": payload.question, "graph_id": payload.graph_id, "lens": payload.lens}),
            actor_id=user.id,
            provider=response.provider,
            model=response.model,
            output=output,
        )
        return {"answer": output["answer"], "confidence": output["confidence"], "citations": context["citations"], "agent_run": run}

    @app.post("/graph/research", response_model=GraphResearchOut, status_code=status.HTTP_201_CREATED)
    async def graph_research(
        payload: GraphResearchCreate,
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if graph_id or lens:
            payload = payload.model_copy(
                update={"graph_id": graph_id or payload.graph_id, "lens": lens or payload.lens}
            )
        try:
            provider = configured_provider_registry(settings, repository).resolve(payload.provider, payload.model)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        response = await provider.complete(
            system="Create a concise research note that can be ingested into Graphview as reviewable proposals.",
            user=json.dumps({"query": payload.query, "source_policy": payload.source_policy, "lens": payload.lens}, sort_keys=True),
            response_format="research",
        )
        title = str(response.structured.get("title") or f"AI research note: {payload.query[:96]}")
        content = str(response.structured.get("content") or response.text)
        document = await build_document(kind="markdown", title=title, content=content)
        generated = [
            proposal.__dict__
            for proposal in generate_proposals(
                document,
                limit=6,
                extraction_lenses=[payload.lens] if payload.lens in {"research", "engineering", "ops"} else None,
            )
        ]
        ingestion = repository.create_ingestion_result(
            source_payload=SourceCreate(
                kind="markdown",
                title=title,
                uri=f"agent-research://{payload.query[:80]}",
                checksum=document.checksum,
                metadata={"agentProvider": response.provider, "agentModel": response.model, "researchQuery": payload.query},
            ),
            generated_proposals=generated,
            embedding_model=EMBEDDING_MODEL,
            embedding_vector=embed_text(document.text),
            actor_id=user.id,
            source_text=document.text,
            graph_id=payload.graph_id,
        )
        run = repository.create_agent_run(
            AgentRunCreate(kind="research", input={"query": payload.query, "graph_id": payload.graph_id, "lens": payload.lens}),
            actor_id=user.id,
            provider=response.provider,
            model=response.model,
            output={
                "message": response.text,
                "source_id": ingestion["source"]["id"],
                "proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]],
                "confidence": response.confidence,
            },
            status="waiting_for_review",
        )
        task = repository.create_research_task(
            payload,
            actor_id=user.id,
            provider=response.provider,
            model=response.model,
            agent_run_id=run["id"],
            result={"source_id": ingestion["source"]["id"], "proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]]},
        )
        if ingestion["proposals"]:
            repository.create_agent_action_proposal(
                agent_run_id=run["id"],
                action_type="review_proposals",
                title="Review AI research proposals",
                summary=f"{len(ingestion['proposals'])} proposals are ready for human review.",
                payload={"proposal_ids": [proposal["id"] for proposal in ingestion["proposals"]]},
                citations=[],
                confidence=response.confidence,
            )
            run = repository.get_agent_run(run["id"]) or run
        return {
            "research_task": task,
            "agent_run": run,
            "source": ingestion["source"],
            "ingestion_run": ingestion["ingestion_run"],
            "proposals": ingestion["proposals"],
        }

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
