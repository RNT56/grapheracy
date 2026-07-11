import pytest

from graphview_api.agent_context.service import AgentContextService


class RecordingAgentContextRepository:
    def __init__(self) -> None:
        self.client_value = {"id": "client-1", "scopes": ["context:capture"]}
        self.session_value = {"id": "session-1", "status": "running"}
        self.cursor_value = 4
        self.artifact_value = {"artifact_id": "artifact-1", "text": "retained"}
        self.last_since_sequence = None

    def authenticate_agent_context_token(self, token):
        return self.client_value

    def create_agent_context_client(self, payload, *, actor_id):
        return {"client": self.client_value, "actor_id": actor_id}

    def create_agent_context_session(self, payload, *, client):
        return self.session_value

    def update_agent_context_session(self, session_id, payload, *, client):
        return self.session_value

    def ingest_agent_context_events(self, payload, *, client):
        return {"accepted_count": len(payload.events)}

    def list_agent_context_sessions(self, *, limit=50):
        return [self.session_value]

    def get_agent_context_session(self, session_id):
        return self.session_value

    def list_agent_context_events(self, session_id, *, limit=100, since_sequence=None):
        self.last_since_sequence = since_sequence
        return [{"id": "event-5", "sequence": 5}]

    def agent_context_event_sequence(self, session_id, event_id):
        return self.cursor_value

    def agent_context_graph(self, session_id):
        return {"session_id": session_id, "nodes": []}

    def agent_context_artifact_content(self, artifact_id):
        return self.artifact_value

    def run_agent_context_retention(self):
        return {"purged_count": 1}


def test_agent_context_service_enforces_capture_scope() -> None:
    repository = RecordingAgentContextRepository()
    service = AgentContextService(repository)

    assert service.authenticate_capture("token")["id"] == "client-1"
    repository.client_value = {"id": "client-2", "scopes": ["context:read"]}
    with pytest.raises(PermissionError):
        service.authenticate_capture("token")


def test_agent_context_service_resumes_strictly_after_stable_cursor() -> None:
    repository = RecordingAgentContextRepository()
    events = AgentContextService(repository).replay_events(
        "session-1",
        limit=25,
        since_sequence=2,
        last_event_id="event-4",
    )

    assert repository.last_since_sequence == 4
    assert events[0]["sequence"] == 5


def test_agent_context_service_rejects_expired_cursor_and_missing_content() -> None:
    repository = RecordingAgentContextRepository()
    repository.cursor_value = None
    repository.artifact_value = None
    service = AgentContextService(repository)

    with pytest.raises(ValueError):
        service.replay_events("session-1", limit=25, since_sequence=None, last_event_id="expired")
    with pytest.raises(KeyError):
        service.artifact_content("missing")
