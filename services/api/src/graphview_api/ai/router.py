from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from graphview_api.auth import OPERATE_PERMISSION, READ_PERMISSION, WRITE_PERMISSION, CurrentUser, require_permission
from graphview_api.repository import GraphRepository
from graphview_api.schemas import (
    AgentRunCreate,
    AgentRunOut,
    GraphBuildSpecCreate,
    GraphBuildSpecOut,
    PlanningMessageCreate,
    PlanningSessionCreate,
    PlanningSessionOut,
    ProviderCredentialUpdate,
    ProviderDescriptorOut,
)
from graphview_api.settings import Settings, get_settings


def create_planning_router(
    repo_provider: Callable[[], GraphRepository],
    *,
    provider_registry_factory,
) -> APIRouter:
    router = APIRouter()

    @router.get("/providers")
    async def providers(
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        return {"providers": provider_registry_factory(settings, repository).descriptors()}

    @router.patch("/providers/{provider_id}/credentials")
    async def update_provider_credentials(
        provider_id: str,
        payload: ProviderCredentialUpdate,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        try:
            repository.upsert_ai_provider_api_key(provider_id, payload.api_key, make_default=payload.make_default)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return {"providers": provider_registry_factory(settings, repository).descriptors()}

    @router.delete("/providers/{provider_id}/credentials")
    async def delete_provider_credentials(
        provider_id: str,
        _: CurrentUser = Depends(require_permission(OPERATE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, list[ProviderDescriptorOut]]:
        try:
            repository.delete_ai_provider_api_key(provider_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return {"providers": provider_registry_factory(settings, repository).descriptors()}

    @router.post("/planning-sessions", response_model=PlanningSessionOut, status_code=status.HTTP_201_CREATED)
    async def create_planning_session(
        payload: PlanningSessionCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        return repository.create_planning_session(payload, user.id)

    @router.get("/planning-sessions")
    async def planning_sessions(
        graph_id: str | None = Query(default=None),
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict[str, list[PlanningSessionOut]]:
        return {"planning_sessions": repository.list_planning_sessions(graph_id)}

    @router.get("/planning-sessions/{session_id}", response_model=PlanningSessionOut)
    async def planning_session(
        session_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        session = repository.get_planning_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found")
        return session

    @router.post("/planning-sessions/{session_id}/messages", response_model=PlanningSessionOut)
    async def create_planning_message(
        session_id: str,
        payload: PlanningMessageCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        session = repository.get_planning_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found")
        registry = provider_registry_factory(settings, repository)
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

    @router.post("/planning-sessions/{session_id}/build-spec", response_model=GraphBuildSpecOut)
    async def create_graph_build_spec(
        session_id: str,
        payload: GraphBuildSpecCreate,
        _: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        try:
            return repository.upsert_graph_build_spec(session_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning session not found") from error

    @router.post("/agent-runs", response_model=AgentRunOut, status_code=status.HTTP_201_CREATED)
    async def create_agent_run(
        payload: AgentRunCreate,
        user: CurrentUser = Depends(require_permission(WRITE_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
        settings: Settings = Depends(get_settings),
    ) -> dict:
        try:
            provider = provider_registry_factory(settings, repository).resolve(payload.provider, payload.model)
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

    @router.get("/agent-runs/{agent_run_id}", response_model=AgentRunOut)
    async def agent_run(
        agent_run_id: str,
        _: CurrentUser = Depends(require_permission(READ_PERMISSION)),
        repository: GraphRepository = Depends(repo_provider),
    ) -> dict:
        run = repository.get_agent_run(agent_run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
        return run

    @router.get("/agent-tools")
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

    return router
