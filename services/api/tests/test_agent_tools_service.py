from graphview_api.ai.tools_service import AgentToolsService
from graphview_api.schemas import AgentToolCallCreate


class RecordingAgentToolsRepository:
    def __init__(self) -> None:
        self.proposal_actor = None

    def graph_query_context(self, payload):
        return {
            "citations": [{"id": "citation-1"}],
            "nodes": [{"id": "node-1"}],
            "sources": [{"id": "source-1"}],
        }

    def list_sources(self, query=None, graph_id=None):
        return [{"id": "source-1", "title": "Evidence", "uri": "https://example.test/evidence"}]

    def get_source(self, source_id, project_id=None):
        return {"id": source_id, "title": "Evidence"}

    def list_source_chunks(self, source_id=None, graph_id=None):
        return [{"id": "chunk-1", "locator": "p.1", "text": "Grounded evidence text."}]

    def create_proposal(self, payload, actor_id):
        self.proposal_actor = actor_id
        return {"id": "proposal-1"}


def test_agent_tools_service_blocks_empty_graph_query() -> None:
    result = AgentToolsService(RecordingAgentToolsRepository()).execute(
        AgentToolCallCreate(kind="graph_query", input={"question": ""}),
        actor_id="agent-1",
    )

    assert result["status"] == "blocked"
    assert result["citations"] == []


def test_agent_tools_service_opens_source_as_cited_read_only_context() -> None:
    result = AgentToolsService(RecordingAgentToolsRepository()).execute(
        AgentToolCallCreate(kind="source_open", input={"source_id": "source-1"}),
        actor_id="agent-1",
    )

    assert result["status"] == "succeeded"
    assert result["citations"][0]["source_chunk_id"] == "chunk-1"
    assert result["affected_graph_ids"] == ["source-1"]


def test_agent_tools_service_creates_proposals_only_as_pending_review() -> None:
    repository = RecordingAgentToolsRepository()
    result = AgentToolsService(repository).execute(
        AgentToolCallCreate(
            kind="proposal_create",
            input={
                "source_id": "source-1",
                "proposed_value": {"id": "node-1", "label": "Grounded concept", "kind": "concept"},
            },
        ),
        actor_id="agent-1",
    )

    assert result["status"] == "pending_review"
    assert result["resulting_proposal_id"] == "proposal-1"
    assert repository.proposal_actor == "agent-1"
