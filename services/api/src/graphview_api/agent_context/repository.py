from __future__ import annotations

from typing import Protocol

from graphview_api.schemas import (
    AgentContextClientCreate,
    AgentContextEventBatchCreate,
    AgentContextSessionCreate,
    AgentContextSessionUpdate,
)


class AgentContextRepositoryPort(Protocol):
    def authenticate_agent_context_token(self, token: str) -> dict | None: ...

    def create_agent_context_client(self, payload: AgentContextClientCreate, *, actor_id: str) -> dict: ...

    def create_agent_context_session(self, payload: AgentContextSessionCreate, *, client: dict) -> dict: ...

    def update_agent_context_session(
        self,
        session_id: str,
        payload: AgentContextSessionUpdate,
        *,
        client: dict,
    ) -> dict: ...

    def ingest_agent_context_events(self, payload: AgentContextEventBatchCreate, *, client: dict) -> dict: ...

    def list_agent_context_sessions(self, *, limit: int = 50) -> list[dict]: ...

    def get_agent_context_session(self, session_id: str) -> dict | None: ...

    def list_agent_context_events(
        self,
        session_id: str,
        *,
        limit: int = 100,
        since_sequence: int | None = None,
    ) -> list[dict]: ...

    def agent_context_event_sequence(self, session_id: str, event_id: str) -> int | None: ...

    def agent_context_graph(self, session_id: str) -> dict: ...

    def agent_context_artifact_content(self, artifact_id: str) -> dict | None: ...

    def run_agent_context_retention(self) -> dict: ...
