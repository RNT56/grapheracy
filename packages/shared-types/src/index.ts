export type Id<T extends string> = string & { readonly __type: T };

export type GraphProjectId = Id<"GraphProject">;
export type TopicId = Id<"Topic">;
export type SourceId = Id<"Source">;
export type ContentNodeId = Id<"ContentNode">;
export type SemanticEdgeId = Id<"SemanticEdge">;
export type IngestionRunId = Id<"IngestionRun">;
export type ExtractionProposalId = Id<"ExtractionProposal">;
export type ReviewDecisionId = Id<"ReviewDecision">;
export type ContentEmbeddingId = Id<"ContentEmbedding">;
export type PlanningSessionId = Id<"PlanningSession">;
export type PlanningMessageId = Id<"PlanningMessage">;
export type GraphBuildSpecId = Id<"GraphBuildSpec">;
export type AgentRunId = Id<"AgentRun">;
export type AgentStepId = Id<"AgentStep">;
export type ResearchTaskId = Id<"ResearchTask">;
export type AgentActionProposalId = Id<"AgentActionProposal">;
export type GraphActivityEventId = Id<"GraphActivityEvent">;
export type SignalId = Id<"Signal">;
export type ObservationId = Id<"Observation">;
export type AlertId = Id<"Alert">;
export type AttentionItemId = Id<"AttentionItem">;
export type OwnerId = Id<"Owner">;
export type RoutingPolicyId = Id<"RoutingPolicy">;
export type DecisionRecordId = Id<"DecisionRecord">;
export type ActionProposalId = Id<"ActionProposal">;
export type ActionRunId = Id<"ActionRun">;
export type OutcomeId = Id<"Outcome">;
export type FeedbackEventId = Id<"FeedbackEvent">;
export type AgentContextClientId = Id<"AgentContextClient">;
export type AgentContextSessionId = Id<"AgentContextSession">;
export type AgentContextEventId = Id<"AgentContextEvent">;
export type AgentContextArtifactId = Id<"AgentContextArtifact">;
export type AgentContextBlobId = Id<"AgentContextBlob">;

export type SourceKind = "text" | "markdown" | "url" | "pdf" | "repository" | "ops-document";
export type ConnectorKind = "upload" | "url" | "repository" | "google-workspace" | "notion";

export type ExtractionLensId = "research" | "engineering" | "ops";
export type GraphLensId = "all" | ExtractionLensId;
export type ProviderId = "graphview-local" | "openai" | "anthropic" | "gemini";
export type AgentRunKind = "planning" | "graph_query" | "research" | "action_apply";
export type AgentRunStatus = "queued" | "running" | "waiting_for_review" | "completed" | "failed" | "cancelled";
export type ResearchTaskStatus = "draft" | "queued" | "running" | "proposal_ready" | "blocked" | "completed" | "failed";
export type AgentActionProposalStatus = "pending_review" | "approved" | "rejected" | "applied" | "failed";
export type AgentRunMode = "graph" | "planning";
export type FocusTargetKind = "graph" | "node" | "source" | "chunk" | "proposal" | "plan";
export type AgentToolKind =
  | "graph_query"
  | "source_search"
  | "source_open"
  | "research_run"
  | "proposal_create"
  | "review_action"
  | "connector_sync"
  | "graph_layout";
export type AgentToolStatus = "pending_review" | "running" | "succeeded" | "failed" | "blocked";
export type CaptureAuthority = "gateway" | "adapter_reported" | "passive_reconciled";
export type RuntimeKind = "codex" | "claude-code" | "cursor" | "vscode" | "mcp" | "openai-compatible" | "generic";
export type AgentContextSessionStatus = "running" | "completed" | "failed" | "cancelled";
export type ContextEventKind =
  | "session_started"
  | "heartbeat"
  | "file_opened"
  | "file_read"
  | "selection_changed"
  | "search_performed"
  | "shell_command"
  | "prompt_built"
  | "model_request"
  | "model_response"
  | "edit_applied"
  | "diff_observed"
  | "test_run"
  | "commit_observed"
  | "session_ended";
export type AgentContextArtifactKind =
  | "file"
  | "selection"
  | "search_result"
  | "shell"
  | "prompt"
  | "model"
  | "diff"
  | "test"
  | "commit"
  | "editor"
  | "other";
export type AgentContextContentKind = "text" | "binary" | "metadata";
export type AgentContextRedactionStatus = "redacted" | "not_required" | "metadata_only";
export type AgentContextEncryptionStatus = "encrypted" | "metadata_only";
export type ReviewWorkItemKind =
  | "new_entity"
  | "new_relation"
  | "source_extraction"
  | "research_result"
  | "conflicting_fact"
  | "stale_source"
  | "connector_issue"
  | "planning_action";
export type GraphObjectKind =
  | "graph"
  | "node"
  | "edge"
  | "source"
  | "chunk"
  | "proposal"
  | "review"
  | "agent_run"
  | "tool_call"
  | "signal"
  | "observation"
  | "alert"
  | "attention"
  | "owner"
  | "policy"
  | "decision"
  | "action_proposal"
  | "action_run"
  | "outcome"
  | "feedback"
  | "agent_context_client"
  | "agent_context_session"
  | "agent_context_event"
  | "agent_context_artifact";
export type GraphVisualStatus =
  | "hover"
  | "focus"
  | "related"
  | "dimmed"
  | "scanning"
  | "cited"
  | "incoming"
  | "candidate"
  | "ready"
  | "blocked"
  | "accepted"
  | "rejected"
  | "edited"
  | "deferred"
  | "stale"
  | "sensed"
  | "routed"
  | "assigned"
  | "sla_at_risk"
  | "action_proposed"
  | "action_running"
  | "outcome_waiting"
  | "outcome_succeeded"
  | "outcome_failed"
  | "feedback_applied"
  | "reopened"
  | "context_active"
  | "context_authoritative"
  | "context_reconciled"
  | "context_redacted";
export type GraphActivityEventKind =
  | "graph_hover"
  | "graph_focus"
  | "evidence_cited"
  | "agent_scan"
  | "agent_tool_call"
  | "research_started"
  | "source_incoming"
  | "proposal_candidate"
  | "review_ready"
  | "review_blocked"
  | "review_accepted"
  | "review_rejected"
  | "review_edited"
  | "review_deferred"
  | "knowledge_stale"
  | "signal_sensed"
  | "observation_recorded"
  | "alert_routed"
  | "attention_assigned"
  | "decision_recorded"
  | "action_proposed"
  | "action_approved"
  | "action_running"
  | "outcome_waiting"
  | "outcome_succeeded"
  | "outcome_failed"
  | "feedback_applied"
  | "attention_reopened"
  | "agent_context_started"
  | "agent_context_event"
  | "agent_context_ended";
export type GraphActivityEventStatus = "queued" | "running" | "ready" | "blocked" | "succeeded" | "failed" | "cancelled";
export type SignalKind =
  | "source_changed"
  | "source_stale"
  | "proposal_ready"
  | "proposal_blocked"
  | "conflict_detected"
  | "anomaly_detected"
  | "connector_issue"
  | "agent_action_pending"
  | "decision_due"
  | "outcome_due"
  | "policy_violation";
export type NervousSystemSeverity = "info" | "low" | "medium" | "high" | "critical";
export type SignalStatus = "new" | "linked" | "routed" | "dismissed" | "resolved";
export type AlertStatus = "open" | "assigned" | "blocked" | "resolved" | "dismissed";
export type AttentionStatus =
  | "open"
  | "assigned"
  | "waiting_for_review"
  | "waiting_for_action"
  | "waiting_for_outcome"
  | "resolved"
  | "dismissed"
  | "blocked"
  | "reopened";
export type SlaStatus = "none" | "on_track" | "at_risk" | "overdue";
export type OwnerType = "person" | "team" | "service_account" | "group";
export type OwnershipScopeKind = "project" | "lens" | "topic" | "source" | "node_kind" | "node" | "edge" | "policy" | "action_type" | "connector";
export type DecisionRecordValue = "accept" | "reject" | "approve" | "defer" | "dismiss" | "escalate" | "reopen";
export type ActionProposalStatus =
  | "proposed"
  | "pending_review"
  | "approved"
  | "rejected"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
export type ActionRunStatus = "queued" | "running" | "succeeded" | "failed" | "partial" | "cancelled";
export type OutcomeStatus = "waiting" | "succeeded" | "failed" | "partial" | "unresolved" | "resolved" | "reopened";
export type FeedbackKind = "source_freshness" | "confidence_update" | "priority_update" | "policy_suggestion" | "graph_memory_proposal" | "false_positive";
export type ActionSafetyLevel = "internal_safe" | "graph_mutation" | "external_stub" | "external_side_effect";

export const NODE_KIND_DEFINITIONS = [
  {
    id: "concept",
    label: "Concept",
    category: "knowledge",
    description: "An abstract idea, theme, capability, or knowledge unit."
  },
  {
    id: "topic",
    label: "Topic",
    category: "knowledge",
    description: "A structural knowledge area created from folders, pages, headings, or themes."
  },
  {
    id: "term",
    label: "Term",
    category: "knowledge",
    description: "A named term, definition, acronym, or controlled vocabulary item."
  },
  {
    id: "document",
    label: "Document",
    category: "source",
    description: "A human-readable document, page, memo, PDF, note, or exported office file."
  },
  {
    id: "source",
    label: "Source",
    category: "source",
    description: "An imported, linked, cited, or connector-origin source artifact."
  },
  {
    id: "text",
    label: "Text",
    category: "source",
    description: "Plain text content imported directly or produced by connector extraction."
  },
  {
    id: "markdown",
    label: "Markdown",
    category: "source",
    description: "Markdown notes, pages, documents, and connector exports."
  },
  {
    id: "url",
    label: "URL",
    category: "source",
    description: "A web page, link, external URL, or fetched web source."
  },
  {
    id: "pdf",
    label: "PDF",
    category: "source",
    description: "A PDF document, exported file, or parsed PDF source."
  },
  {
    id: "ops_document",
    label: "Ops",
    category: "source",
    description: "An operational document, process record, policy, or playbook source."
  },
  {
    id: "dataset",
    label: "Dataset",
    category: "source",
    description: "A structured table, CSV, sheet, database extract, or metric data source."
  },
  {
    id: "system",
    label: "System",
    category: "engineering",
    description: "A software system, platform, app, environment, or technical boundary."
  },
  {
    id: "component",
    label: "Component",
    category: "engineering",
    description: "A subsystem, UI surface, library area, package area, or deployable part."
  },
  {
    id: "service",
    label: "Service",
    category: "engineering",
    description: "A service, daemon, backend, worker, queue consumer, or integration surface."
  },
  {
    id: "api",
    label: "API",
    category: "engineering",
    description: "An API, endpoint, protocol, SDK surface, or contract."
  },
  {
    id: "repository",
    label: "Repository",
    category: "engineering",
    description: "A code repository, monorepo, package workspace, or version-controlled project."
  },
  {
    id: "module",
    label: "Module",
    category: "engineering",
    description: "A source module, namespace, importable unit, or code organization layer."
  },
  {
    id: "package",
    label: "Package",
    category: "engineering",
    description: "A dependency, package, library, framework, or imported third-party unit."
  },
  {
    id: "file",
    label: "File",
    category: "engineering",
    description: "A file, path, asset file, generated artifact, or repository object."
  },
  {
    id: "symbol",
    label: "Symbol",
    category: "engineering",
    description: "A class, function, interface, type, constant, route handler, or code symbol."
  },
  {
    id: "workflow",
    label: "Workflow",
    category: "operations",
    description: "A workflow, playbook, lifecycle, approval path, or operating sequence."
  },
  {
    id: "policy",
    label: "Policy",
    category: "operations",
    description: "A policy, standard, governance document, or operating rule."
  },
  {
    id: "process",
    label: "Process",
    category: "operations",
    description: "A process, policy procedure, governance flow, or repeatable operation."
  },
  {
    id: "vendor",
    label: "Vendor",
    category: "operations",
    description: "A vendor, supplier, partner service, or third-party operational dependency."
  },
  {
    id: "decision",
    label: "Decision",
    category: "operations",
    description: "A reviewed decision, tradeoff, exception, recommendation, or recorded choice."
  },
  {
    id: "requirement",
    label: "Requirement",
    category: "operations",
    description: "A requirement, policy obligation, constraint, acceptance criterion, or rule."
  },
  {
    id: "risk",
    label: "Risk",
    category: "operations",
    description: "A risk, blocker, issue, threat, incident class, or unresolved concern."
  },
  {
    id: "metric",
    label: "Metric",
    category: "product",
    description: "A KPI, measure, threshold, score, signal, or tracked quantitative value."
  },
  {
    id: "event",
    label: "Event",
    category: "product",
    description: "An event, incident, release, milestone, session, or time-bound occurrence."
  },
  {
    id: "incident",
    label: "Incident",
    category: "operations",
    description: "An incident, outage, response record, postmortem, or operational event."
  },
  {
    id: "project",
    label: "Project",
    category: "operations",
    description: "A project, initiative, program, rollout, migration, or coordinated body of work."
  },
  {
    id: "owner",
    label: "Owner",
    category: "people",
    description: "An accountable person, team, group, or organization that owns operational work."
  },
  {
    id: "review_cycle",
    label: "Review Cycle",
    category: "operations",
    description: "A review cadence, freshness requirement, expiration policy, or recurring checkpoint."
  },
  {
    id: "task",
    label: "Task",
    category: "product",
    description: "A task, issue, ticket, action item, backlog item, or unit of work."
  },
  {
    id: "person",
    label: "Person",
    category: "people",
    description: "A person, author, owner, stakeholder, or contributor."
  },
  {
    id: "team",
    label: "Team",
    category: "people",
    description: "A team, group, squad, department, or functional owner."
  },
  {
    id: "organization",
    label: "Organization",
    category: "people",
    description: "An organization, vendor, customer, partner, company, or institution."
  },
  {
    id: "product",
    label: "Product",
    category: "product",
    description: "A product, app, service offering, customer-facing surface, or business line."
  },
  {
    id: "feature",
    label: "Feature",
    category: "product",
    description: "A feature, user-facing capability, screen, behavior, or product area."
  },
  {
    id: "asset",
    label: "Asset",
    category: "source",
    description: "A media asset, design asset, binary artifact, model, fixture, or reusable resource."
  },
  {
    id: "location",
    label: "Location",
    category: "people",
    description: "A place, region, office, deployment location, market, or physical context."
  }
] as const;

export type ContentNodeKind = (typeof NODE_KIND_DEFINITIONS)[number]["id"];
export type NodeKindCategory = (typeof NODE_KIND_DEFINITIONS)[number]["category"];

export interface NodeKindDefinition {
  id: ContentNodeKind;
  label: string;
  category: NodeKindCategory;
  description: string;
}

export const CONTENT_NODE_KIND_IDS = NODE_KIND_DEFINITIONS.map((definition) => definition.id);

const NODE_KIND_ID_SET = new Set<string>(CONTENT_NODE_KIND_IDS);

export const NODE_KIND_ALIASES: Record<string, ContentNodeKind> = {
  acronym: "term",
  action: "task",
  action_item: "task",
  artifact: "asset",
  backlog: "task",
  block: "topic",
  chart: "metric",
  class: "symbol",
  collection: "topic",
  company: "organization",
  constraint: "requirement",
  customer: "organization",
  dependency: "package",
  doc: "document",
  endpoint: "api",
  entity: "concept",
  file_path: "file",
  folder: "topic",
  framework: "package",
  function: "symbol",
  goal: "requirement",
  group: "team",
  heading: "topic",
  incident_response: "incident",
  integration: "service",
  issue: "task",
  kpi: "metric",
  library: "package",
  link: "source",
  memo: "document",
  milestone: "event",
  note: "document",
  org: "organization",
  owner_team: "owner",
  page: "document",
  path: "file",
  policy_document: "policy",
  procedure: "process",
  program: "project",
  pull_request: "task",
  repo: "repository",
  resource: "asset",
  review: "review_cycle",
  review_cadence: "review_cycle",
  route: "api",
  sdk: "api",
  squad: "team",
  table: "dataset",
  ticket: "task",
  url: "source",
  supplier: "vendor"
};

export function isContentNodeKind(kind: string): kind is ContentNodeKind {
  return NODE_KIND_ID_SET.has(kind);
}

export function normalizeContentNodeKind(kind: string | null | undefined): ContentNodeKind {
  const normalized = (kind ?? "").trim().toLowerCase().replaceAll(/[\s-]+/g, "_");
  if (isContentNodeKind(normalized)) return normalized;
  return NODE_KIND_ALIASES[normalized] ?? "concept";
}

export interface ExtractionLensDescriptor {
  id: ExtractionLensId;
  label: string;
  summary: string;
  defaultProposalLimit: number;
  sourceKinds: SourceKind[];
  primaryNodeKinds: ContentNodeKind[];
  provenanceFields: string[];
}

export interface GraphLensDescriptor {
  id: GraphLensId;
  label: string;
  summary: string;
  activeByDefault: boolean;
}

export interface GraphInsightCount {
  name: string;
  count: number;
}

export interface GraphInsightTopNode {
  id: ContentNodeId;
  label: string;
  kind: ContentNodeKind;
  degree: number;
}

export interface GraphInsights {
  projectId: GraphProjectId;
  generatedAt: string;
  nodeCount: number;
  edgeCount: number;
  sourceCount: number;
  proposalCount: number;
  pendingProposalCount: number;
  reviewDecisionCount: number;
  connectedEdgeCount: number;
  orphanEdgeCount: number;
  provenanceCoverage: {
    reviewedItemCount: number;
    tracedItemCount: number;
    missingItemCount: number;
    coveragePercent: number;
  };
  sourceKinds: GraphInsightCount[];
  nodeKinds: GraphInsightCount[];
  relationCounts: GraphInsightCount[];
  proposalStatuses: GraphInsightCount[];
  topNodes: GraphInsightTopNode[];
}

export interface GraphNeighborhood {
  centerNode: ContentNode;
  depth: number;
  limit: number;
  nodes: ContentNode[];
  edges: SemanticEdge[];
  omittedNodeCount: number;
  omittedEdgeCount: number;
}

export interface GraphPath {
  sourceNode: ContentNode;
  targetNode: ContentNode;
  maxDepth: number;
  pathFound: boolean;
  distance?: number;
  nodes: ContentNode[];
  edges: SemanticEdge[];
}

export interface GraphObjectRef {
  kind: GraphObjectKind;
  id: string;
  label?: string;
}

export interface GraphVisualState {
  object: GraphObjectRef;
  statuses: GraphVisualStatus[];
  active: boolean;
  intensity: number;
  reason?: string;
  updatedAt?: string;
}

export interface GraphTooltipModel {
  object: GraphObjectRef;
  title: string;
  kindLabel: string;
  summary?: string;
  contains?: string[];
  url?: string;
  citations: AgentCitation[];
  statuses: GraphVisualStatus[];
  metadata: Record<string, unknown>;
}

export interface GraphActivityEvent {
  id: GraphActivityEventId;
  projectId: GraphProjectId;
  graphId?: string;
  kind: GraphActivityEventKind;
  status: GraphActivityEventStatus;
  subject: GraphObjectRef;
  actorId?: string;
  agentRunId?: AgentRunId;
  agentToolCallId?: string;
  sourceIds: SourceId[];
  sourceChunkIds: SourceChunk["id"][];
  nodeIds: ContentNodeId[];
  edgeIds: SemanticEdgeId[];
  proposalIds: ExtractionProposalId[];
  reviewDecisionIds: ReviewDecisionId[];
  citations: AgentCitation[];
  summary: string;
  metadata: Record<string, unknown>;
  occurredAt: string;
}

export interface Signal {
  id: SignalId;
  projectId: GraphProjectId;
  graphId?: string;
  kind: SignalKind;
  status: SignalStatus;
  severity: NervousSystemSeverity;
  sourceKind: "manual" | "api" | "connector" | "schedule" | "webhook" | "agent";
  sourceId?: SourceId;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  checksum: string;
  traceId: string;
  actorId?: string;
  receivedAt: string;
  createdAt: string;
}

export interface Observation {
  id: ObservationId;
  projectId: GraphProjectId;
  signalId?: SignalId;
  kind: string;
  summary: string;
  confidence?: number;
  evidence: AgentCitation[];
  objectRefs: GraphObjectRef[];
  sourceIds: SourceId[];
  nodeIds: ContentNodeId[];
  edgeIds: SemanticEdgeId[];
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface Owner {
  id: OwnerId;
  projectId: GraphProjectId;
  ownerType: OwnerType;
  displayName: string;
  contact?: string;
  scopeKind: OwnershipScopeKind;
  scopeId?: string;
  escalationContact?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface RoutingPolicy {
  id: RoutingPolicyId;
  projectId: GraphProjectId;
  name: string;
  description?: string;
  enabled: boolean;
  match: Record<string, unknown>;
  severity: NervousSystemSeverity;
  ownerId?: OwnerId;
  slaSeconds?: number;
  suggestedActions: string[];
  approvalRequired: boolean;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface Alert {
  id: AlertId;
  projectId: GraphProjectId;
  signalId?: SignalId;
  observationId?: ObservationId;
  ownerId?: OwnerId;
  policyId?: RoutingPolicyId;
  severity: NervousSystemSeverity;
  status: AlertStatus;
  title: string;
  summary: string;
  reason: string;
  objectRefs: GraphObjectRef[];
  dueAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface AttentionItem {
  id: AttentionItemId;
  projectId: GraphProjectId;
  kind: string;
  status: AttentionStatus;
  severity: NervousSystemSeverity;
  slaStatus: SlaStatus;
  title: string;
  summary: string;
  ownerId?: OwnerId;
  assigneeId?: string;
  dueAt?: string;
  sourceId?: SourceId;
  signalId?: SignalId;
  observationId?: ObservationId;
  alertId?: AlertId;
  proposalId?: ExtractionProposalId;
  decisionRecordId?: DecisionRecordId;
  actionProposalId?: ActionProposalId;
  actionRunId?: ActionRunId;
  outcomeId?: OutcomeId;
  feedbackEventId?: FeedbackEventId;
  objectRefs: GraphObjectRef[];
  evidence: AgentCitation[];
  suggestedActions: string[];
  blockers: string[];
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string;
}

export interface DecisionRecord {
  id: DecisionRecordId;
  projectId: GraphProjectId;
  alertId?: AlertId;
  attentionItemId?: AttentionItemId;
  proposalId?: ExtractionProposalId;
  decision: DecisionRecordValue;
  rationale: string;
  actorId: string;
  evidence: AgentCitation[];
  objectRefs: GraphObjectRef[];
  createdAt: string;
}

export interface ActionSafetyMetadata {
  safetyLevel: ActionSafetyLevel;
  mutatesGraphview: boolean;
  callsExternalSystem: boolean;
  transfersPrivateContent: boolean;
  approvalRequired: boolean;
}

export interface ActionProposal {
  id: ActionProposalId;
  projectId: GraphProjectId;
  decisionRecordId?: DecisionRecordId;
  alertId?: AlertId;
  attentionItemId?: AttentionItemId;
  actionType: string;
  status: ActionProposalStatus;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  redactedPayload: Record<string, unknown>;
  safety: ActionSafetyMetadata;
  approvalRequired: boolean;
  createdBy: string;
  approvedBy?: string;
  rejectedBy?: string;
  rationale?: string;
  createdAt: string;
  updatedAt: string;
  decidedAt?: string;
}

export interface ActionRun {
  id: ActionRunId;
  projectId: GraphProjectId;
  actionProposalId: ActionProposalId;
  actionType: string;
  status: ActionRunStatus;
  executorId: string;
  target?: string;
  redactedPayload: Record<string, unknown>;
  externalId?: string;
  traceId: string;
  errorCode?: string;
  error?: string;
  startedAt: string;
  finishedAt?: string;
}

export interface Outcome {
  id: OutcomeId;
  projectId: GraphProjectId;
  actionRunId?: ActionRunId;
  attentionItemId?: AttentionItemId;
  alertId?: AlertId;
  status: OutcomeStatus;
  title: string;
  summary: string;
  result: Record<string, unknown>;
  actorId: string;
  occurredAt: string;
  createdAt: string;
}

export interface FeedbackEvent {
  id: FeedbackEventId;
  projectId: GraphProjectId;
  outcomeId?: OutcomeId;
  actionRunId?: ActionRunId;
  attentionItemId?: AttentionItemId;
  kind: FeedbackKind;
  summary: string;
  effect: Record<string, unknown>;
  proposedValue?: Record<string, unknown>;
  actorId: string;
  createdAt: string;
}

export interface ReviewQueueItem {
  proposal: ExtractionProposal;
  source?: Source;
  priorityScore: number;
  action: "review_node" | "review_relationship" | "accept_endpoints";
  workItemKind?: ReviewWorkItemKind;
  changeSummary?: string;
  evidenceSummary?: string;
  affectedGraphIds?: string[];
  citations?: AgentCitation[];
  blocked: boolean;
  readyToCommit: boolean;
  reason: string;
  endpointNodeIds: ContentNodeId[];
  missingEndpointNodeIds: ContentNodeId[];
}

export interface ReviewQueue {
  generatedAt: string;
  pendingCount: number;
  readyCount: number;
  blockedCount: number;
  items: ReviewQueueItem[];
}

export interface ReviewDashboard {
  projectId: GraphProjectId;
  generatedAt: string;
  proposalCount: number;
  pendingCount: number;
  readyCount: number;
  blockedCount: number;
  reviewDecisionCount: number;
  acceptedCount: number;
  rejectedCount: number;
  editedCount: number;
  deferredCount: number;
  acceptanceRate: number;
  commitRate: number;
  proposalKindCounts: GraphInsightCount[];
  pendingKindCounts: GraphInsightCount[];
  decisionCounts: GraphInsightCount[];
  reviewerCounts: GraphInsightCount[];
  oldestPendingProposalId?: ExtractionProposalId;
  oldestPendingCreatedAt?: string;
}

export interface ReviewActivityItem {
  decision: ReviewDecision;
  proposal?: ExtractionProposal;
  source?: Source;
  summary: string;
}

export interface ReviewActivity {
  generatedAt: string;
  reviewDecisionCount: number;
  returnedCount: number;
  items: ReviewActivityItem[];
}

export interface SourceReviewSummary {
  source: Source;
  status: "no_proposals" | "pending_review" | "mixed" | "reviewed";
  proposalCount: number;
  pendingCount: number;
  reviewedCount: number;
  decisionCount: number;
  acceptedCount: number;
  rejectedCount: number;
  editedCount: number;
  deferredCount: number;
  lastReviewedAt?: string;
}

export interface SourceReviewCoverage {
  generatedAt: string;
  sourceCount: number;
  proposalCount: number;
  pendingCount: number;
  reviewedCount: number;
  returnedCount: number;
  sources: SourceReviewSummary[];
}

export interface Provenance {
  sourceId: SourceId;
  sourceUri?: string;
  locator?: string;
  extractedBy?: "human" | "worker" | "import";
  actorId?: string;
  ingestionRunId?: IngestionRunId;
  observedAt: string;
  traceId: string;
}

export interface GraphProject {
  id: GraphProjectId;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
}

export interface Topic {
  id: TopicId;
  projectId: GraphProjectId;
  name: string;
  description?: string;
  parentTopicId?: TopicId;
  createdAt: string;
  updatedAt: string;
}

export interface Source {
  id: SourceId;
  projectId: GraphProjectId;
  kind: SourceKind;
  title: string;
  uri?: string;
  objectKey?: string;
  checksum?: string;
  connectorKind?: ConnectorKind;
  remoteId?: string;
  remoteParentId?: string;
  remoteModifiedAt?: string;
  remoteUrl?: string;
  metadata?: Record<string, unknown>;
  staleAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ContentNode {
  id: ContentNodeId;
  projectId: GraphProjectId;
  topicIds: TopicId[];
  label: string;
  kind: ContentNodeKind;
  summary?: string;
  metadata?: Record<string, unknown>;
  provenance: Provenance[];
  createdAt: string;
  updatedAt: string;
}

export interface SemanticEdge {
  id: SemanticEdgeId;
  projectId: GraphProjectId;
  sourceNodeId: ContentNodeId;
  targetNodeId: ContentNodeId;
  relation:
    | "supports"
    | "contradicts"
    | "depends_on"
    | "causes"
    | "mentions"
    | "defines"
    | "relates_to"
    | "contains"
    | "part_of"
    | "references"
    | "imports"
    | "implements"
    | "owned_by"
    | "has_review_cycle"
    | "governs";
  weight?: number;
  metadata?: Record<string, unknown>;
  provenance: Provenance[];
  createdAt: string;
  updatedAt: string;
}

export interface GraphSettings {
  projectId: GraphProjectId;
  llmEnabled: boolean;
  llmProvider?: string;
  llmModel?: string;
  autoCommitThreshold: number;
  settings: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface ConnectorAccount {
  id: Id<"ConnectorAccount">;
  projectId: GraphProjectId;
  kind: ConnectorKind;
  displayName: string;
  status: "connected" | "disabled" | "error";
  createdBy: string;
  scopes: string[];
  settings: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface ConnectorTarget {
  id: Id<"ConnectorTarget">;
  projectId: GraphProjectId;
  accountId: ConnectorAccount["id"];
  connectorKind: ConnectorKind;
  targetType: "file" | "folder" | "page" | "database" | "repository" | "url" | "upload";
  remoteId: string;
  title: string;
  parentRemoteId?: string;
  syncSettings: Record<string, unknown>;
  lastSyncedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ConnectorSyncRun {
  id: Id<"ConnectorSyncRun">;
  projectId: GraphProjectId;
  targetId: ConnectorTarget["id"];
  status: "running" | "completed" | "failed";
  stage: string;
  sourceCount: number;
  chunkCount: number;
  proposalCount: number;
  autoCommittedCount: number;
  error?: string;
  traceId: string;
  startedAt: string;
  finishedAt?: string;
}

export interface SourceChunk {
  id: Id<"SourceChunk">;
  projectId: GraphProjectId;
  sourceId: SourceId;
  parentChunkId?: SourceChunk["id"];
  headingPath: string[];
  blockType: "document" | "heading" | "paragraph" | "table" | "list" | "code" | "link" | "metadata";
  ordinal: number;
  text: string;
  links: string[];
  mentions: string[];
  checksum: string;
  locator: string;
  createdAt: string;
}

export interface IngestionRun {
  id: IngestionRunId;
  projectId: GraphProjectId;
  sourceId: SourceId;
  status: "queued" | "running" | "proposal_ready" | "committed" | "failed" | "cancelled";
  stage: "fetch" | "extract" | "analyze" | "embed" | "propose" | "commit";
  traceId: string;
  startedAt?: string;
  finishedAt?: string;
  errorCode?: string;
}

export interface ExtractionProposal {
  id: ExtractionProposalId;
  projectId: GraphProjectId;
  ingestionRunId: IngestionRunId;
  kind: "content_node" | "semantic_edge";
  status: "pending_review" | "accepted" | "rejected" | "edited" | "deferred";
  proposedValue: unknown;
  confidence?: number;
  provenance: Provenance[];
  createdAt: string;
}

export interface ReviewDecision {
  id: ReviewDecisionId;
  projectId: GraphProjectId;
  proposalId: ExtractionProposalId;
  reviewerId: string;
  decision: "accept" | "reject" | "edit" | "defer";
  editedValue?: unknown;
  rationale?: string;
  decidedAt: string;
}

export interface ContentEmbedding {
  id: ContentEmbeddingId;
  projectId: GraphProjectId;
  proposalId?: ExtractionProposalId;
  contentNodeId?: ContentNodeId;
  embeddingModel: string;
  vector: number[];
  createdAt: string;
}

export interface ProviderModelDescriptor {
  id: string;
  label: string;
  default: boolean;
  capabilities: string[];
  contextWindow?: number;
}

export interface ProviderDescriptor {
  id: ProviderId;
  label: string;
  enabled: boolean;
  configured: boolean;
  defaultModel: string;
  capabilities: string[];
  models: ProviderModelDescriptor[];
}

export interface AgentCitation {
  id: string;
  label: string;
  sourceId?: SourceId;
  sourceTitle?: string;
  sourceChunkId?: SourceChunk["id"];
  nodeId?: ContentNodeId;
  proposalId?: ExtractionProposalId;
  locator?: string;
  quote?: string;
  url?: string;
  confidence?: number;
}

export interface AgentStep {
  id: AgentStepId;
  projectId: GraphProjectId;
  agentRunId: AgentRunId;
  name: string;
  status: string;
  inputSummary?: string;
  outputSummary?: string;
  error?: string;
  traceId: string;
  metadata: Record<string, unknown>;
  startedAt: string;
  finishedAt?: string;
}

export interface AgentActionProposal {
  id: AgentActionProposalId;
  projectId: GraphProjectId;
  agentRunId: AgentRunId;
  actionType: string;
  status: AgentActionProposalStatus;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  citations: AgentCitation[];
  confidence?: number;
  createdAt: string;
  updatedAt: string;
  appliedAt?: string;
}

export interface FocusTarget {
  kind: FocusTargetKind;
  id?: string;
  label?: string;
}

export interface AgentGeneratedArtifact {
  id: string;
  kind: "plan" | "source" | "subgraph" | "proposal_diff" | "evidence_bundle";
  title: string;
  payload: Record<string, unknown>;
  citations: AgentCitation[];
}

export interface AgentToolCall {
  id: string;
  kind: AgentToolKind;
  input: Record<string, unknown>;
  status: AgentToolStatus;
  citations: AgentCitation[];
  affectedGraphIds: string[];
  resultingProposalId?: ExtractionProposalId | AgentActionProposalId;
  summary?: string;
  startedAt?: string;
  finishedAt?: string;
}

export interface AgentRun {
  id: AgentRunId;
  projectId: GraphProjectId;
  planningSessionId?: PlanningSessionId;
  kind: AgentRunKind;
  mode?: AgentRunMode;
  focusTarget?: FocusTarget;
  status: AgentRunStatus;
  provider: ProviderId | string;
  model: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  traceId: string;
  createdBy: string;
  startedAt: string;
  finishedAt?: string;
  error?: string;
  steps: AgentStep[];
  toolCalls?: AgentToolCall[];
  generatedArtifacts?: AgentGeneratedArtifact[];
  actionProposals: AgentActionProposal[];
}

export interface AgentContextClient {
  id: AgentContextClientId;
  projectId: GraphProjectId;
  displayName: string;
  runtimeKind: RuntimeKind;
  status: "active" | "revoked";
  createdBy: string;
  scopes: string[];
  settings: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  lastSeenAt?: string;
  revokedAt?: string;
}

export interface AgentContextSession {
  id: AgentContextSessionId;
  projectId: GraphProjectId;
  clientId: AgentContextClientId;
  runtimeKind: RuntimeKind;
  authority: CaptureAuthority;
  status: AgentContextSessionStatus;
  title: string;
  workspaceRoot?: string;
  repositoryUri?: string;
  branch?: string;
  commitSha?: string;
  metadata: Record<string, unknown>;
  startedAt: string;
  endedAt?: string;
  updatedAt: string;
}

export interface AgentContextArtifact {
  id: AgentContextArtifactId;
  projectId: GraphProjectId;
  sessionId: AgentContextSessionId;
  kind: AgentContextArtifactKind;
  uri?: string;
  path?: string;
  title: string;
  contentType: string;
  checksum?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface AgentContextBlob {
  id: AgentContextBlobId;
  projectId: GraphProjectId;
  sessionId: AgentContextSessionId;
  artifactId?: AgentContextArtifactId;
  contentKind: AgentContextContentKind;
  mediaType: string;
  redactionStatus: AgentContextRedactionStatus;
  encryptionStatus: AgentContextEncryptionStatus;
  checksum: string;
  byteCount: number;
  tokenCount?: number;
  metadata: Record<string, unknown>;
  createdAt: string;
  expiresAt?: string;
}

export interface AgentContextEvent {
  id: AgentContextEventId;
  projectId: GraphProjectId;
  sessionId: AgentContextSessionId;
  clientEventId: string;
  sequence: number;
  eventKind: ContextEventKind;
  authority: CaptureAuthority;
  status: "accepted" | "duplicate" | "rejected";
  summary: string;
  checksum: string;
  artifactId?: AgentContextArtifactId;
  blobId?: AgentContextBlobId;
  payload: Record<string, unknown>;
  objectRefs: GraphObjectRef[];
  occurredAt: string;
  receivedAt: string;
}

export interface AgentContextGraphNode {
  id: string;
  kind: string;
  label: string;
  authority?: CaptureAuthority;
  metadata: Record<string, unknown>;
}

export interface AgentContextGraphEdge {
  id: string;
  sourceId: string;
  targetId: string;
  relation: string;
  observed: boolean;
  metadata: Record<string, unknown>;
}

export interface AgentContextGraph {
  session: AgentContextSession;
  nodes: AgentContextGraphNode[];
  edges: AgentContextGraphEdge[];
  artifacts: AgentContextArtifact[];
  events: AgentContextEvent[];
}

export interface AgentContextEventBatchResult {
  session: AgentContextSession;
  acceptedCount: number;
  duplicateCount: number;
  rejectedCount: number;
  events: AgentContextEvent[];
}

export interface GraphBuildSpec {
  id: GraphBuildSpecId;
  projectId: GraphProjectId;
  sessionId: PlanningSessionId;
  version: number;
  title: string;
  objective: string;
  status: "draft" | "approved" | "archived" | string;
  spec: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface PlanningMessage {
  id: PlanningMessageId;
  projectId: GraphProjectId;
  sessionId: PlanningSessionId;
  agentRunId?: AgentRunId;
  role: "user" | "assistant" | "system";
  content: string;
  provider?: ProviderId | string;
  model?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface PlanningSession {
  id: PlanningSessionId;
  projectId: GraphProjectId;
  graphId?: string;
  lens: GraphLensId;
  title: string;
  goal: string;
  status: "active" | "archived" | string;
  provider?: ProviderId | string;
  model?: string;
  createdBy: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  messages: PlanningMessage[];
  buildSpec?: GraphBuildSpec;
}

export interface ResearchTask {
  id: ResearchTaskId;
  projectId: GraphProjectId;
  agentRunId?: AgentRunId;
  planningSessionId?: PlanningSessionId;
  query: string;
  status: ResearchTaskStatus;
  provider: ProviderId | string;
  model: string;
  sourcePolicy: "web" | "graph" | "connectors" | "mixed" | string;
  idempotencyKey: string;
  result: Record<string, unknown>;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface GraphQueryRequest {
  question: string;
  graphId?: string;
  lens: GraphLensId;
  nodeId?: ContentNodeId;
  sourceId?: SourceId;
  provider?: ProviderId | string;
  model?: string;
}

export interface GraphQueryAnswer {
  answer: string;
  confidence: number;
  citations: AgentCitation[];
  agentRun: AgentRun;
}

export type GraphviewEventName =
  | "source.created"
  | "ingestion.started"
  | "proposal.ready"
  | "review.committed"
  | "graph.updated";

export interface GraphviewEvent<TPayload = unknown> {
  id: string;
  name: GraphviewEventName;
  schemaVersion: 1;
  projectId: GraphProjectId;
  actorId?: string;
  traceId: string;
  occurredAt: string;
  payload: TPayload;
}
