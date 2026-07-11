from __future__ import annotations

from typing import Protocol

from graphview_api.schemas import (
    AgentRunCreate,
    GraphBuildSpecCreate,
    GraphQueryCreate,
    PlanningMessageCreate,
    PlanningSessionCreate,
    ProposalCreate,
)


class AiRepositoryPort(Protocol):
    def upsert_ai_provider_api_key(self, provider_id: str, api_key: str, *, make_default: bool = True) -> dict: ...

    def delete_ai_provider_api_key(self, provider_id: str) -> dict: ...

    def create_planning_session(self, payload: PlanningSessionCreate, actor_id: str) -> dict: ...

    def list_planning_sessions(self, graph_id: str | None = None) -> list[dict]: ...

    def get_planning_session(self, session_id: str) -> dict | None: ...

    def add_planning_message(
        self,
        session_id: str,
        payload: PlanningMessageCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        assistant_content: str,
        assistant_metadata: dict,
        agent_run_output: dict,
    ) -> dict: ...

    def upsert_graph_build_spec(self, session_id: str, payload: GraphBuildSpecCreate) -> dict: ...

    def create_agent_run(
        self,
        payload: AgentRunCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        output: dict,
        status: str = "completed",
    ) -> dict: ...

    def get_agent_run(self, agent_run_id: str) -> dict | None: ...

    def graph_query_context(self, payload: GraphQueryCreate) -> dict: ...

    def list_sources(self, query: str | None = None, graph_id: str | None = None) -> list[dict]: ...

    def get_source(self, source_id: str, project_id: str | None = None) -> dict | None: ...

    def list_source_chunks(self, source_id: str | None = None, graph_id: str | None = None) -> list[dict]: ...

    def create_proposal(self, payload: ProposalCreate, actor_id: str) -> dict: ...
