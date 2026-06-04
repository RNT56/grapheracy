from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphProjectOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    kind: Literal["text", "markdown", "url", "pdf", "repository", "ops-document"] = "text"
    title: str = Field(min_length=1, max_length=240)
    uri: str | None = None
    object_key: str | None = None
    checksum: str | None = None


class SourceUpdate(BaseModel):
    kind: Literal["text", "markdown", "url", "pdf", "repository", "ops-document"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    uri: str | None = None
    object_key: str | None = None
    checksum: str | None = None


class SourceOut(SourceCreate):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class ContentNodeOut(BaseModel):
    id: str
    project_id: str
    topic_ids: list[str]
    label: str
    kind: str
    summary: str | None = None
    provenance: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class SemanticEdgeOut(BaseModel):
    id: str
    project_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    weight: float | None = None
    provenance: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class IngestionRunOut(BaseModel):
    id: str
    project_id: str
    source_id: str
    status: str
    stage: str
    trace_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None


class ProposalCreate(BaseModel):
    source_id: str
    kind: Literal["content_node", "semantic_edge"] = "content_node"
    proposed_value: dict[str, Any]
    confidence: float | None = Field(default=None, ge=0, le=1)
    locator: str | None = None


class IngestionCreate(BaseModel):
    kind: Literal["text", "markdown", "url", "pdf"] = "text"
    title: str = Field(min_length=1, max_length=240)
    content: str | None = None
    uri: str | None = None
    content_base64: str | None = None
    proposal_limit: int = Field(default=4, ge=1, le=12)


class ProposalOut(BaseModel):
    id: str
    project_id: str
    ingestion_run_id: str
    kind: str
    status: str
    proposed_value: dict[str, Any]
    confidence: float | None = None
    provenance: list[dict[str, Any]]
    created_at: datetime


class EmbeddingOut(BaseModel):
    id: str
    project_id: str
    proposal_id: str | None = None
    content_node_id: str | None = None
    embedding_model: str
    vector: list[float]
    created_at: datetime


class IngestionResultOut(BaseModel):
    source: SourceOut
    ingestion_run: IngestionRunOut
    proposals: list[ProposalOut]
    embeddings: list[EmbeddingOut]


class ReviewDecisionCreate(BaseModel):
    proposal_id: str
    decision: Literal["accept", "reject", "edit", "defer"]
    edited_value: dict[str, Any] | None = None
    rationale: str | None = None


class ReviewDecisionOut(BaseModel):
    id: str
    project_id: str
    proposal_id: str
    reviewer_id: str
    decision: str
    edited_value: dict[str, Any] | None = None
    rationale: str | None = None
    decided_at: datetime


class GraphOut(BaseModel):
    project: GraphProjectOut
    nodes: list[ContentNodeOut]
    edges: list[SemanticEdgeOut]
    user: str


class ExportBundle(BaseModel):
    project: GraphProjectOut
    sources: list[SourceOut]
    nodes: list[ContentNodeOut]
    edges: list[SemanticEdgeOut]
    ingestion_runs: list[IngestionRunOut]
    proposals: list[ProposalOut]
    embeddings: list[EmbeddingOut]
    review_decisions: list[ReviewDecisionOut]


class ImportBundle(BaseModel):
    sources: list[SourceCreate] = []
    proposals: list[ProposalCreate] = []
