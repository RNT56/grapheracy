import asyncio
from types import SimpleNamespace

import pytest

from graphview_api.ai.retrieval_service import RetrievalService
from graphview_api.schemas import AgentActionApprovalCreate, GraphQueryCreate, GraphResearchCreate
from graphview_api.settings import Settings


class FakeProvider:
    async def complete(self, *, response_format, **_kwargs):
        if response_format == "graph_query":
            structured = {"answer": "Grounded answer", "confidence": 0.88}
            text = "Grounded answer"
        else:
            structured = {"title": "Research note", "content": "# Finding\nEvidence supports the proposal."}
            text = "Evidence supports the proposal."
        return SimpleNamespace(provider="fake", model="fake-model", text=text, structured=structured, confidence=0.88)


class FakeRegistry:
    def resolve(self, _provider, _model):
        return FakeProvider()


class RecordingRetrievalRepository:
    def __init__(self) -> None:
        self.agent_run_value = {"id": "run-1"}
        self.action_value = {"id": "action-1", "agent_run_id": "run-1"}
        self.created_runs: list[dict] = []
        self.action_proposals: list[dict] = []

    def get_agent_run(self, agent_run_id):
        return self.agent_run_value

    def get_agent_action(self, action_id):
        return self.action_value

    def approve_agent_action(self, payload, reviewer_id):
        return {"id": payload.action_proposal_id, "reviewer_id": reviewer_id, "status": "approved"}

    def graph_query_context(self, payload):
        return {"citations": [{"id": "citation-1"}], "nodes": [{"id": "node-1"}], "sources": []}

    def create_agent_run(self, payload, **kwargs):
        value = {"id": "run-1", "kind": payload.kind, **kwargs}
        self.created_runs.append(value)
        return value

    def create_ingestion_result(self, **kwargs):
        return {
            "source": {"id": "source-1"},
            "ingestion_run": {"id": "ingestion-1"},
            "proposals": [{"id": "proposal-1"}],
        }

    def create_research_task(self, payload, **kwargs):
        return {"id": "research-1", "query": payload.query}

    def create_agent_action_proposal(self, **kwargs):
        self.action_proposals.append(kwargs)
        return {"id": "action-1"}


def service(repository: RecordingRetrievalRepository | None = None) -> RetrievalService:
    return RetrievalService(
        repository or RecordingRetrievalRepository(),
        Settings(database_url="sqlite://"),
        provider_registry_factory=lambda _settings, _repository: FakeRegistry(),
    )


def test_retrieval_service_requires_agent_owned_action_proposal() -> None:
    repository = RecordingRetrievalRepository()
    repository.action_value = {"id": "action-1", "agent_run_id": "other-run"}

    with pytest.raises(KeyError, match="action_proposal"):
        service(repository).approve_action(
            "run-1",
            AgentActionApprovalCreate(action_proposal_id="action-1", decision="approve"),
            reviewer_id="reviewer-1",
        )


def test_retrieval_service_preserves_citations_and_audit_run() -> None:
    repository = RecordingRetrievalRepository()
    result = asyncio.run(
        service(repository).query(
            GraphQueryCreate(question="What supports this?"),
            graph_id="graph-1",
            lens="research",
            actor_id="reader-1",
        )
    )

    assert result["answer"] == "Grounded answer"
    assert result["citations"] == [{"id": "citation-1"}]
    assert repository.created_runs[0]["actor_id"] == "reader-1"


def test_retrieval_service_research_creates_review_gated_action() -> None:
    repository = RecordingRetrievalRepository()
    result = asyncio.run(
        service(repository).research(
            GraphResearchCreate(query="Investigate evidence"),
            graph_id="graph-1",
            lens="research",
            actor_id="researcher-1",
        )
    )

    assert result["proposals"] == [{"id": "proposal-1"}]
    assert repository.action_proposals[0]["action_type"] == "review_proposals"
    assert repository.created_runs[0]["status"] == "waiting_for_review"
