import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from graphview_api.agent_context import create_agent_context_router
from graphview_api.api_v1 import create_v1_router
from graphview_api.auth import (
    OPERATE_PERMISSION,
    READ_PERMISSION,
    REVIEW_PERMISSION,
    WRITE_PERMISSION,
    CurrentUser,
    require_permission,
)
from graphview_api.connectors import connector_descriptors
from graphview_api.db import create_app_engine
from graphview_api.ingestion import EMBEDDING_MODEL, build_document, embed_text, generate_proposals
from graphview_api.identity import IdentityService
from graphview_api.identity.router import create_identity_router
from graphview_api.http_middleware import install_http_middleware
from graphview_api.lenses import EXTRACTION_LENS_DESCRIPTORS, GRAPH_LENS_DESCRIPTORS, normalize_graph_lens
from graphview_api.llm import build_llm_provider, build_provider_registry
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate, JobOut
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.connector_state import ConnectorStateRepository
from graphview_api.observability import RequestMetrics, configure_telemetry, observe_sse_stream
from graphview_api.object_store import build_object_store
from graphview_api.operations import create_health_router, create_operations_router
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    AgentActionApprovalCreate,
    AgentActionProposalOut,
    ActionProposalCreate,
    ActionProposalDecision,
    ActionProposalOut,
    ActionRunCreate,
    ActionRunOut,
    AlertAssign,
    AlertOut,
    AttentionOut,
    AttentionTransition,
    AgentToolCallCreate,
    AgentToolCallOut,
    AgentRunCreate,
    AgentRunOut,
    BackupBundle,
    ConnectorAccountCreate,
    ConnectorAccountOut,
    ConnectorCredentialUpdate,
    ConnectorSyncCreate,
    ConnectorSyncRunOut,
    ConnectorTargetCreate,
    ConnectorTargetOut,
    ConnectorTargetUpdate,
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
    IngestionCreate,
    IngestionResultOut,
    IngestionRunOut,
    LineageTraceOut,
    DecisionRecordCreate,
    DecisionRecordOut,
    ExtractionLensOut,
    FeedbackEventCreate,
    FeedbackEventOut,
    GraphResearchCreate,
    GraphResearchOut,
    ObservationCreate,
    ObservationOut,
    OutcomeCreate,
    OutcomeOut,
    OwnerCreate,
    OwnerOut,
    OwnerUpdate,
    PlanningMessageCreate,
    PlanningSessionCreate,
    PlanningSessionOut,
    ProposalCreate,
    ProviderCredentialUpdate,
    ProviderDescriptorOut,
    ProposalOut,
    RoutingPolicyCreate,
    RoutingPolicyOut,
    RoutingPolicyUpdate,
    ReviewActivityOut,
    ReviewDashboardOut,
    ReviewQueueOut,
    ReviewDecisionCreate,
    ReviewDecisionOut,
    SignalCreate,
    SignalOut,
    SourceReviewCoverageOut,
    SourceCreate,
    SourceChunkOut,
    SourceOut,
    SourceUpdate,
)
from graphview_api.settings import Settings, get_settings
from graphview_api.secret_store import build_secret_store
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

    @app.get("/signals")
    async def signals(
        kind: str | None = Query(default=None),
        status: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[SignalOut]]:
        return {"signals": repository.list_signals(kind=kind, status=status, limit=limit)}

    @app.get("/signals/{signal_id}", response_model=SignalOut)
    async def signal(
        signal_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        item = repository.get_signal(signal_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
        return item

    @app.post("/signals", response_model=SignalOut, status_code=status.HTTP_201_CREATED)
    async def create_signal(
        payload: SignalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_signal(payload, user.id)

    @app.get("/observations")
    async def observations(
        signal_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ObservationOut]]:
        return {"observations": repository.list_observations(signal_id=signal_id, limit=limit)}

    @app.post("/observations", response_model=ObservationOut, status_code=status.HTTP_201_CREATED)
    async def create_observation(
        payload: ObservationCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_observation(payload, user.id)

    @app.get("/alerts")
    async def alerts(
        status_filter: str | None = Query(default=None, alias="status"),
        severity: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[AlertOut]]:
        return {"alerts": repository.list_alerts(status=status_filter, severity=severity, limit=limit)}

    @app.post("/alerts/{alert_id}/assign", response_model=AlertOut)
    async def assign_alert(
        alert_id: str,
        payload: AlertAssign,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        item = repository.assign_alert(alert_id, payload, user.id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return item

    @app.get("/attention", response_model=AttentionOut)
    async def attention(
        status_filter: str | None = Query(default=None, alias="status"),
        severity: str | None = Query(default=None),
        owner_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.list_attention(status=status_filter, severity=severity, owner_id=owner_id, limit=limit)

    @app.post("/attention/{attention_item_id}/transition", response_model=AttentionOut)
    async def transition_attention(
        attention_item_id: str,
        payload: AttentionTransition,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        item = repository.transition_attention(attention_item_id, payload, user.id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attention item not found")
        return {"generated_at": datetime.now(timezone.utc), "returned_count": 1, "items": [item]}

    @app.get("/owners")
    async def owners(
        scope_kind: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[OwnerOut]]:
        return {"owners": repository.list_owners(scope_kind=scope_kind, limit=limit)}

    @app.post("/owners", response_model=OwnerOut, status_code=status.HTTP_201_CREATED)
    async def create_owner(
        payload: OwnerCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_owner(payload)

    @app.patch("/owners/{owner_id}", response_model=OwnerOut)
    async def update_owner(
        owner_id: str,
        payload: OwnerUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        owner = repository.update_owner(owner_id, payload)
        if owner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
        return owner

    @app.get("/routing-policies")
    async def routing_policies(
        enabled: bool | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[RoutingPolicyOut]]:
        return {"routing_policies": repository.list_routing_policies(enabled=enabled, limit=limit)}

    @app.post("/routing-policies", response_model=RoutingPolicyOut, status_code=status.HTTP_201_CREATED)
    async def create_routing_policy(
        payload: RoutingPolicyCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_routing_policy(payload)

    @app.patch("/routing-policies/{policy_id}", response_model=RoutingPolicyOut)
    async def update_routing_policy(
        policy_id: str,
        payload: RoutingPolicyUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        policy = repository.update_routing_policy(policy_id, payload)
        if policy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing policy not found")
        return policy

    @app.get("/decision-records")
    async def decision_records(
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[DecisionRecordOut]]:
        return {"decision_records": repository.list_decision_records(limit=limit)}

    @app.post("/decision-records", response_model=DecisionRecordOut, status_code=status.HTTP_201_CREATED)
    async def create_decision_record(
        payload: DecisionRecordCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_decision_record(payload, user.id)

    @app.get("/action-proposals")
    async def action_proposals(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ActionProposalOut]]:
        return {"action_proposals": repository.list_action_proposals(status=status_filter, limit=limit)}

    @app.post("/action-proposals", response_model=ActionProposalOut, status_code=status.HTTP_201_CREATED)
    async def create_action_proposal(
        payload: ActionProposalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_action_proposal(payload, user.id)

    @app.post("/action-proposals/{action_proposal_id}/approve", response_model=ActionProposalOut)
    async def approve_action_proposal(
        action_proposal_id: str,
        payload: ActionProposalDecision,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            item = repository.decide_action_proposal(action_proposal_id, "approved", payload, user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        return item

    @app.post("/action-proposals/{action_proposal_id}/reject", response_model=ActionProposalOut)
    async def reject_action_proposal(
        action_proposal_id: str,
        payload: ActionProposalDecision,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            item = repository.decide_action_proposal(action_proposal_id, "rejected", payload, user.id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found")
        return item

    @app.get("/action-runs")
    async def action_runs(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ActionRunOut]]:
        return {"action_runs": repository.list_action_runs(status=status_filter, limit=limit)}

    @app.post("/action-runs", response_model=ActionRunOut, status_code=status.HTTP_201_CREATED)
    async def create_action_run(
        payload: ActionRunCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.create_action_run(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @app.get("/outcomes")
    async def outcomes(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[OutcomeOut]]:
        return {"outcomes": repository.list_outcomes(status=status_filter, limit=limit)}

    @app.post("/action-runs/{action_run_id}/outcome", response_model=OutcomeOut, status_code=status.HTTP_201_CREATED)
    async def create_action_run_outcome(
        action_run_id: str,
        payload: OutcomeCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.create_outcome(payload, user.id, action_run_id=action_run_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action run not found") from error

    @app.post("/feedback-events", response_model=FeedbackEventOut, status_code=status.HTTP_201_CREATED)
    async def create_feedback_event(
        payload: FeedbackEventCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_feedback_event(payload, user.id)

    @app.get("/feedback-events")
    async def feedback_events(
        kind: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[FeedbackEventOut]]:
        return {"feedback_events": repository.list_feedback_events(kind=kind, limit=limit)}

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

    @app.get("/connectors")
    async def connectors(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
    ) -> dict[str, list[dict[str, object]]]:
        return {"connectors": connector_descriptors()}

    @app.get("/connector-accounts")
    async def connector_accounts(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ConnectorAccountOut]]:
        return {"connector_accounts": repository.list_connector_accounts()}

    @app.post("/connector-accounts", response_model=ConnectorAccountOut, status_code=status.HTTP_201_CREATED)
    async def create_connector_account(
        payload: ConnectorAccountCreate,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_connector_account(payload, user.id)

    @app.patch("/connector-accounts/{account_id}/credentials", response_model=ConnectorAccountOut)
    async def update_connector_account_credentials(
        account_id: str,
        payload: ConnectorCredentialUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.update_connector_account_tokens(
                account_id,
                payload.token_json,
                project_id="project-default",
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @app.delete("/connector-accounts/{account_id}/credentials", response_model=ConnectorAccountOut)
    async def delete_connector_account_credentials(
        account_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.clear_connector_account_tokens(account_id, project_id="project-default")
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @app.get("/connector-targets")
    async def connector_targets(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ConnectorTargetOut]]:
        return {"connector_targets": repository.list_connector_targets()}

    @app.post("/connector-targets", response_model=ConnectorTargetOut, status_code=status.HTTP_201_CREATED)
    async def create_connector_target(
        payload: ConnectorTargetCreate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.create_connector_target(payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector account not found") from error

    @app.patch("/connector-targets/{target_id}", response_model=ConnectorTargetOut)
    async def update_connector_target(
        target_id: str,
        payload: ConnectorTargetUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        target = repository.update_connector_target(target_id, payload)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        return target

    @app.get("/connector-sync-runs")
    async def connector_sync_runs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ConnectorSyncRunOut]]:
        return {"connector_sync_runs": repository.list_connector_sync_runs()}

    @app.get("/connector-sync-runs/{sync_run_id}", response_model=ConnectorSyncRunOut)
    async def connector_sync_run(
        sync_run_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        sync_run = repository.get_connector_sync_run(sync_run_id)
        if sync_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector sync run not found")
        return sync_run

    @app.post("/connector-sync-runs", status_code=status.HTTP_201_CREATED)
    async def create_connector_sync_run(
        payload: ConnectorSyncCreate,
        response: Response,
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if settings.environment in {"local", "test", "development"}:
            try:
                return await GraphJobExecutor(repository, settings, llm_provider_factory=build_llm_provider).connector_sync(
                    payload.target_id,
                    actor_id=user.id,
                    worker_id="api-development-compatibility",
                    retry_attempt=1,
                )
            except KeyError as error:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found") from error
        bundle = repository.connector_target_bundle(payload.target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        _, target, _ = bundle
        response.status_code = status.HTTP_202_ACCEPTED
        ConnectorStateRepository(repository.engine).mark_queued(payload.target_id)
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"connector-sync:{payload.target_id}:{target.get('updated_at')}",
                payload={"project_id": target["project_id"], "target_id": payload.target_id, "actor_id": user.id},
            ),
            project_id=target["project_id"],
        )

    @app.get("/source-chunks")
    async def source_chunks(
        source_id: str | None = Query(default=None),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[SourceChunkOut]]:
        return {"source_chunks": repository.list_source_chunks(source_id, graph_id)}

    @app.get("/lineage/{entity_kind}/{entity_id}", response_model=LineageTraceOut)
    async def lineage(
        entity_kind: str,
        entity_id: str,
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        if entity_kind not in {"source", "proposal", "node", "edge"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineage entity not found")
        trace = repository.lineage(entity_kind, entity_id, graph_id)
        if trace is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineage entity not found")
        return trace

    @app.get("/sources")
    async def sources(
        q: str | None = Query(default=None),
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[SourceOut]]:
        return {"sources": repository.list_sources(q, graph_id)}

    @app.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
    async def create_source(
        payload: SourceCreate,
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.create_source(payload, graph_id)

    @app.patch("/sources/{source_id}", response_model=SourceOut)
    async def update_source(
        source_id: str,
        payload: SourceUpdate,
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        source = repository.update_source(source_id, payload)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return source

    @app.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_source(
        source_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> None:
        if not repository.delete_source(source_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    @app.get("/ingestion-runs")
    async def ingestion_runs(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[IngestionRunOut]]:
        return {"ingestion_runs": repository.list_ingestion_runs()}

    @app.post("/ingestion-runs", response_model=IngestionResultOut | JobOut, status_code=status.HTTP_201_CREATED)
    async def create_ingestion_run(
        payload: IngestionCreate,
        response: Response,
        graph_id: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        if settings.environment in {"local", "test", "development"}:
            try:
                return await GraphJobExecutor(repository, settings).ingestion(payload, actor_id=user.id, graph_id=graph_id)
            except ValueError as error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        project_id = (graph_id or "project-default").split(":", 1)[0]
        response.status_code = status.HTTP_202_ACCEPTED
        serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return JobRepository(repository.engine).enqueue(
            JobCreate(
                kind="ingestion.run",
                queue="ingestion",
                idempotency_key=f"ingestion:{project_id}:{hashlib.sha256(serialized.encode()).hexdigest()}",
                payload={"project_id": project_id, "graph_id": graph_id, "actor_id": user.id, "ingestion": payload.model_dump(mode="json")},
            ),
            project_id=project_id,
        )

    @app.get("/proposals")
    async def proposals(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ProposalOut]]:
        return {"proposals": repository.list_proposals(graph_id, lens=normalize_graph_lens(lens))}

    @app.get("/review-queue", response_model=ReviewQueueOut)
    async def review_queue(
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        return repository.review_queue(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    @app.get("/review-dashboard", response_model=ReviewDashboardOut)
    async def review_dashboard(
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        return repository.review_dashboard(graph_id, normalize_graph_lens(lens))

    @app.get("/review-activity", response_model=ReviewActivityOut)
    async def review_activity(
        limit: int = Query(default=10, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        return repository.review_activity(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    @app.get("/review-sources", response_model=SourceReviewCoverageOut)
    async def review_sources(
        limit: int = Query(default=25, ge=1, le=100),
        graph_id: str | None = Query(default=None),
        lens: str | None = Query(default="all"),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, object]:
        return repository.source_review_coverage(limit=limit, graph_id=graph_id, lens=normalize_graph_lens(lens))

    @app.post("/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
    async def create_proposal(
        payload: ProposalCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.create_proposal(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error

    @app.get("/review-decisions")
    async def review_decisions(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict[str, list[ReviewDecisionOut]]:
        return {"review_decisions": repository.list_review_decisions(graph_id)}

    @app.post("/review-decisions", response_model=ReviewDecisionOut, status_code=status.HTTP_201_CREATED)
    async def create_review_decision(
        payload: ReviewDecisionCreate,
        user: CurrentUser = Depends(require_permission(REVIEW_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            return repository.review(payload, user.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

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
