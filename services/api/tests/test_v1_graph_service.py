from graphview_api.api_v1.service import GraphProjectionService, event_envelope
from graphview_api.schemas import GraphLayoutUpsert


class RecordingProjectionRepository:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def list_layouts(self, project_id: str, *, include_positions: bool):
        self.calls.append(("list_layouts", project_id, include_positions))
        return [{"name": "review"}]

    def upsert_layout(self, project_id: str, payload: GraphLayoutUpsert, *, actor_id: str):
        self.calls.append(("upsert_layout", project_id, payload.name, actor_id))
        return {"name": payload.name}


class RecordingLegacyRepository:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.events = [
            {
                "id": "event-1",
                "project_id": "project-1",
                "event_type": "graph.changed",
                "actor_id": "user-1",
                "created_at": "2026-07-11T10:00:00Z",
                "payload": {"trace_id": "trace-1", "authority": "reviewer"},
                "object_refs": [],
            }
        ]

    def list_graph_activity_events(self, **kwargs):
        self.calls.append(("latest", kwargs))
        return self.events

    def list_graph_activity_events_after(self, **kwargs):
        self.calls.append(("after", kwargs))
        return self.events


def test_v1_graph_service_owns_layout_project_scope_and_route_name_authority() -> None:
    projection = RecordingProjectionRepository()
    service = GraphProjectionService(projection, RecordingLegacyRepository())
    payload = GraphLayoutUpsert(positions=[{"node_id": "node-1", "x": 1, "y": 2}])

    assert service.list_layouts("project-1:graph", include_positions=True) == [{"name": "review"}]
    assert service.put_layout("project-1:graph", "review", payload, actor_id="user-1") == {"name": "review"}
    assert projection.calls == [
        ("list_layouts", "project-1", True),
        ("upsert_layout", "project-1", "review", "user-1"),
    ]


def test_v1_graph_service_builds_stable_activity_pages_and_respects_replay_cursor() -> None:
    legacy = RecordingLegacyRepository()
    service = GraphProjectionService(RecordingProjectionRepository(), legacy)

    latest = service.activity_page("project-1:graph", cursor=None, limit=50)
    replay = service.activity_page("project-1:graph", cursor="event-0", limit=50)

    assert latest["events"][0] == event_envelope(legacy.events[0], "project-1:graph")
    assert latest["page"] == {"next_cursor": None, "returned_count": 1, "total_count": None}
    assert replay["events"][0]["trace_id"] == "trace-1"
    assert legacy.calls == [
        ("latest", {"graph_id": "project-1:graph", "limit": 50}),
        ("after", {"graph_id": "project-1:graph", "cursor": "event-0", "limit": 50}),
    ]
