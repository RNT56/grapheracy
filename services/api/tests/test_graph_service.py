from datetime import UTC, datetime

import pytest

from graphview_api.graph.service import GraphService


class RecordingGraphRepository:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.neighborhood_value = {"nodes": [{"id": "node-1"}], "edges": []}
        self.path_value = {"nodes": [{"id": "node-1"}, {"id": "node-2"}], "edges": []}

    def graph(self, graph_id=None, lens=None):
        self.calls.append(("graph", graph_id, lens))
        return {"id": graph_id or "default"}, [{"id": "node-1"}], []

    def list_graph_views(self):
        return [{"id": "default"}]

    def list_graph_activity_events(self, **kwargs):
        self.calls.append(("activity", kwargs))
        return [
            {"id": "event-1", "payload": {"agent_run_id": "run-1"}},
            {"id": "event-2", "object_refs": [{"kind": "agent_run", "id": "run-2"}]},
        ]

    def insights(self, graph_id=None, lens=None):
        return {"graph_id": graph_id, "lens": lens}

    def neighborhood(self, *_args, **_kwargs):
        return self.neighborhood_value

    def path(self, *_args, **_kwargs):
        return self.path_value

    def graph_settings(self):
        return {"llm_enabled": False}

    def update_graph_settings(self, payload):
        return {"llm_enabled": payload.llm_enabled}


def test_graph_service_normalizes_lens_and_shapes_authenticated_view() -> None:
    repository = RecordingGraphRepository()
    service = GraphService(repository)

    result = service.graph(graph_id="graph-1", lens="invalid", user_id="user-1")

    assert repository.calls == [("graph", "graph-1", "all")]
    assert result["project"]["id"] == "graph-1"
    assert result["user"] == "user-1"


def test_graph_service_filters_agent_activity_without_leaking_other_runs() -> None:
    service = GraphService(RecordingGraphRepository())

    result = service.agent_run_activity(
        agent_run_id="run-2",
        limit=10,
        since=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result["returned_count"] == 1
    assert result["events"][0]["id"] == "event-2"


def test_graph_service_raises_domain_not_found_for_missing_projection() -> None:
    repository = RecordingGraphRepository()
    repository.neighborhood_value = None
    repository.path_value = None
    service = GraphService(repository)

    with pytest.raises(KeyError):
        service.neighborhood(node_id="missing", depth=1, limit=25, graph_id=None, lens="all")
    with pytest.raises(KeyError):
        service.path(
            source_node_id="missing",
            target_node_id="also-missing",
            max_depth=4,
            graph_id=None,
            lens="all",
        )
