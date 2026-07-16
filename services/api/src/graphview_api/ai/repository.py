from __future__ import annotations

from typing import Protocol

from graphview_api.schemas import (
    AgentActionApprovalCreate,
    AgentRunCreate,
    GraphBuildSpecCreate,
    GraphQueryCreate,
    PlanningMessageCreate,
    PlanningSessionCreate,
    ProposalCreate,
    GraphResearchCreate,
    SourceCreate,
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

    def get_agent_action(self, action_id: str) -> dict | None: ...

    def approve_agent_action(self, payload: AgentActionApprovalCreate, reviewer_id: str) -> dict: ...

    def create_ingestion_result(
        self,
        *,
        source_payload: SourceCreate,
        generated_proposals: list[dict],
        embedding_model: str,
        embedding_vector: list[float],
        actor_id: str,
        source_text: str,
        graph_id: str | None = None,
    ) -> dict: ...

    def create_research_task(
        self,
        payload: GraphResearchCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        agent_run_id: str,
        result: dict,
    ) -> dict: ...

    def create_agent_action_proposal(self, **kwargs) -> dict: ...
