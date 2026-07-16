from graphview_api.operations.service import DataOperationsService
from graphview_api.schemas import ImportBundle, ProposalCreate, SourceCreate


class RecordingOperationsRepository:
    def __init__(self) -> None:
        self.created_sources: list[str] = []
        self.created_proposals: list[tuple[str, str]] = []

    def search(self, query, graph_id=None):
        return {"nodes": [{"id": "node-1", "query": query, "graph_id": graph_id}]}

    def export_bundle(self, graph_id=None):
        return {"project": {"id": graph_id or "project-default"}}

    def backup_bundle(self, *, actor_id, include_agent_context_content=False):
        return {"actor_id": actor_id, "include_agent_context_content": include_agent_context_content}

    def restore_bundle(self, payload, *, actor_id):
        return {"restored": True, "actor_id": actor_id}

    def create_source(self, payload, graph_id=None):
        self.created_sources.append(payload.title)
        return {"id": "source-1"}

    def create_proposal(self, payload, actor_id):
        self.created_proposals.append((payload.source_id, actor_id))
        return {"id": "proposal-1"}


def test_data_operations_service_scopes_search_and_export() -> None:
    service = DataOperationsService(RecordingOperationsRepository())

    assert service.search(query="evidence", graph_id="graph-1")["nodes"][0]["graph_id"] == "graph-1"
    assert service.export(graph_id="graph-1")["project"]["id"] == "graph-1"


def test_data_operations_service_preserves_backup_authority_and_content_policy() -> None:
    result = DataOperationsService(RecordingOperationsRepository()).backup(
        actor_id="admin-1",
        include_agent_context_content=True,
    )

    assert result == {"actor_id": "admin-1", "include_agent_context_content": True}


def test_data_operations_service_imports_through_review_gated_creation_paths() -> None:
    repository = RecordingOperationsRepository()
    service = DataOperationsService(repository)
    result = service.import_bundle(
        ImportBundle(
            sources=[SourceCreate(kind="text", title="Imported evidence")],
            proposals=[
                ProposalCreate(
                    source_id="source-1",
                    proposed_value={"id": "node-1", "label": "Imported concept", "kind": "concept"},
                )
            ],
        ),
        actor_id="admin-1",
    )

    assert repository.created_sources == ["Imported evidence"]
    assert repository.created_proposals == [("source-1", "admin-1")]
    assert result["project"]["id"] == "project-default"
