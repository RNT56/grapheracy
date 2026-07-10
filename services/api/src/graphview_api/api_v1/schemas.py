from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from graphview_api.schemas import ContentNodeOut, SemanticEdgeOut


class PageInfo(BaseModel):
    next_cursor: str | None = None
    returned_count: int
    total_count: int | None = None


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    trace_id: str | None = None


class GraphBounds(BaseModel):
    min_x: float = -1.0
    min_y: float = -1.0
    max_x: float = 1.0
    max_y: float = 1.0

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            raise ValueError("Graph bounds require min values lower than max values")
        return self


class GraphPositionIn(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    x: float
    y: float
    z: float | None = None
    cluster_key: str | None = Field(default=None, max_length=160)


class GraphLayoutUpsert(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=160)
    algorithm: str = Field(default="forceatlas2", min_length=1, max_length=80)
    graph_version: int | None = Field(default=None, ge=1)
    settings: dict[str, Any] = Field(default_factory=dict)
    positions: list[GraphPositionIn] = Field(min_length=1, max_length=100_000)


class GraphPositionOut(GraphPositionIn):
    pass


class GraphLayoutOut(BaseModel):
    id: str
    project_id: str
    name: str
    algorithm: str
    graph_version: int
    settings: dict[str, Any]
    position_count: int
    positions: list[GraphPositionOut] = Field(default_factory=list)
    created_by: str
    created_at: datetime
    updated_at: datetime


class GraphViewportNode(BaseModel):
    node: ContentNodeOut
    x: float
    y: float
    z: float | None = None


class GraphCluster(BaseModel):
    id: str
    label: str
    x: float
    y: float
    node_count: int
    edge_count: int
    dominant_kind: str
    node_ids: list[str] = Field(default_factory=list)


class GraphViewportEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: str
    weight: float | None = None
    count: int = 1
    edge: SemanticEdgeOut | None = None


class GraphViewportOut(BaseModel):
    graph_id: str
    project_id: str
    graph_version: int
    etag: str
    zoom: float
    level: Literal["clusters", "mixed", "nodes"]
    bounds: GraphBounds
    nodes: list[GraphViewportNode]
    edges: list[GraphViewportEdge]
    clusters: list[GraphCluster]
    omitted_node_count: int
    omitted_edge_count: int
    page: PageInfo


class GraphSubgraphOut(BaseModel):
    graph_id: str
    project_id: str
    graph_version: int
    focus_node_id: str | None = None
    depth: int
    nodes: list[ContentNodeOut]
    edges: list[SemanticEdgeOut]
    omitted_node_count: int
    omitted_edge_count: int


class GraphSearchAnchor(BaseModel):
    id: str
    kind: Literal["node", "source"]
    label: str
    summary: str | None = None
    score: float
    node_id: str | None = None
    source_id: str | None = None


class GraphSearchOut(BaseModel):
    graph_id: str
    query: str
    anchors: list[GraphSearchAnchor]
    page: PageInfo


class GraphEventEnvelope(BaseModel):
    id: str
    event_type: str
    schema_version: int
    project_id: str
    graph_id: str
    trace_id: str
    actor: dict[str, Any]
    occurred_at: datetime
    received_at: datetime
    replay_cursor: str
    payload: dict[str, Any]
    object_refs: list[dict[str, Any]]


class GraphActivityPage(BaseModel):
    graph_id: str
    events: list[GraphEventEnvelope]
    page: PageInfo


class UploadAccepted(BaseModel):
    object_key: str
    filename: str
    content_type: str
    size_bytes: int
    checksum: str
    job_id: str


class ConnectorCursorOut(BaseModel):
    target_id: str
    cursor: str | None = None
    lease_owner: str | None = None
    leased_until: datetime | None = None
    updated_at: datetime


class ConnectorHealthOut(BaseModel):
    target_id: str
    status: Literal["healthy", "syncing", "degraded", "auth_failed", "rate_limited", "disabled"]
    last_success_at: datetime | None = None
    next_scheduled_at: datetime | None = None
    cursor: ConnectorCursorOut
    retry_attempt: int
    imported_count: int
    deleted_count: int
    actionable_failure: str | None = None
