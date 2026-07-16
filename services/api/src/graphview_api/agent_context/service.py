from __future__ import annotations

from graphview_api.agent_context.repository import AgentContextRepositoryPort
from graphview_api.schemas import (
    AgentContextClientCreate,
    AgentContextEventBatchCreate,
    AgentContextSessionCreate,
    AgentContextSessionUpdate,
)

CAPTURE_SCOPE = "context:capture"


class AgentContextService:
    def __init__(self, repository: AgentContextRepositoryPort) -> None:
        self.repository = repository

    def authenticate_capture(self, token: str) -> dict:
        client = self.repository.authenticate_agent_context_token(token)
        if client is None or CAPTURE_SCOPE not in client.get("scopes", []):
            raise PermissionError("Invalid agent context token")
        return client

    def create_client(self, payload: AgentContextClientCreate, *, actor_id: str) -> dict:
        return self.repository.create_agent_context_client(payload, actor_id=actor_id)

    def create_session(self, payload: AgentContextSessionCreate, *, client: dict) -> dict:
        return self.repository.create_agent_context_session(payload, client=client)

    def update_session(self, session_id: str, payload: AgentContextSessionUpdate, *, client: dict) -> dict:
        return self.repository.update_agent_context_session(session_id, payload, client=client)

    def ingest_events(self, payload: AgentContextEventBatchCreate, *, client: dict) -> dict:
        return self.repository.ingest_agent_context_events(payload, client=client)

    def sessions(self, *, limit: int) -> dict[str, list[dict]]:
        return {"sessions": self.repository.list_agent_context_sessions(limit=limit)}

    def session(self, session_id: str) -> dict:
        value = self.repository.get_agent_context_session(session_id)
        if value is None:
            raise KeyError(session_id)
        return value

    def events(self, session_id: str, *, limit: int, since_sequence: int | None) -> dict[str, list[dict]]:
        self.session(session_id)
        return {
            "events": self.repository.list_agent_context_events(
                session_id,
                limit=limit,
                since_sequence=since_sequence,
            )
        }

    def graph(self, session_id: str) -> dict:
        return self.repository.agent_context_graph(session_id)

    def artifact_content(self, artifact_id: str) -> dict:
        value = self.repository.agent_context_artifact_content(artifact_id)
        if value is None:
            raise KeyError(artifact_id)
        return value

    def replay_events(
        self,
        session_id: str,
        *,
        limit: int,
        since_sequence: int | None,
        last_event_id: str | None,
    ) -> list[dict]:
        self.session(session_id)
        if last_event_id:
            replay_sequence = self.repository.agent_context_event_sequence(session_id, last_event_id)
            if replay_sequence is None:
                raise ValueError("Agent context replay cursor is no longer available")
            since_sequence = max(since_sequence or 0, replay_sequence)
        return self.repository.list_agent_context_events(
            session_id,
            limit=limit,
            since_sequence=since_sequence,
        )

    def retention(self) -> dict:
        return self.repository.run_agent_context_retention()
