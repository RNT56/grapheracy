import asyncio
from types import SimpleNamespace

import pytest

from graphview_api.ai.service import PlanningService
from graphview_api.schemas import PlanningMessageCreate, ProviderCredentialUpdate
from graphview_api.settings import Settings


class FakeProvider:
    async def complete(self, **_kwargs):
        return SimpleNamespace(
            provider="fake",
            model="fake-model",
            text="Plan ready",
            structured={"title": "Build graph", "objective": "Map evidence", "steps": []},
            confidence=0.9,
        )


class FakeRegistry:
    def descriptors(self):
        return [{"id": "fake", "configured": True}]

    def resolve(self, _provider, _model):
        return FakeProvider()


class RecordingAiRepository:
    def __init__(self) -> None:
        self.session_value = {
            "id": "planning-1",
            "title": "Architecture",
            "goal": "Map boundaries",
            "lens": "engineering",
            "provider": None,
            "model": None,
        }
        self.provider_updates: list[tuple] = []
        self.build_specs: list[tuple] = []

    def upsert_ai_provider_api_key(self, provider_id, api_key, *, make_default=True):
        self.provider_updates.append((provider_id, api_key, make_default))
        return {}

    def delete_ai_provider_api_key(self, provider_id):
        return {}

    def create_planning_session(self, payload, actor_id):
        return {**self.session_value, "created_by": actor_id}

    def list_planning_sessions(self, graph_id=None):
        return [self.session_value]

    def get_planning_session(self, session_id):
        return self.session_value

    def add_planning_message(self, session_id, payload, **kwargs):
        return {**self.session_value, "assistant_content": kwargs["assistant_content"]}

    def upsert_graph_build_spec(self, session_id, payload):
        self.build_specs.append((session_id, payload))
        return {"id": "spec-1"}

    def create_agent_run(self, payload, **kwargs):
        return {"id": "run-1", "kind": payload.kind, **kwargs}

    def get_agent_run(self, agent_run_id):
        return {"id": agent_run_id}


def service(repository: RecordingAiRepository | None = None) -> PlanningService:
    return PlanningService(
        repository or RecordingAiRepository(),
        Settings(database_url="sqlite://"),
        provider_registry_factory=lambda _settings, _repository: FakeRegistry(),
    )


def test_planning_service_owns_provider_credential_transition() -> None:
    repository = RecordingAiRepository()
    result = service(repository).update_provider(
        "fake",
        ProviderCredentialUpdate(api_key="secret", make_default=False),
    )

    assert repository.provider_updates == [("fake", "secret", False)]
    assert result["providers"][0]["configured"] is True


def test_planning_service_builds_review_gated_spec_from_provider_response() -> None:
    repository = RecordingAiRepository()
    result = asyncio.run(
        service(repository).create_message(
            "planning-1",
            PlanningMessageCreate(content="Create a plan"),
            actor_id="planner-1",
        )
    )

    assert result["id"] == "planning-1"
    assert repository.build_specs[0][1].status == "draft"
    assert repository.build_specs[0][1].objective == "Map evidence"


def test_planning_service_exposes_missing_session_as_domain_error() -> None:
    repository = RecordingAiRepository()
    repository.session_value = None

    with pytest.raises(KeyError):
        service(repository).session("missing")
