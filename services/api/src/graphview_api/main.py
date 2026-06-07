import json
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from graphview_api.auth import (
    OPERATE_PERMISSION,
    READ_PERMISSION,
    REVIEW_PERMISSION,
    WRITE_PERMISSION,
    CurrentUser,
    get_current_user,
    require_permission,
)
from graphview_api.connectors import build_connector_proposals, connector_descriptors, fetch_connector_documents
from graphview_api.db import create_app_engine
from graphview_api.ingestion import EMBEDDING_MODEL, NormalizedDocument, build_document, embed_text, generate_proposals
from graphview_api.lenses import EXTRACTION_LENS_DESCRIPTORS, GRAPH_LENS_DESCRIPTORS, normalize_graph_lens
from graphview_api.llm import build_llm_provider, build_provider_registry
from graphview_api.observability import RequestMetrics
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
    ProviderDescriptorOut,
    ResearchTaskOut,
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Graphview API", version=VERSION)
    repository = GraphRepository(
        create_app_engine(settings.database_url),
        secret_key=settings.secret_key,
        auto_commit_threshold=settings.auto_commit_threshold,
        safe_action_types=settings.safe_action_types,
    )
    repository.initialize()
    app.state.repository = repository
    app.state.metrics = RequestMetrics()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observe_requests(request: Request, call_next):
        trace_id = request.headers.get("X-Graphview-Trace-Id") or f"trace_{uuid4().hex[:20]}"
        start = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (perf_counter() - start) * 1000
            app.state.metrics.record(path=request.url.path, status_code=status_code, duration_ms=duration_ms)
            if "response" in locals():
                response.headers["X-Graphview-Trace-Id"] = trace_id

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "graphview-api"}

    def repo() -> GraphRepository:
        return app.state.repository

    @app.get("/version")
    async def version(settings: Settings = Depends(get_settings)) -> dict[str, str]:
        return {"service": "graphview-api", "version": VERSION, "environment": settings.environment}

    @app.get("/observability/ready")
    async def ready(
        settings: Settings = Depends(get_settings),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ):
        try:
            repository.project()
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "service": "graphview-api", "database": "error"},
            )
        return {
            "status": "ready",
            "service": "graphview-api",
            "database": "ok",
            "environment": settings.environment,
            "version": VERSION,
        }

    @app.get("/observability/metrics")
    async def metrics(
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
    ) -> dict[str, object]:
        return app.state.metrics.snapshot()

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
            event_stream(),
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
        settings: Settings = Depends(get_settings),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        return {"providers": build_provider_registry(settings).descriptors()}

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
        registry = build_provider_registry(settings)
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
            provider = build_provider_registry(settings).resolve(payload.provider, payload.model)
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
            provider = build_provider_registry(settings).resolve(payload.provider, payload.model)
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
            provider = build_provider_registry(settings).resolve(payload.provider, payload.model)
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
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        bundle = repository.connector_target_bundle(payload.target_id)
        if bundle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector target not found")
        account, target, token_json = bundle
        try:
            documents = await fetch_connector_documents(account=account, target=target, token_json=token_json)
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Connector sync failed") from error

        graph_settings = repository.graph_settings()
        target_settings = target.get("sync_settings", {})
        llm_enabled = bool(target_settings.get("llm_enabled", graph_settings.get("llm_enabled", settings.llm_enabled)))
        llm_provider = str(target_settings.get("llm_provider") or graph_settings.get("llm_provider") or settings.llm_provider)
        llm_model = str(target_settings.get("llm_model") or graph_settings.get("llm_model") or settings.llm_model)
        llm_base_url = str(target_settings.get("llm_base_url") or graph_settings["settings"].get("llm_base_url") or settings.llm_base_url)
        llm_api_key = target_settings.get("llm_api_key") or graph_settings["settings"].get("llm_api_key") or settings.llm_api_key
        auto_commit_threshold = float(
            target_settings.get("auto_commit_threshold", graph_settings.get("auto_commit_threshold", settings.auto_commit_threshold))
        )
        llm = build_llm_provider(
            enabled=llm_enabled,
            provider=llm_provider,
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=llm_model,
        )

        proposals_by_remote_id: dict[str, list[dict]] = {}
        vectors_by_remote_id: dict[str, list[float]] = {}
        for document in documents:
            proposals = [proposal.__dict__ for proposal in build_connector_proposals(document)]
            proposals.extend(
                proposal.__dict__
                for proposal in generate_proposals(
                    NormalizedDocument(
                        kind=document.source_kind,
                        title=document.title,
                        text=document.text,
                        uri=document.uri or document.remote_url,
                        checksum=document.checksum,
                        locator=document.uri or document.remote_url or document.remote_id,
                    )
                )
            )
            if llm_enabled:
                proposals.extend(
                    proposal.__dict__
                    for proposal in await llm.extract(
                        title=document.title,
                        text=document.text,
                        locator=document.uri or document.remote_url or document.remote_id,
                    )
                )
            proposals_by_remote_id[document.remote_id] = proposals
            vectors_by_remote_id[document.remote_id] = embed_text(document.text)

        return repository.create_connector_sync_result(
            target_id=payload.target_id,
            documents=documents,
            generated_proposals_by_remote_id=proposals_by_remote_id,
            embedding_model=EMBEDDING_MODEL,
            embedding_vectors_by_remote_id=vectors_by_remote_id,
            actor_id=user.id,
            auto_commit_threshold=auto_commit_threshold,
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

    @app.post("/ingestion-runs", response_model=IngestionResultOut, status_code=status.HTTP_201_CREATED)
    async def create_ingestion_run(
        payload: IngestionCreate,
        graph_id: str | None = Query(default=None),
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        try:
            document = await build_document(
                kind=payload.kind,
                title=payload.title,
                content=payload.content,
                uri=payload.uri,
                content_base64=payload.content_base64,
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Source ingestion failed") from error
        generated = [
            proposal.__dict__
            for proposal in generate_proposals(
                document,
                limit=payload.proposal_limit,
                extraction_lenses=payload.extraction_lenses,
                proposal_limit_per_lens=payload.proposal_limit_per_lens,
            )
        ]
        return repository.create_ingestion_result(
            source_payload=SourceCreate(
                kind=payload.kind,
                title=payload.title,
                uri=payload.uri,
                checksum=document.checksum,
            ),
            generated_proposals=generated,
            embedding_model=EMBEDDING_MODEL,
            embedding_vector=embed_text(document.text),
            actor_id=user.id,
            source_text=document.text,
            graph_id=graph_id,
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
        user: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.backup_bundle(actor_id=user.id)

    @app.post("/restore", response_model=ExportBundle)
    async def restore(
        payload: BackupBundle,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo),
    ) -> dict:
        return repository.restore_bundle(payload.bundle)

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

    return app


app = create_app()
