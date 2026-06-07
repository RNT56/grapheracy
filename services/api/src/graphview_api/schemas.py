from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SOURCE_KINDS = ("text", "markdown", "url", "pdf", "repository", "ops-document")
CONNECTOR_KINDS = ("upload", "url", "repository", "google-workspace", "notion")
CONTENT_NODE_KINDS = (
    "concept",
    "topic",
    "term",
    "document",
    "source",
    "text",
    "markdown",
    "url",
    "pdf",
    "ops_document",
    "dataset",
    "system",
    "component",
    "service",
    "api",
    "repository",
    "module",
    "package",
    "file",
    "symbol",
    "workflow",
    "policy",
    "process",
    "vendor",
    "decision",
    "requirement",
    "risk",
    "metric",
    "event",
    "incident",
    "project",
    "owner",
    "review_cycle",
    "task",
    "person",
    "team",
    "organization",
    "product",
    "feature",
    "asset",
    "location",
)
CONTENT_NODE_KIND_ALIASES = {
    "acronym": "term",
    "action": "task",
    "action_item": "task",
    "artifact": "asset",
    "company": "organization",
    "dependency": "package",
    "doc": "document",
    "endpoint": "api",
    "entity": "concept",
    "folder": "topic",
    "function": "symbol",
    "heading": "topic",
    "issue": "task",
    "kpi": "metric",
    "link": "source",
    "memo": "document",
    "note": "document",
    "org": "organization",
    "page": "document",
    "path": "file",
    "policy_document": "policy",
    "procedure": "process",
    "pull_request": "task",
    "repo": "repository",
    "review": "review_cycle",
    "route": "api",
    "supplier": "vendor",
    "ticket": "task",
}
SEMANTIC_RELATIONS = (
    "supports",
    "contradicts",
    "depends_on",
    "causes",
    "mentions",
    "defines",
    "relates_to",
    "contains",
    "part_of",
    "references",
    "imports",
    "implements",
    "owned_by",
    "has_review_cycle",
    "governs",
)
SOURCE_CHUNK_BLOCK_TYPES = ("document", "heading", "paragraph", "table", "list", "code", "link", "metadata")

SourceKind = Literal["text", "markdown", "url", "pdf", "repository", "ops-document"]
ConnectorKind = Literal["upload", "url", "repository", "google-workspace", "notion"]
ContentNodeKind = Literal[
    "concept",
    "topic",
    "term",
    "document",
    "source",
    "text",
    "markdown",
    "url",
    "pdf",
    "ops_document",
    "dataset",
    "system",
    "component",
    "service",
    "api",
    "repository",
    "module",
    "package",
    "file",
    "symbol",
    "workflow",
    "policy",
    "process",
    "vendor",
    "decision",
    "requirement",
    "risk",
    "metric",
    "event",
    "incident",
    "project",
    "owner",
    "review_cycle",
    "task",
    "person",
    "team",
    "organization",
    "product",
    "feature",
    "asset",
    "location",
]
SemanticRelation = Literal[
    "supports",
    "contradicts",
    "depends_on",
    "causes",
    "mentions",
    "defines",
    "relates_to",
    "contains",
    "part_of",
    "references",
    "imports",
    "implements",
    "owned_by",
    "has_review_cycle",
    "governs",
]
ProposalKind = Literal["content_node", "semantic_edge"]
ProposalStatus = Literal["pending_review", "accepted", "rejected", "edited", "deferred"]
ReviewDecisionValue = Literal["accept", "reject", "edit", "defer"]
IngestionRunStatus = Literal["queued", "running", "proposal_ready", "committed", "failed", "cancelled"]
IngestionRunStage = Literal["fetch", "extract", "analyze", "embed", "propose", "commit"]
ConnectorStatus = Literal["connected", "disabled", "error"]
ConnectorTargetType = Literal["file", "folder", "page", "database", "repository", "url", "upload"]
ConnectorSyncStatus = Literal["running", "completed", "failed"]
SourceChunkBlockType = Literal["document", "heading", "paragraph", "table", "list", "code", "link", "metadata"]
AgentRunMode = Literal["graph", "planning"]
FocusTargetKind = Literal["graph", "node", "source", "chunk", "proposal", "plan"]
AgentToolKind = Literal[
    "graph_query",
    "source_search",
    "source_open",
    "research_run",
    "proposal_create",
    "review_action",
    "connector_sync",
    "graph_layout",
]
AgentToolStatus = Literal["pending_review", "running", "succeeded", "failed", "blocked"]
SignalKind = Literal[
    "source_changed",
    "source_stale",
    "proposal_ready",
    "proposal_blocked",
    "conflict_detected",
    "anomaly_detected",
    "connector_issue",
    "agent_action_pending",
    "decision_due",
    "outcome_due",
    "policy_violation",
]
NervousSystemSeverity = Literal["info", "low", "medium", "high", "critical"]
SignalStatus = Literal["new", "linked", "routed", "dismissed", "resolved"]
SignalSourceKind = Literal["manual", "api", "connector", "schedule", "webhook", "agent"]
AlertStatus = Literal["open", "assigned", "blocked", "resolved", "dismissed"]
AttentionStatus = Literal[
    "open",
    "assigned",
    "waiting_for_review",
    "waiting_for_action",
    "waiting_for_outcome",
    "resolved",
    "dismissed",
    "blocked",
    "reopened",
]
SlaStatus = Literal["none", "on_track", "at_risk", "overdue"]
OwnerType = Literal["person", "team", "service_account", "group"]
OwnershipScopeKind = Literal["project", "lens", "topic", "source", "node_kind", "node", "edge", "policy", "action_type", "connector"]
DecisionRecordValue = Literal["accept", "reject", "approve", "defer", "dismiss", "escalate", "reopen"]
ActionProposalStatus = Literal["proposed", "pending_review", "approved", "rejected", "queued", "running", "succeeded", "failed", "cancelled"]
ActionRunStatus = Literal["queued", "running", "succeeded", "failed", "partial", "cancelled"]
OutcomeStatus = Literal["waiting", "succeeded", "failed", "partial", "unresolved", "resolved", "reopened"]
FeedbackKind = Literal["source_freshness", "confidence_update", "priority_update", "policy_suggestion", "graph_memory_proposal", "false_positive"]
ActionSafetyLevel = Literal["internal_safe", "graph_mutation", "external_stub", "external_side_effect"]
ReviewWorkItemKind = Literal[
    "new_entity",
    "new_relation",
    "source_extraction",
    "research_result",
    "conflicting_fact",
    "stale_source",
    "connector_issue",
    "planning_action",
]


def normalize_content_node_kind(kind: str | None) -> str:
    normalized = (kind or "concept").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in CONTENT_NODE_KINDS:
        return normalized
    return CONTENT_NODE_KIND_ALIASES.get(normalized, "")


def normalize_semantic_relation(relation: str | None) -> str:
    normalized = (relation or "relates_to").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in SEMANTIC_RELATIONS else ""


def _non_empty_string(value: Any, field_name: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if max_length is not None and len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def validate_content_node_proposal_value(value: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(value)
    normalized["label"] = _non_empty_string(normalized.get("label"), "proposed_value.label", max_length=240)
    node_kind = normalize_content_node_kind(str(normalized.get("kind") or "concept"))
    if not node_kind:
        raise ValueError(f"Unsupported proposed_value.kind: {normalized.get('kind')}")
    normalized["kind"] = node_kind
    if normalized.get("id") is not None:
        normalized["id"] = _non_empty_string(normalized["id"], "proposed_value.id", max_length=128)
    if normalized.get("summary") is not None and not isinstance(normalized["summary"], str):
        raise ValueError("proposed_value.summary must be a string when provided")
    topic_ids = normalized.get("topicIds", [])
    if topic_ids is None:
        topic_ids = []
    if not isinstance(topic_ids, list) or not all(isinstance(item, str) and item for item in topic_ids):
        raise ValueError("proposed_value.topicIds must be a list of non-empty strings")
    normalized["topicIds"] = topic_ids
    metadata = normalized.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("proposed_value.metadata must be an object when provided")
    normalized["metadata"] = metadata
    return normalized


def validate_semantic_edge_proposal_value(value: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(value)
    normalized["sourceNodeId"] = _non_empty_string(
        normalized.get("sourceNodeId"),
        "proposed_value.sourceNodeId",
        max_length=128,
    )
    normalized["targetNodeId"] = _non_empty_string(
        normalized.get("targetNodeId"),
        "proposed_value.targetNodeId",
        max_length=128,
    )
    relation = normalize_semantic_relation(str(normalized.get("relation") or "relates_to"))
    if not relation:
        raise ValueError(f"Unsupported proposed_value.relation: {normalized.get('relation')}")
    normalized["relation"] = relation
    if normalized.get("id") is not None:
        normalized["id"] = _non_empty_string(normalized["id"], "proposed_value.id", max_length=128)
    if normalized.get("sourceLabel") is not None:
        normalized["sourceLabel"] = _non_empty_string(normalized["sourceLabel"], "proposed_value.sourceLabel", max_length=240)
    if normalized.get("targetLabel") is not None:
        normalized["targetLabel"] = _non_empty_string(normalized["targetLabel"], "proposed_value.targetLabel", max_length=240)
    if normalized.get("label") is not None:
        normalized["label"] = _non_empty_string(normalized["label"], "proposed_value.label", max_length=520)
    if normalized.get("weight") is not None:
        weight = normalized["weight"]
        if not isinstance(weight, int | float) or weight < 0 or weight > 1:
            raise ValueError("proposed_value.weight must be a number from 0 to 1 when provided")
        normalized["weight"] = float(weight)
    metadata = normalized.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("proposed_value.metadata must be an object when provided")
    normalized["metadata"] = metadata
    return normalized


class GraphProjectOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class GraphViewOut(BaseModel):
    id: str
    project_id: str
    label: str
    description: str | None = None
    kind: Literal["project", "scope"]
    source_ids: list[str] = Field(default_factory=list)
    node_count: int
    edge_count: int
    source_count: int
    pending_proposal_count: int


class SourceCreate(BaseModel):
    kind: SourceKind = "text"
    title: str = Field(min_length=1, max_length=240)
    uri: str | None = None
    object_key: str | None = None
    checksum: str | None = None
    connector_kind: ConnectorKind | None = None
    remote_id: str | None = None
    remote_parent_id: str | None = None
    remote_modified_at: datetime | None = None
    remote_url: str | None = None
    metadata: dict[str, Any] | None = None
    stale_at: datetime | None = None


class SourceUpdate(BaseModel):
    kind: SourceKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    uri: str | None = None
    object_key: str | None = None
    checksum: str | None = None
    connector_kind: ConnectorKind | None = None
    remote_id: str | None = None
    remote_parent_id: str | None = None
    remote_modified_at: datetime | None = None
    remote_url: str | None = None
    metadata: dict[str, Any] | None = None
    stale_at: datetime | None = None


class SourceOut(SourceCreate):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class ProvenanceOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    sourceId: str
    sourceUri: str | None = None
    locator: str | None = None
    extractedBy: Literal["human", "worker", "import"] | None = None
    actorId: str | None = None
    ingestionRunId: str | None = None
    observedAt: str
    traceId: str


class TopicOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    parent_topic_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ContentNodeOut(BaseModel):
    id: str
    project_id: str
    topic_ids: list[str]
    label: str
    kind: ContentNodeKind
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceOut]
    created_at: datetime
    updated_at: datetime

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: Any) -> str:
        normalized = normalize_content_node_kind(str(value) if value is not None else None)
        if not normalized:
            raise ValueError(f"Unsupported content node kind: {value}")
        return normalized


class SemanticEdgeOut(BaseModel):
    id: str
    project_id: str
    source_node_id: str
    target_node_id: str
    relation: SemanticRelation
    weight: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceOut]
    created_at: datetime
    updated_at: datetime

    @field_validator("relation", mode="before")
    @classmethod
    def validate_relation(cls, value: Any) -> str:
        normalized = normalize_semantic_relation(str(value) if value is not None else None)
        if not normalized:
            raise ValueError(f"Unsupported semantic relation: {value}")
        return normalized


class IngestionRunOut(BaseModel):
    id: str
    project_id: str
    source_id: str
    status: IngestionRunStatus
    stage: IngestionRunStage
    trace_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None


class ProposalCreate(BaseModel):
    source_id: str
    kind: ProposalKind = "content_node"
    proposed_value: dict[str, Any]
    confidence: float | None = Field(default=None, ge=0, le=1)
    locator: str | None = None

    @model_validator(mode="after")
    def validate_proposed_value(self):
        if self.kind == "content_node":
            self.proposed_value = validate_content_node_proposal_value(self.proposed_value)
        else:
            self.proposed_value = validate_semantic_edge_proposal_value(self.proposed_value)
        return self


class IngestionCreate(BaseModel):
    kind: Literal["text", "markdown", "url", "pdf", "repository", "ops-document"] = "text"
    title: str = Field(min_length=1, max_length=240)
    content: str | None = None
    uri: str | None = None
    content_base64: str | None = None
    proposal_limit: int = Field(default=4, ge=1, le=12)
    extraction_lenses: list[Literal["research", "engineering", "ops"]] | None = None
    proposal_limit_per_lens: int | None = Field(default=None, ge=1, le=12)


class ProposalOut(BaseModel):
    id: str
    project_id: str
    ingestion_run_id: str
    kind: ProposalKind
    status: ProposalStatus
    proposed_value: dict[str, Any]
    confidence: float | None = None
    provenance: list[ProvenanceOut]
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
    decision: ReviewDecisionValue
    edited_value: dict[str, Any] | None = None
    rationale: str | None = None


class ReviewDecisionOut(BaseModel):
    id: str
    project_id: str
    proposal_id: str
    reviewer_id: str
    decision: ReviewDecisionValue
    edited_value: dict[str, Any] | None = None
    rationale: str | None = None
    decided_at: datetime


class GraphOut(BaseModel):
    project: GraphProjectOut
    nodes: list[ContentNodeOut]
    edges: list[SemanticEdgeOut]
    user: str


class GraphObjectRefOut(BaseModel):
    kind: str
    id: str
    label: str | None = None


class GraphActivityEventOut(BaseModel):
    id: str
    project_id: str
    event_type: str
    actor_id: str | None = None
    summary: str
    object_refs: list[GraphObjectRefOut] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    lenses: list[str] = Field(default_factory=list)
    created_at: datetime


class GraphActivityOut(BaseModel):
    generated_at: datetime
    returned_count: int
    events: list[GraphActivityEventOut] = Field(default_factory=list)


class SignalCreate(BaseModel):
    graph_id: str | None = None
    kind: SignalKind
    severity: NervousSystemSeverity = "medium"
    source_kind: SignalSourceKind = "manual"
    source_id: str | None = None
    title: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    received_at: datetime | None = None
    route: bool = True

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _non_empty_string(value, "title", max_length=240)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return _non_empty_string(value, "summary", max_length=2000)


class SignalOut(BaseModel):
    id: str
    project_id: str
    graph_id: str | None = None
    kind: SignalKind
    status: SignalStatus
    severity: NervousSystemSeverity
    source_kind: SignalSourceKind
    source_id: str | None = None
    title: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    checksum: str
    trace_id: str
    actor_id: str | None = None
    received_at: datetime
    created_at: datetime


class ObservationCreate(BaseModel):
    signal_id: str | None = None
    kind: str = "signal_interpretation"
    summary: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    object_refs: list[GraphObjectRefOut] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_links(self) -> "ObservationCreate":
        if not (self.signal_id or self.source_ids or self.node_ids or self.edge_ids or self.object_refs):
            raise ValueError("Observation must link to a signal or graph/source object.")
        return self


class ObservationOut(BaseModel):
    id: str
    project_id: str
    signal_id: str | None = None
    kind: str
    summary: str
    confidence: float | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    object_refs: list[GraphObjectRefOut] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class OwnerCreate(BaseModel):
    owner_type: OwnerType
    display_name: str
    contact: str | None = None
    scope_kind: OwnershipScopeKind = "project"
    scope_id: str | None = None
    escalation_contact: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OwnerUpdate(BaseModel):
    display_name: str | None = None
    contact: str | None = None
    scope_kind: OwnershipScopeKind | None = None
    scope_id: str | None = None
    escalation_contact: str | None = None
    metadata: dict[str, Any] | None = None


class OwnerOut(BaseModel):
    id: str
    project_id: str
    owner_type: OwnerType
    display_name: str
    contact: str | None = None
    scope_kind: OwnershipScopeKind
    scope_id: str | None = None
    escalation_contact: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class RoutingPolicyCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    match: dict[str, Any] = Field(default_factory=dict)
    severity: NervousSystemSeverity = "medium"
    owner_id: str | None = None
    sla_seconds: int | None = Field(default=None, ge=60)
    suggested_actions: list[str] = Field(default_factory=list)
    approval_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoutingPolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    match: dict[str, Any] | None = None
    severity: NervousSystemSeverity | None = None
    owner_id: str | None = None
    sla_seconds: int | None = Field(default=None, ge=60)
    suggested_actions: list[str] | None = None
    approval_required: bool | None = None
    metadata: dict[str, Any] | None = None


class RoutingPolicyOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    enabled: bool
    match: dict[str, Any] = Field(default_factory=dict)
    severity: NervousSystemSeverity
    owner_id: str | None = None
    sla_seconds: int | None = None
    suggested_actions: list[str] = Field(default_factory=list)
    approval_required: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AlertOut(BaseModel):
    id: str
    project_id: str
    signal_id: str | None = None
    observation_id: str | None = None
    owner_id: str | None = None
    policy_id: str | None = None
    severity: NervousSystemSeverity
    status: AlertStatus
    title: str
    summary: str
    reason: str
    object_refs: list[GraphObjectRefOut] = Field(default_factory=list)
    due_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertAssign(BaseModel):
    owner_id: str | None = None
    assignee_id: str | None = None
    status: AlertStatus = "assigned"


class AttentionItemOut(BaseModel):
    id: str
    project_id: str
    kind: str
    status: AttentionStatus
    severity: NervousSystemSeverity
    sla_status: SlaStatus
    title: str
    summary: str
    owner_id: str | None = None
    assignee_id: str | None = None
    due_at: datetime | None = None
    source_id: str | None = None
    signal_id: str | None = None
    observation_id: str | None = None
    alert_id: str | None = None
    proposal_id: str | None = None
    decision_record_id: str | None = None
    action_proposal_id: str | None = None
    action_run_id: str | None = None
    outcome_id: str | None = None
    feedback_event_id: str | None = None
    object_refs: list[GraphObjectRefOut] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class AttentionOut(BaseModel):
    generated_at: datetime
    returned_count: int
    items: list[AttentionItemOut] = Field(default_factory=list)


class AttentionTransition(BaseModel):
    status: AttentionStatus
    assignee_id: str | None = None
    blockers: list[str] | None = None
    rationale: str | None = None


class DecisionRecordCreate(BaseModel):
    alert_id: str | None = None
    attention_item_id: str | None = None
    proposal_id: str | None = None
    decision: DecisionRecordValue
    rationale: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    object_refs: list[GraphObjectRefOut] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target(self) -> "DecisionRecordCreate":
        if not (self.alert_id or self.attention_item_id or self.proposal_id):
            raise ValueError("Decision record must link to an alert, attention item, or proposal.")
        return self


class DecisionRecordOut(BaseModel):
    id: str
    project_id: str
    alert_id: str | None = None
    attention_item_id: str | None = None
    proposal_id: str | None = None
    decision: DecisionRecordValue
    rationale: str
    actor_id: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    object_refs: list[GraphObjectRefOut] = Field(default_factory=list)
    created_at: datetime


class ActionSafetyOut(BaseModel):
    safety_level: ActionSafetyLevel
    mutates_graphview: bool
    calls_external_system: bool
    transfers_private_content: bool
    approval_required: bool


class ActionProposalCreate(BaseModel):
    decision_record_id: str | None = None
    alert_id: str | None = None
    attention_item_id: str | None = None
    action_type: str
    title: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    safety: ActionSafetyOut | None = None
    approval_required: bool = True


class ActionProposalDecision(BaseModel):
    rationale: str | None = None


class ActionProposalOut(BaseModel):
    id: str
    project_id: str
    decision_record_id: str | None = None
    alert_id: str | None = None
    attention_item_id: str | None = None
    action_type: str
    status: ActionProposalStatus
    title: str
    summary: str
    redacted_payload: dict[str, Any] = Field(default_factory=dict)
    safety: ActionSafetyOut
    approval_required: bool
    created_by: str
    approved_by: str | None = None
    rejected_by: str | None = None
    rationale: str | None = None
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None = None


class ActionRunCreate(BaseModel):
    action_proposal_id: str


class ActionRunOut(BaseModel):
    id: str
    project_id: str
    action_proposal_id: str
    action_type: str
    status: ActionRunStatus
    executor_id: str
    target: str | None = None
    redacted_payload: dict[str, Any] = Field(default_factory=dict)
    external_id: str | None = None
    trace_id: str
    error_code: str | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class OutcomeCreate(BaseModel):
    attention_item_id: str | None = None
    alert_id: str | None = None
    status: OutcomeStatus
    title: str
    summary: str
    result: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class OutcomeOut(BaseModel):
    id: str
    project_id: str
    action_run_id: str | None = None
    attention_item_id: str | None = None
    alert_id: str | None = None
    status: OutcomeStatus
    title: str
    summary: str
    result: dict[str, Any] = Field(default_factory=dict)
    actor_id: str
    occurred_at: datetime
    created_at: datetime


class FeedbackEventCreate(BaseModel):
    outcome_id: str | None = None
    action_run_id: str | None = None
    attention_item_id: str | None = None
    kind: FeedbackKind
    summary: str
    effect: dict[str, Any] = Field(default_factory=dict)
    proposed_value: dict[str, Any] | None = None


class FeedbackEventOut(BaseModel):
    id: str
    project_id: str
    outcome_id: str | None = None
    action_run_id: str | None = None
    attention_item_id: str | None = None
    kind: FeedbackKind
    summary: str
    effect: dict[str, Any] = Field(default_factory=dict)
    proposed_value: dict[str, Any] | None = None
    actor_id: str
    created_at: datetime


class GraphNeighborhoodOut(BaseModel):
    center_node: ContentNodeOut
    depth: int
    limit: int
    nodes: list[ContentNodeOut]
    edges: list[SemanticEdgeOut]
    omitted_node_count: int
    omitted_edge_count: int


class GraphPathOut(BaseModel):
    source_node: ContentNodeOut
    target_node: ContentNodeOut
    max_depth: int
    path_found: bool
    distance: int | None = None
    nodes: list[ContentNodeOut] = Field(default_factory=list)
    edges: list[SemanticEdgeOut] = Field(default_factory=list)


class ReviewQueueItemOut(BaseModel):
    proposal: ProposalOut
    source: SourceOut | None = None
    priority_score: int
    action: Literal["review_node", "review_relationship", "accept_endpoints"]
    work_item_kind: ReviewWorkItemKind | None = None
    change_summary: str | None = None
    evidence_summary: str | None = None
    affected_graph_ids: list[str] = Field(default_factory=list)
    citations: list["AgentCitationOut"] = Field(default_factory=list)
    blocked: bool
    ready_to_commit: bool
    reason: str
    endpoint_node_ids: list[str] = Field(default_factory=list)
    missing_endpoint_node_ids: list[str] = Field(default_factory=list)


class ReviewQueueOut(BaseModel):
    generated_at: datetime
    pending_count: int
    ready_count: int
    blocked_count: int
    items: list[ReviewQueueItemOut] = Field(default_factory=list)


class ReviewDashboardOut(BaseModel):
    project_id: str
    generated_at: datetime
    proposal_count: int
    pending_count: int
    ready_count: int
    blocked_count: int
    review_decision_count: int
    accepted_count: int
    rejected_count: int
    edited_count: int
    deferred_count: int
    acceptance_rate: float
    commit_rate: float
    proposal_kind_counts: list[dict[str, Any]] = Field(default_factory=list)
    pending_kind_counts: list[dict[str, Any]] = Field(default_factory=list)
    decision_counts: list[dict[str, Any]] = Field(default_factory=list)
    reviewer_counts: list[dict[str, Any]] = Field(default_factory=list)
    oldest_pending_proposal_id: str | None = None
    oldest_pending_created_at: datetime | None = None


class ReviewActivityItemOut(BaseModel):
    decision: ReviewDecisionOut
    proposal: ProposalOut | None = None
    source: SourceOut | None = None
    summary: str


class ReviewActivityOut(BaseModel):
    generated_at: datetime
    review_decision_count: int
    returned_count: int
    items: list[ReviewActivityItemOut] = Field(default_factory=list)


class SourceReviewSummaryOut(BaseModel):
    source: SourceOut
    status: Literal["no_proposals", "pending_review", "mixed", "reviewed"]
    proposal_count: int
    pending_count: int
    reviewed_count: int
    decision_count: int
    accepted_count: int
    rejected_count: int
    edited_count: int
    deferred_count: int
    last_reviewed_at: datetime | None = None


class SourceReviewCoverageOut(BaseModel):
    generated_at: datetime
    source_count: int
    proposal_count: int
    pending_count: int
    reviewed_count: int
    returned_count: int
    sources: list[SourceReviewSummaryOut] = Field(default_factory=list)


class LineageTraceOut(BaseModel):
    entity_kind: Literal["source", "proposal", "node", "edge"]
    entity_id: str
    source: dict[str, Any] | None = None
    ingestion_runs: list[dict[str, Any]] = Field(default_factory=list)
    proposals: list[dict[str, Any]] = Field(default_factory=list)
    review_decisions: list[dict[str, Any]] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class GraphInsightsOut(BaseModel):
    project_id: str
    generated_at: datetime
    node_count: int
    edge_count: int
    source_count: int
    proposal_count: int
    pending_proposal_count: int
    review_decision_count: int
    connected_edge_count: int
    orphan_edge_count: int
    provenance_coverage: dict[str, Any]
    source_kinds: list[dict[str, Any]] = Field(default_factory=list)
    node_kinds: list[dict[str, Any]] = Field(default_factory=list)
    relation_counts: list[dict[str, Any]] = Field(default_factory=list)
    proposal_statuses: list[dict[str, Any]] = Field(default_factory=list)
    top_nodes: list[dict[str, Any]] = Field(default_factory=list)


class ExtractionLensOut(BaseModel):
    id: Literal["research", "engineering", "ops"]
    label: str
    summary: str
    default_proposal_limit: int
    source_kinds: list[SourceKind]
    primary_node_kinds: list[ContentNodeKind]
    provenance_fields: list[str]


class GraphLensOut(BaseModel):
    id: Literal["all", "research", "engineering", "ops"]
    label: str
    summary: str
    active_by_default: bool


class GraphSettingsUpdate(BaseModel):
    llm_enabled: bool | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    auto_commit_threshold: float | None = Field(default=None, ge=0, le=1)
    settings: dict[str, Any] | None = None


class GraphSettingsOut(BaseModel):
    project_id: str
    llm_enabled: bool
    llm_provider: str | None = None
    llm_model: str | None = None
    auto_commit_threshold: float
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProviderModelDescriptorOut(BaseModel):
    id: str
    label: str
    default: bool = False
    capabilities: list[str] = Field(default_factory=list)
    context_window: int | None = None


class ProviderDescriptorOut(BaseModel):
    id: str
    label: str
    enabled: bool
    configured: bool
    default_model: str
    capabilities: list[str] = Field(default_factory=list)
    models: list[ProviderModelDescriptorOut] = Field(default_factory=list)


class AgentCitationOut(BaseModel):
    id: str
    label: str
    source_id: str | None = None
    source_title: str | None = None
    source_chunk_id: str | None = None
    node_id: str | None = None
    proposal_id: str | None = None
    locator: str | None = None
    quote: str | None = None
    url: str | None = None
    confidence: float | None = None


class AgentActionProposalOut(BaseModel):
    id: str
    project_id: str
    agent_run_id: str
    action_type: str
    status: Literal["pending_review", "approved", "rejected", "applied", "failed"]
    title: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    citations: list[AgentCitationOut] = Field(default_factory=list)
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None = None


class FocusTargetOut(BaseModel):
    kind: FocusTargetKind
    id: str | None = None
    label: str | None = None


class AgentGeneratedArtifactOut(BaseModel):
    id: str
    kind: Literal["plan", "source", "subgraph", "proposal_diff", "evidence_bundle"]
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    citations: list[AgentCitationOut] = Field(default_factory=list)


class AgentToolCallCreate(BaseModel):
    kind: AgentToolKind
    input: dict[str, Any] = Field(default_factory=dict)
    mode: AgentRunMode = "graph"
    focus_target: FocusTargetOut | None = None


class AgentToolCallOut(BaseModel):
    id: str
    kind: AgentToolKind
    input: dict[str, Any] = Field(default_factory=dict)
    status: AgentToolStatus
    citations: list[AgentCitationOut] = Field(default_factory=list)
    affected_graph_ids: list[str] = Field(default_factory=list)
    resulting_proposal_id: str | None = None
    summary: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentStepOut(BaseModel):
    id: str
    project_id: str
    agent_run_id: str
    name: str
    status: str
    input_summary: str | None = None
    output_summary: str | None = None
    error: str | None = None
    trace_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime | None = None


class AgentRunCreate(BaseModel):
    kind: Literal["planning", "graph_query", "research", "action_apply"]
    input: dict[str, Any] = Field(default_factory=dict)
    mode: AgentRunMode = "graph"
    focus_target: FocusTargetOut | None = None
    provider: str | None = None
    model: str | None = None
    planning_session_id: str | None = None


class AgentRunOut(BaseModel):
    id: str
    project_id: str
    planning_session_id: str | None = None
    kind: str
    mode: AgentRunMode = "graph"
    focus_target: FocusTargetOut | None = None
    status: Literal["queued", "running", "waiting_for_review", "completed", "failed", "cancelled"]
    provider: str
    model: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    created_by: str
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    steps: list[AgentStepOut] = Field(default_factory=list)
    tool_calls: list[AgentToolCallOut] = Field(default_factory=list)
    generated_artifacts: list[AgentGeneratedArtifactOut] = Field(default_factory=list)
    action_proposals: list[AgentActionProposalOut] = Field(default_factory=list)


class GraphBuildSpecCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    objective: str | None = Field(default=None, min_length=1)
    status: Literal["draft", "approved", "archived"] = "draft"
    spec: dict[str, Any] = Field(default_factory=dict)


class GraphBuildSpecOut(BaseModel):
    id: str
    project_id: str
    session_id: str
    version: int
    title: str
    objective: str
    status: str
    spec: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PlanningMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None


class PlanningMessageOut(BaseModel):
    id: str
    project_id: str
    session_id: str
    agent_run_id: str | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class PlanningSessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    goal: str = Field(min_length=1)
    graph_id: str | None = None
    lens: Literal["all", "research", "engineering", "ops"] = "all"
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanningSessionOut(BaseModel):
    id: str
    project_id: str
    graph_id: str | None = None
    lens: str
    title: str
    goal: str
    status: str
    provider: str | None = None
    model: str | None = None
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    messages: list[PlanningMessageOut] = Field(default_factory=list)
    build_spec: GraphBuildSpecOut | None = None


class GraphQueryCreate(BaseModel):
    question: str = Field(min_length=1)
    graph_id: str | None = None
    lens: Literal["all", "research", "engineering", "ops"] = "all"
    node_id: str | None = None
    source_id: str | None = None
    provider: str | None = None
    model: str | None = None


class GraphQueryAnswerOut(BaseModel):
    answer: str
    confidence: float
    citations: list[AgentCitationOut] = Field(default_factory=list)
    agent_run: AgentRunOut


class GraphResearchCreate(BaseModel):
    query: str = Field(min_length=1)
    graph_id: str | None = None
    lens: Literal["all", "research", "engineering", "ops"] = "all"
    provider: str | None = None
    model: str | None = None
    source_policy: Literal["web", "graph", "connectors", "mixed"] = "mixed"


class ResearchTaskOut(BaseModel):
    id: str
    project_id: str
    agent_run_id: str | None = None
    planning_session_id: str | None = None
    query: str
    status: Literal["draft", "queued", "running", "proposal_ready", "blocked", "completed", "failed"]
    provider: str
    model: str
    source_policy: str
    idempotency_key: str
    result: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime
    updated_at: datetime


class GraphResearchOut(BaseModel):
    research_task: ResearchTaskOut
    agent_run: AgentRunOut
    source: SourceOut | None = None
    ingestion_run: IngestionRunOut | None = None
    proposals: list[ProposalOut] = Field(default_factory=list)


class AgentActionApprovalCreate(BaseModel):
    action_proposal_id: str
    decision: Literal["approve", "reject"]
    rationale: str | None = None


class ConnectorAccountCreate(BaseModel):
    kind: ConnectorKind
    display_name: str = Field(min_length=1, max_length=240)
    token_json: dict[str, Any] | None = None
    scopes: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class ConnectorAccountOut(BaseModel):
    id: str
    project_id: str
    kind: ConnectorKind
    display_name: str
    status: ConnectorStatus
    created_by: str
    scopes: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ConnectorTargetCreate(BaseModel):
    account_id: str
    target_type: ConnectorTargetType
    remote_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=240)
    parent_remote_id: str | None = None
    sync_settings: dict[str, Any] = Field(default_factory=dict)


class ConnectorTargetUpdate(BaseModel):
    target_type: ConnectorTargetType | None = None
    remote_id: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    parent_remote_id: str | None = None
    sync_settings: dict[str, Any] | None = None


class ConnectorTargetOut(BaseModel):
    id: str
    project_id: str
    account_id: str
    connector_kind: ConnectorKind
    target_type: ConnectorTargetType
    remote_id: str
    title: str
    parent_remote_id: str | None = None
    sync_settings: dict[str, Any] = Field(default_factory=dict)
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConnectorSyncCreate(BaseModel):
    target_id: str
    force: bool = False


class ConnectorSyncRunOut(BaseModel):
    id: str
    project_id: str
    target_id: str
    status: ConnectorSyncStatus
    stage: str
    source_count: int
    chunk_count: int
    proposal_count: int
    auto_committed_count: int
    error: str | None = None
    trace_id: str
    started_at: datetime
    finished_at: datetime | None = None


class SourceChunkOut(BaseModel):
    id: str
    project_id: str
    source_id: str
    parent_chunk_id: str | None = None
    heading_path: list[str]
    block_type: SourceChunkBlockType
    ordinal: int
    text: str
    links: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    checksum: str
    locator: str
    created_at: datetime


class ExportBundle(BaseModel):
    project: GraphProjectOut
    sources: list[SourceOut]
    topics: list[TopicOut] = Field(default_factory=list)
    nodes: list[ContentNodeOut]
    edges: list[SemanticEdgeOut]
    ingestion_runs: list[IngestionRunOut]
    proposals: list[ProposalOut]
    embeddings: list[EmbeddingOut]
    review_decisions: list[ReviewDecisionOut]
    connector_accounts: list[ConnectorAccountOut] = Field(default_factory=list)
    connector_targets: list[ConnectorTargetOut] = Field(default_factory=list)
    connector_sync_runs: list[ConnectorSyncRunOut] = Field(default_factory=list)
    source_chunks: list[SourceChunkOut] = Field(default_factory=list)
    graph_settings: GraphSettingsOut | None = None
    planning_sessions: list[PlanningSessionOut] = Field(default_factory=list)
    agent_runs: list[AgentRunOut] = Field(default_factory=list)
    research_tasks: list[ResearchTaskOut] = Field(default_factory=list)
    agent_action_proposals: list[AgentActionProposalOut] = Field(default_factory=list)
    activity_events: list[GraphActivityEventOut] = Field(default_factory=list)
    signals: list[SignalOut] = Field(default_factory=list)
    observations: list[ObservationOut] = Field(default_factory=list)
    owners: list[OwnerOut] = Field(default_factory=list)
    routing_policies: list[RoutingPolicyOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    attention_items: list[AttentionItemOut] = Field(default_factory=list)
    decision_records: list[DecisionRecordOut] = Field(default_factory=list)
    action_proposals: list[ActionProposalOut] = Field(default_factory=list)
    action_runs: list[ActionRunOut] = Field(default_factory=list)
    outcomes: list[OutcomeOut] = Field(default_factory=list)
    feedback_events: list[FeedbackEventOut] = Field(default_factory=list)


class BackupMetadataOut(BaseModel):
    schema_version: Literal[1] = 1
    created_at: datetime
    created_by: str
    project_id: str
    source_count: int
    node_count: int
    edge_count: int
    proposal_count: int


class BackupBundle(BaseModel):
    metadata: BackupMetadataOut
    bundle: ExportBundle


class ImportBundle(BaseModel):
    sources: list[SourceCreate] = []
    proposals: list[ProposalCreate] = []
