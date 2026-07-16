from __future__ import annotations

import json

from graphview_api.ai.repository import AiRepositoryPort
from graphview_api.schemas import (
    AgentRunCreate,
    GraphBuildSpecCreate,
    PlanningMessageCreate,
    PlanningSessionCreate,
    ProviderCredentialUpdate,
)
from graphview_api.settings import Settings


class PlanningService:
    def __init__(self, repository: AiRepositoryPort, settings: Settings, *, provider_registry_factory) -> None:
        self.repository = repository
        self.settings = settings
        self.provider_registry_factory = provider_registry_factory

    def registry(self):
        return self.provider_registry_factory(self.settings, self.repository)

    def providers(self) -> dict[str, list[dict]]:
        return {"providers": self.registry().descriptors()}

    def update_provider(self, provider_id: str, payload: ProviderCredentialUpdate) -> dict[str, list[dict]]:
        self.repository.upsert_ai_provider_api_key(provider_id, payload.api_key, make_default=payload.make_default)
        return self.providers()

    def delete_provider(self, provider_id: str) -> dict[str, list[dict]]:
        self.repository.delete_ai_provider_api_key(provider_id)
        return self.providers()

    def create_session(self, payload: PlanningSessionCreate, *, actor_id: str) -> dict:
        return self.repository.create_planning_session(payload, actor_id)

    def sessions(self, *, graph_id: str | None) -> dict[str, list[dict]]:
        return {"planning_sessions": self.repository.list_planning_sessions(graph_id)}

    def session(self, session_id: str) -> dict:
        value = self.repository.get_planning_session(session_id)
        if value is None:
            raise KeyError(session_id)
        return value

    async def create_message(
        self,
        session_id: str,
        payload: PlanningMessageCreate,
        *,
        actor_id: str,
    ) -> dict:
        session = self.session(session_id)
        provider = self.registry().resolve(
            payload.provider or session.get("provider"),
            payload.model or session.get("model"),
        )
        response = await provider.complete(
            system="Create a concise Graphview planning response and a graph build spec. Graph mutations must remain review-gated.",
            user=json.dumps(
                {
                    "title": session["title"],
                    "goal": session["goal"],
                    "message": payload.content,
                    "lens": session["lens"],
                },
                sort_keys=True,
            ),
            response_format="graph_build_spec",
        )
        build_spec = response.structured or {}
        updated = self.repository.add_planning_message(
            session_id,
            payload,
            actor_id=actor_id,
            provider=response.provider,
            model=response.model,
            assistant_content=response.text,
            assistant_metadata={"buildSpec": build_spec, "confidence": response.confidence},
            agent_run_output={"message": response.text, "build_spec": build_spec, "confidence": response.confidence},
        )
        if build_spec:
            self.repository.upsert_graph_build_spec(
                session_id,
                GraphBuildSpecCreate(
                    title=str(build_spec.get("title") or session["title"]),
                    objective=str(build_spec.get("objective") or session["goal"]),
                    status="draft",
                    spec=build_spec,
                ),
            )
            updated = self.repository.get_planning_session(session_id) or updated
        return updated

    def create_build_spec(self, session_id: str, payload: GraphBuildSpecCreate) -> dict:
        return self.repository.upsert_graph_build_spec(session_id, payload)

    async def create_agent_run(self, payload: AgentRunCreate, *, actor_id: str) -> dict:
        provider = self.registry().resolve(payload.provider, payload.model)
        response = await provider.complete(
            system="Execute a Graphview agent run without direct graph mutation.",
            user=json.dumps(payload.input, sort_keys=True),
            response_format="text",
        )
        return self.repository.create_agent_run(
            payload,
            actor_id=actor_id,
            provider=response.provider,
            model=response.model,
            output={"message": response.text, "structured": response.structured, "confidence": response.confidence},
        )

    def agent_run(self, agent_run_id: str) -> dict:
        value = self.repository.get_agent_run(agent_run_id)
        if value is None:
            raise KeyError(agent_run_id)
        return value

    def tools(self) -> dict[str, list[dict[str, object]]]:
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
