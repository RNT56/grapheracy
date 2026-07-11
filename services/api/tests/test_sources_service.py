import pytest

from graphview_api.schemas import SourceCreate, SourceUpdate
from graphview_api.settings import Settings
from graphview_api.sources.service import SourcesService


class RecordingSourcesRepository:
    engine = None

    def __init__(self) -> None:
        self.lineage_value = {"entity": {"id": "source-1"}}
        self.updated_value = {"id": "source-1", "title": "Updated"}
        self.deleted = True

    def list_source_chunks(self, source_id=None, graph_id=None):
        return [{"id": "chunk-1", "source_id": source_id, "graph_id": graph_id}]

    def lineage(self, entity_kind, entity_id, graph_id=None):
        return self.lineage_value

    def list_sources(self, query=None, graph_id=None):
        return [{"id": "source-1", "query": query, "graph_id": graph_id}]

    def create_source(self, payload, graph_id=None):
        return {"id": "source-1", "title": payload.title, "graph_id": graph_id}

    def update_source(self, source_id, payload):
        return self.updated_value

    def delete_source(self, source_id):
        return self.deleted

    def list_ingestion_runs(self):
        return [{"id": "ingestion-1"}]


def service(repository: RecordingSourcesRepository | None = None) -> SourcesService:
    return SourcesService(repository or RecordingSourcesRepository(), Settings(database_url="sqlite://"))


def test_sources_service_owns_source_projection_and_creation() -> None:
    value = service()

    assert value.sources(query="graph", graph_id="project-default")["sources"][0]["query"] == "graph"
    created = value.create_source(
        SourceCreate(kind="text", title="Evidence"),
        graph_id="project-default",
    )
    assert created["title"] == "Evidence"


def test_sources_service_rejects_unknown_or_missing_lineage() -> None:
    repository = RecordingSourcesRepository()
    value = service(repository)

    with pytest.raises(KeyError):
        value.lineage(entity_kind="unsupported", entity_id="source-1", graph_id=None)
    repository.lineage_value = None
    with pytest.raises(KeyError):
        value.lineage(entity_kind="source", entity_id="missing", graph_id=None)


def test_sources_service_exposes_not_found_transitions_for_router_mapping() -> None:
    repository = RecordingSourcesRepository()
    repository.updated_value = None
    repository.deleted = False
    value = service(repository)

    with pytest.raises(KeyError):
        value.update_source("missing", SourceUpdate(title="Missing"))
    with pytest.raises(KeyError):
        value.delete_source("missing")
