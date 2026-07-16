from __future__ import annotations

from datetime import datetime, timezone

from graphview_api.graph.repository import GraphRepositoryPort
from graphview_api.lenses import EXTRACTION_LENS_DESCRIPTORS, GRAPH_LENS_DESCRIPTORS, normalize_graph_lens
from graphview_api.schemas import GraphSettingsUpdate


class GraphService:
    def __init__(self, repository: GraphRepositoryPort) -> None:
        self.repository = repository

    def graph(self, *, graph_id: str | None, lens: str | None, user_id: str) -> dict[str, object]:
        project, nodes, edges = self.repository.graph(graph_id, normalize_graph_lens(lens))
        return {"project": project, "nodes": nodes, "edges": edges, "user": user_id}

    def graphs(self) -> list[dict[str, object]]:
        return self.repository.list_graph_views()

    def activity(
        self,
        *,
        graph_id: str | None,
        lens: str | None,
        limit: int,
        since: datetime | None,
    ) -> dict[str, object]:
        events = self.activity_events(graph_id=graph_id, lens=lens, limit=limit, since=since)
        return {"generated_at": datetime.now(timezone.utc), "returned_count": len(events), "events": events}

    def activity_events(
        self,
        *,
        graph_id: str | None,
        lens: str | None,
        limit: int,
        since: datetime | None,
    ) -> list[dict]:
        return self.repository.list_graph_activity_events(
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
            limit=limit,
            since=since,
        )

    def agent_run_activity(self, *, agent_run_id: str, limit: int, since: datetime | None) -> dict[str, object]:
        events = [
            event
            for event in self.repository.list_graph_activity_events(limit=100, since=since)
            if _activity_event_matches_agent_run(event, agent_run_id)
        ][:limit]
        return {"generated_at": datetime.now(timezone.utc), "returned_count": len(events), "events": events}

    def insights(self, *, graph_id: str | None, lens: str | None) -> dict[str, object]:
        return self.repository.insights(graph_id, normalize_graph_lens(lens))

    def neighborhood(
        self,
        *,
        node_id: str,
        depth: int,
        limit: int,
        graph_id: str | None,
        lens: str | None,
    ) -> dict[str, object]:
        value = self.repository.neighborhood(
            node_id,
            depth=depth,
            limit=limit,
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
        )
        if value is None:
            raise KeyError(node_id)
        return value

    def path(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        max_depth: int,
        graph_id: str | None,
        lens: str | None,
    ) -> dict[str, object]:
        value = self.repository.path(
            source_node_id,
            target_node_id,
            max_depth=max_depth,
            graph_id=graph_id,
            lens=normalize_graph_lens(lens),
        )
        if value is None:
            raise KeyError((source_node_id, target_node_id))
        return value

    def extraction_lenses(self) -> dict[str, list[dict[str, object]]]:
        return {"extraction_lenses": EXTRACTION_LENS_DESCRIPTORS}

    def graph_lenses(self) -> dict[str, list[dict[str, object]]]:
        return {"graph_lenses": GRAPH_LENS_DESCRIPTORS}

    def settings(self) -> dict:
        return self.repository.graph_settings()

    def update_settings(self, payload: GraphSettingsUpdate) -> dict:
        return self.repository.update_graph_settings(payload)


def _activity_event_matches_agent_run(event: dict[str, object], agent_run_id: str) -> bool:
    payload = event.get("payload")
    if isinstance(payload, dict) and payload.get("agent_run_id") == agent_run_id:
        return True
    refs = event.get("object_refs")
    if not isinstance(refs, list):
        return False
    return any(
        isinstance(ref, dict) and ref.get("kind") == "agent_run" and ref.get("id") == agent_run_id
        for ref in refs
    )
