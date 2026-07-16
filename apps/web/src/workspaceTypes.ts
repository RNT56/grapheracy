import type {
  ContentNode,
  ExtractionLensDescriptor,
  GraphActivityEvent,
  GraphLensId,
  SourceKind
} from "@graphview/shared-types";

export interface ApiSource {
  id: string;
  title: string;
  kind: string;
  uri?: string | null;
  connector_kind?: "upload" | "url" | "repository" | "google-workspace" | "notion" | null;
  remote_id?: string | null;
  remote_parent_id?: string | null;
  remote_url?: string | null;
  metadata?: Record<string, unknown> | null;
  stale_at?: string | null;
}

export interface ApiProposal {
  id: string;
  kind: "content_node" | "semantic_edge";
  status: string;
  proposed_value: {
    label?: string;
    kind?: string;
    summary?: string;
    relation?: string;
    id?: string;
    sourceNodeId?: string;
    targetNodeId?: string;
    sourceLabel?: string;
    targetLabel?: string;
    weight?: number;
    metadata?: Record<string, unknown>;
  };
}

export interface ApiGraphProject {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiContentNode {
  id: string;
  project_id: string;
  topic_ids: string[];
  label: string;
  kind: string;
  summary?: string | null;
  metadata?: Record<string, unknown> | null;
  provenance: [];
  created_at: string;
  updated_at: string;
}

export interface ApiSemanticEdge {
  id: string;
  project_id: string;
  source_node_id: string;
  target_node_id: string;
  relation: string;
  weight?: number | null;
  metadata?: Record<string, unknown> | null;
  provenance: [];
  created_at: string;
  updated_at: string;
}

export interface ApiGraph {
  project: ApiGraphProject;
  nodes: ApiContentNode[];
  edges: ApiSemanticEdge[];
}

export interface ApiGraphView {
  id: string;
  project_id: string;
  label: string;
  description?: string | null;
  kind: "project" | "scope";
  source_ids: string[];
  node_count: number;
  edge_count: number;
  source_count: number;
  pending_proposal_count: number;
}

export interface ApiLineage {
  entity_kind: "source" | "proposal" | "node" | "edge";
  entity_id: string;
  source?: ApiSource | null;
  proposals: ApiProposal[];
  review_decisions: unknown[];
  nodes: ApiContentNode[];
  edges: ApiSemanticEdge[];
  provenance: unknown[];
}

export interface ApiInsights {
  node_count: number;
  edge_count: number;
  source_count: number;
  proposal_count: number;
  pending_proposal_count: number;
  connected_edge_count: number;
  orphan_edge_count: number;
  provenance_coverage: {
    reviewed_item_count: number;
    traced_item_count: number;
    missing_item_count: number;
    coverage_percent: number;
  };
  top_nodes: Array<{
    id: string;
    label: string;
    kind: string;
    degree: number;
  }>;
}

export interface ApiNeighborhood {
  center_node: ApiContentNode;
  depth: number;
  limit: number;
  nodes: ApiContentNode[];
  edges: ApiSemanticEdge[];
  omitted_node_count: number;
  omitted_edge_count: number;
}

export interface ApiPath {
  source_node: ApiContentNode;
  target_node: ApiContentNode;
  max_depth: number;
  path_found: boolean;
  distance?: number | null;
  nodes: ApiContentNode[];
  edges: ApiSemanticEdge[];
}

export interface ApiReviewQueue {
  pending_count: number;
  ready_count: number;
  blocked_count: number;
  items: Array<{
    proposal: ApiProposal;
    source?: ApiSource | null;
    priority_score: number;
    action: "review_node" | "review_relationship" | "accept_endpoints";
    work_item_kind?: ReviewWorkItemKind | null;
    change_summary?: string | null;
    evidence_summary?: string | null;
    affected_graph_ids?: string[];
    citations?: ApiAgentCitation[];
    blocked: boolean;
    ready_to_commit: boolean;
    reason: string;
    endpoint_node_ids: string[];
    missing_endpoint_node_ids: string[];
  }>;
}

export interface ApiReviewDashboard {
  proposal_count: number;
  pending_count: number;
  ready_count: number;
  blocked_count: number;
  review_decision_count: number;
  accepted_count: number;
  rejected_count: number;
  edited_count: number;
  deferred_count: number;
  acceptance_rate: number;
  commit_rate: number;
  oldest_pending_proposal_id?: string | null;
  oldest_pending_created_at?: string | null;
}

export interface ApiReviewActivity {
  review_decision_count: number;
  returned_count: number;
  items: Array<{
    decision: {
      id: string;
      reviewer_id: string;
      decision: "accept" | "reject" | "edit" | "defer";
      decided_at: string;
    };
    proposal?: ApiProposal | null;
    source?: ApiSource | null;
    summary: string;
  }>;
}

export interface ApiSourceReviewCoverage {
  source_count: number;
  proposal_count: number;
  pending_count: number;
  reviewed_count: number;
  returned_count: number;
  sources: Array<{
    source: ApiSource;
    status: "no_proposals" | "pending_review" | "mixed" | "reviewed";
    proposal_count: number;
    pending_count: number;
    reviewed_count: number;
    decision_count: number;
    accepted_count: number;
    rejected_count: number;
    edited_count: number;
    deferred_count: number;
    last_reviewed_at?: string | null;
  }>;
}

export interface ApiExtractionLens {
  id: ExtractionLensDescriptor["id"];
  label: string;
  summary: string;
  default_proposal_limit: number;
  source_kinds: SourceKind[];
  primary_node_kinds: ContentNode["kind"][];
  provenance_fields: string[];
}

export interface ApiGraphLens {
  id: GraphLensId;
  label: string;
  summary: string;
  active_by_default: boolean;
}

export interface ApiConnectorDescriptor {
  kind: "upload" | "url" | "repository" | "google-workspace" | "notion";
  label: string;
  summary: string;
  target_types: string[];
  requires_account: boolean;
}

export interface ApiConnectorAccount {
  id: string;
  kind: ApiConnectorDescriptor["kind"];
  display_name: string;
  status: string;
  scopes: string[];
  settings: Record<string, unknown>;
}

export interface ApiConnectorTarget {
  id: string;
  account_id: string;
  connector_kind: ApiConnectorDescriptor["kind"];
  target_type: "file" | "folder" | "page" | "database" | "repository" | "url" | "upload";
  remote_id: string;
  title: string;
  sync_settings: Record<string, unknown>;
  last_synced_at?: string | null;
}

export interface ApiConnectorSyncRun {
  id: string;
  target_id: string;
  status: string;
  stage: string;
  source_count: number;
  chunk_count: number;
  proposal_count: number;
  auto_committed_count: number;
  error?: string | null;
  started_at: string;
  finished_at?: string | null;
}

export interface ApiGraphSettings {
  llm_enabled: boolean;
  llm_provider?: string | null;
  llm_model?: string | null;
  auto_commit_threshold: number;
  settings: Record<string, unknown>;
}

export interface ApiSourceChunk {
  id: string;
  source_id: string;
  heading_path: string[];
  block_type: string;
  ordinal: number;
  text: string;
  links: string[];
  mentions: string[];
  locator: string;
}

export interface SourceContentBlock {
  id: string;
  heading_path: string[];
  block_type: string;
  ordinal: number;
  text: string;
  links: string[];
  mentions: string[];
  locator: string;
}

export type ContextPaneTab = "data" | "review";
export type MobileSection = "graph" | "sources" | "focus" | "ask" | "review" | "plan" | "context";
export type WorkspaceMode = "graph" | "planning" | "settings" | "context";
export type SettingsPageId = "providers" | "credentials" | "automation" | "runtime" | "capabilities";
export type GraphViewMode = "overview" | "focus" | "evidence" | "review" | "attention";
export type CaptureAuthority = "gateway" | "adapter_reported" | "passive_reconciled";
export type ReviewWorkItemKind =
  | "new_entity"
  | "new_relation"
  | "source_extraction"
  | "research_result"
  | "conflicting_fact"
  | "stale_source"
  | "connector_issue"
  | "planning_action";
export type AgentToolKind =
  | "graph_query"
  | "source_search"
  | "source_open"
  | "research_run"
  | "proposal_create"
  | "review_action"
  | "connector_sync"
  | "graph_layout";

export interface AttentionItem {
  id: string;
  title: string;
  meta: string;
  detail: string;
  tone: "review" | "source" | "sync" | "lineage" | "research" | "operation";
  actionLabel: string;
}

export type ApiProviderId = "graphview-local" | "openai" | "anthropic" | "gemini";

export const SETTINGS_PAGES: Array<{ id: SettingsPageId; label: string; summary: string }> = [
  { id: "providers", label: "Providers", summary: "Model routing and availability" },
  { id: "credentials", label: "Credentials", summary: "Keys and default provider" },
  { id: "automation", label: "Automation", summary: "Extraction and commit rules" },
  { id: "runtime", label: "Runtime", summary: "Current operating defaults" },
  { id: "capabilities", label: "Capabilities", summary: "Provider feature coverage" }
];

export interface ApiProviderDescriptor {
  id: ApiProviderId;
  label: string;
  enabled: boolean;
  configured: boolean;
  default_model: string;
  capabilities: string[];
  models?: ApiProviderModelDescriptor[];
}

export interface ApiProviderModelDescriptor {
  id: string;
  label: string;
  default: boolean;
  capabilities: string[];
  context_window?: number | null;
}

export const fallbackProviders: ApiProviderDescriptor[] = [
  {
    id: "graphview-local",
    label: "Graphview Local",
    enabled: true,
    configured: true,
    default_model: "graphview-local-deterministic-v1",
    capabilities: ["planning", "graph_query", "research", "structured_output"],
    models: [
      {
        id: "graphview-local-deterministic-v1",
        label: "Local deterministic",
        default: true,
        capabilities: ["planning", "graph_query", "research", "structured_output"]
      }
    ]
  },
  {
    id: "openai",
    label: "OpenAI",
    enabled: false,
    configured: false,
    default_model: "gpt-5.5",
    capabilities: ["planning", "graph_query", "research", "structured_output", "tool_calling"],
    models: [
      { id: "gpt-5.5", label: "gpt-5.5", default: true, capabilities: ["reasoning", "tool_calling", "structured_output"] },
      { id: "gpt-5.4-mini", label: "gpt-5.4-mini", default: false, capabilities: ["fast_reasoning", "tool_calling", "structured_output"] }
    ]
  },
  {
    id: "anthropic",
    label: "Anthropic",
    enabled: false,
    configured: false,
    default_model: "claude-opus-4.8",
    capabilities: ["planning", "graph_query", "research", "tool_calling"],
    models: [
      { id: "claude-opus-4.8", label: "claude-opus-4.8", default: true, capabilities: ["reasoning", "tool_calling", "long_context"] },
      { id: "claude-sonnet-4.6", label: "claude-sonnet-4.6", default: false, capabilities: ["fast_reasoning", "tool_calling", "long_context"] }
    ]
  },
  {
    id: "gemini",
    label: "Gemini",
    enabled: false,
    configured: false,
    default_model: "gemini-3.1-pro",
    capabilities: ["planning", "graph_query", "research", "structured_output", "search_grounding", "url_context"],
    models: [
      { id: "gemini-3.1-pro", label: "gemini-3.1-pro", default: true, capabilities: ["reasoning", "function_calling", "search_grounding", "url_context"] },
      { id: "gemini-3.5-flash", label: "gemini-3.5-flash", default: false, capabilities: ["fast_reasoning", "function_calling", "search_grounding", "url_context"] }
    ]
  }
];

export const providerCredentialCopy: Record<ApiProviderId, { secretLabel: string; placeholder: string; source: string; detail: string }> = {
  "graphview-local": {
    secretLabel: "No external key",
    placeholder: "",
    source: "Built in",
    detail: "Deterministic local provider for planning, graph query, and research fallback."
  },
  openai: {
    secretLabel: "OpenAI API key",
    placeholder: "sk-...",
    source: "OPENAI_API_KEY",
    detail: "Used for OpenAI planning, graph query, structured output, and research runs."
  },
  anthropic: {
    secretLabel: "Anthropic API key",
    placeholder: "sk-ant-...",
    source: "ANTHROPIC_API_KEY",
    detail: "Used for Anthropic planning, graph query, long-context reasoning, and research runs."
  },
  gemini: {
    secretLabel: "Gemini API key",
    placeholder: "AIza...",
    source: "GEMINI_API_KEY",
    detail: "Used for Gemini planning, graph query, grounded research, and URL-context runs."
  }
};

export function withFallbackProviders(providers: ApiProviderDescriptor[] | undefined): ApiProviderDescriptor[] {
  if (!providers?.length) {
    return fallbackProviders;
  }
  const serverProviders = new Map(providers.map((provider) => [provider.id, provider]));
  const normalized = fallbackProviders.map((fallbackProvider) => ({
    ...fallbackProvider,
    ...(serverProviders.get(fallbackProvider.id) ?? {})
  }));
  const fallbackIds = new Set(fallbackProviders.map((provider) => provider.id));
  return [...normalized, ...providers.filter((provider) => !fallbackIds.has(provider.id))];
}

export interface ApiAgentCitation {
  id: string;
  label: string;
  source_id?: string | null;
  source_title?: string | null;
  source_chunk_id?: string | null;
  node_id?: string | null;
  proposal_id?: string | null;
  locator?: string | null;
  quote?: string | null;
  url?: string | null;
  confidence?: number | null;
}

export interface ApiAgentActionProposal {
  id: string;
  agent_run_id: string;
  action_type: string;
  status: "pending_review" | "approved" | "rejected" | "applied" | "failed";
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  citations: ApiAgentCitation[];
  confidence?: number | null;
}

export interface ApiAgentToolCall {
  id: string;
  kind: AgentToolKind;
  input: Record<string, unknown>;
  status: "pending_review" | "running" | "succeeded" | "failed" | "blocked";
  citations: ApiAgentCitation[];
  affected_graph_ids: string[];
  resulting_proposal_id?: string | null;
  summary?: string | null;
}

export interface ApiGeneratedArtifact {
  id: string;
  kind: "plan" | "source" | "subgraph" | "proposal_diff" | "evidence_bundle";
  title: string;
  payload: Record<string, unknown>;
  citations: ApiAgentCitation[];
}

export interface ApiAgentRun {
  id: string;
  kind: "planning" | "graph_query" | "research" | "action_apply";
  mode?: "graph" | "planning";
  status: "queued" | "running" | "waiting_for_review" | "completed" | "failed" | "cancelled";
  provider: string;
  model: string;
  output: Record<string, unknown>;
  trace_id: string;
  tool_calls?: ApiAgentToolCall[];
  generated_artifacts?: ApiGeneratedArtifact[];
  action_proposals: ApiAgentActionProposal[];
}

export interface ApiAgentContextSession {
  id: string;
  project_id: string;
  client_id: string;
  runtime_kind: "codex" | "claude-code" | "cursor" | "vscode" | "mcp" | "openai-compatible" | "generic";
  authority: CaptureAuthority;
  status: "running" | "completed" | "failed" | "cancelled";
  title: string;
  workspace_root?: string | null;
  repository_uri?: string | null;
  branch?: string | null;
  commit_sha?: string | null;
  metadata: Record<string, unknown>;
  started_at: string;
  ended_at?: string | null;
  updated_at: string;
}

export interface ApiAgentContextArtifact {
  id: string;
  session_id: string;
  kind: string;
  uri?: string | null;
  path?: string | null;
  title: string;
  content_type: string;
  checksum?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ApiAgentContextEvent {
  id: string;
  session_id: string;
  client_event_id: string;
  sequence: number;
  event_kind: string;
  authority: CaptureAuthority;
  status: "accepted" | "duplicate" | "rejected";
  summary: string;
  checksum: string;
  artifact_id?: string | null;
  blob_id?: string | null;
  payload: Record<string, unknown>;
  object_refs: Array<{ kind: string; id: string; label?: string | null }>;
  occurred_at: string;
  received_at: string;
}

export interface ApiAgentContextGraph {
  session: ApiAgentContextSession;
  nodes: Array<{ id: string; kind: string; label: string; authority?: CaptureAuthority | null; metadata: Record<string, unknown> }>;
  edges: Array<{ id: string; source_id: string; target_id: string; relation: string; observed: boolean; metadata: Record<string, unknown> }>;
  artifacts: ApiAgentContextArtifact[];
  events: ApiAgentContextEvent[];
}

export interface ApiAgentContextBlob {
  id: string;
  session_id: string;
  artifact_id?: string | null;
  content_kind: "text" | "binary" | "metadata_only";
  media_type?: string | null;
  redaction_status: "not_required" | "redacted" | "metadata_only";
  encryption_status: "encrypted" | "metadata_only";
  checksum?: string | null;
  byte_count?: number | null;
  token_count?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  expires_at?: string | null;
}

export interface ApiAgentContextBlobContent {
  blob: ApiAgentContextBlob;
  text?: string | null;
}

export interface ApiGraphBuildSpec {
  id: string;
  title: string;
  objective: string;
  status: string;
  spec: {
    topics?: Array<{ name?: string; priority?: string }>;
    open_questions?: string[];
    research_tasks?: Array<{ query?: string; source_policy?: string; priority?: string }>;
    node_kinds?: string[];
    edge_relations?: string[];
  } & Record<string, unknown>;
}

export interface ApiPlanningMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  provider?: string | null;
  model?: string | null;
  metadata: Record<string, unknown>;
}

export interface ApiPlanningSession {
  id: string;
  title: string;
  goal: string;
  status: string;
  lens: GraphLensId;
  provider?: string | null;
  model?: string | null;
  messages: ApiPlanningMessage[];
  build_spec?: ApiGraphBuildSpec | null;
}

export interface ApiGraphQueryAnswer {
  answer: string;
  confidence: number;
  citations: ApiAgentCitation[];
  agent_run: ApiAgentRun;
}

export interface ApiGraphResearchResult {
  research_task: {
    id: string;
    status: string;
    query: string;
    result: Record<string, unknown>;
  };
  agent_run: ApiAgentRun;
  source?: ApiSource | null;
  proposals: ApiProposal[];
}

export interface ApiGraphActivityEvent {
  id: string;
  project_id: string;
  graph_id?: string | null;
  event_type?: string;
  kind?: GraphActivityEvent["kind"];
  status?: GraphActivityEvent["status"];
  subject?: { kind: string; id: string; label?: string | null };
  object_refs?: Array<{ kind: string; id: string; label?: string | null }>;
  actor_id?: string | null;
  agent_run_id?: string | null;
  agent_tool_call_id?: string | null;
  source_ids?: string[];
  source_chunk_ids?: string[];
  node_ids?: string[];
  edge_ids?: string[];
  proposal_ids?: string[];
  review_decision_ids?: string[];
  citations?: ApiAgentCitation[];
  summary: string;
  metadata?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  lenses?: string[];
  occurred_at?: string;
  created_at?: string;
}

export interface ApiGraphActivityResponse {
  generated_at?: string;
  returned_count?: number;
  events?: ApiGraphActivityEvent[];
  graph_activity_events?: ApiGraphActivityEvent[];
}

export interface ApiGraphObjectRef {
  kind: string;
  id: string;
  label?: string | null;
}

export interface ApiSignal {
  id: string;
  kind: string;
  status: string;
  severity: string;
  source_kind: string;
  source_id?: string | null;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  received_at: string;
}

export interface ApiOwner {
  id: string;
  owner_type: string;
  display_name: string;
  contact?: string | null;
  escalation_contact?: string | null;
  scope_kind: string;
  scope_id?: string | null;
}

export type ApiActionCredentialKind = "github" | "smtp" | "webhook";

export interface ApiRoutingPolicy {
  id: string;
  name: string;
  enabled: boolean;
  severity: string;
  owner_id?: string | null;
  sla_seconds?: number | null;
  suggested_actions: string[];
}

export interface ApiOperationalAttentionItem {
  id: string;
  kind: string;
  status: string;
  severity: string;
  sla_status: string;
  title: string;
  summary: string;
  owner_id?: string | null;
  assignee_id?: string | null;
  due_at?: string | null;
  source_id?: string | null;
  signal_id?: string | null;
  observation_id?: string | null;
  alert_id?: string | null;
  proposal_id?: string | null;
  decision_record_id?: string | null;
  action_proposal_id?: string | null;
  action_run_id?: string | null;
  outcome_id?: string | null;
  feedback_event_id?: string | null;
  object_refs: ApiGraphObjectRef[];
  suggested_actions: string[];
  blockers: string[];
  updated_at: string;
}

export interface ApiOperationalAttentionResponse {
  generated_at: string;
  returned_count: number;
  items: ApiOperationalAttentionItem[];
}

export interface ApiDecisionRecord {
  id: string;
  attention_item_id?: string | null;
  decision: string;
  rationale: string;
  created_at: string;
}

export interface ApiOperationalActionProposal {
  id: string;
  decision_record_id?: string | null;
  alert_id?: string | null;
  attention_item_id?: string | null;
  action_type: string;
  status: string;
  title: string;
  summary: string;
  redacted_payload: Record<string, unknown>;
  approval_required: boolean;
  updated_at: string;
}

export interface ApiOperationalActionRun {
  id: string;
  action_proposal_id: string;
  action_type: string;
  status: string;
  target?: string | null;
  redacted_payload: Record<string, unknown>;
  external_id?: string | null;
  started_at: string;
}

export interface ApiOperationalOutcome {
  id: string;
  action_run_id?: string | null;
  attention_item_id?: string | null;
  status: string;
  title: string;
  summary: string;
  occurred_at: string;
}

export interface ApiFeedbackEvent {
  id: string;
  outcome_id?: string | null;
  action_run_id?: string | null;
  attention_item_id?: string | null;
  kind: string;
  summary: string;
  created_at: string;
}

export type ContentExpansionRole = "source" | "chunk" | "proposal" | "decision" | "task";
