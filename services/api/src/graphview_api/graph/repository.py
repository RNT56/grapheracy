from __future__ import annotations

from datetime import datetime
from typing import Protocol

from graphview_api.schemas import GraphSettingsUpdate


class GraphRepositoryPort(Protocol):
    def graph(self, graph_id: str | None = None, lens: str | None = None) -> tuple[dict, list[dict], list[dict]]: ...

    def list_graph_views(self) -> list[dict]: ...

    def list_graph_activity_events(
        self,
        *,
        graph_id: str | None = None,
        lens: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[dict]: ...

    def insights(self, graph_id: str | None = None, lens: str | None = None) -> dict: ...

    def neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        limit: int = 25,
        graph_id: str | None = None,
        lens: str | None = None,
    ) -> dict | None: ...

    def path(
        self,
        source_node_id: str,
        target_node_id: str,
        *,
        max_depth: int = 4,
        graph_id: str | None = None,
        lens: str | None = None,
    ) -> dict | None: ...

    def graph_settings(self) -> dict: ...

    def update_graph_settings(self, payload: GraphSettingsUpdate) -> dict: ...
