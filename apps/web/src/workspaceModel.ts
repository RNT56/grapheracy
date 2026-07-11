import {
  normalizeContentNodeKind,
  type AgentCitation,
  type AgentRun as SharedAgentRun,
  type AgentToolCall as SharedAgentToolCall,
  type ContentNode,
  type ContentNodeId,
  type ExtractionLensDescriptor,
  type ExtractionProposal,
  type GraphActivityEvent,
  type GraphLensDescriptor,
  type GraphProject,
  type GraphProjectId,
  type ReviewDecision,
  type SemanticEdge,
  type Source
} from "@graphview/shared-types";
import type {
  ApiAgentCitation,
  ApiAgentRun,
  ApiAgentToolCall,
  ApiExtractionLens,
  ApiGraph,
  ApiGraphActivityEvent,
  ApiGraphActivityResponse,
  ApiGraphLens,
  ApiGraphView,
  ApiProposal,
  ApiReviewActivity,
  ApiSource
} from "./workspaceTypes";

const GENERAL_GRAPH_VIEW_ID = "project-default";

export function normalizeSourceKind(value: string | null | undefined): Source["kind"] {
  if (
    value === "text" ||
    value === "markdown" ||
    value === "url" ||
    value === "pdf" ||
    value === "repository" ||
    value === "ops-document"
  ) {
    return value;
  }
  return "text";
}

export function ensureGeneralGraphView(views: ApiGraphView[], fallbackView?: ApiGraphView): ApiGraphView[] {
  const generalView: ApiGraphView = {
    id: GENERAL_GRAPH_VIEW_ID,
    project_id: GENERAL_GRAPH_VIEW_ID,
    label: "General Knowledge Graph",
    description: "All reviewed sources, scopes, planning sessions, and graph data unified into one knowledge graph.",
    kind: "project",
    source_ids: [],
    node_count: 0,
    edge_count: 0,
    source_count: 0,
    pending_proposal_count: 0
  };
  const seedViews = fallbackView && views.length === 0 ? [fallbackView] : views;
  const normalized = seedViews.map((view) =>
    view.id === GENERAL_GRAPH_VIEW_ID
      ? {
          ...view,
          label: "General Knowledge Graph",
          description: generalView.description
        }
      : view
  );
  return normalized.some((view) => view.id === GENERAL_GRAPH_VIEW_ID)
    ? normalized
    : [generalView, ...normalized];
}

export function normalizeGraph(data: ApiGraph): { project: GraphProject; nodes: ContentNode[]; edges: SemanticEdge[] } {
  return {
    project: {
      id: data.project.id as GraphProjectId,
      name: data.project.name,
      description: data.project.description ?? undefined,
      createdAt: data.project.created_at,
      updatedAt: data.project.updated_at
    },
    nodes: data.nodes.map((node) => ({
      id: node.id as ContentNode["id"],
      projectId: node.project_id as GraphProjectId,
      topicIds: node.topic_ids as ContentNode["topicIds"],
      label: node.label,
      kind: normalizeContentNodeKind(node.kind),
      summary: node.summary ?? undefined,
      metadata: node.metadata ?? {},
      provenance: node.provenance,
      createdAt: node.created_at,
      updatedAt: node.updated_at
    })),
    edges: data.edges.map((edge) => ({
      id: edge.id as SemanticEdge["id"],
      projectId: edge.project_id as GraphProjectId,
      sourceNodeId: edge.source_node_id as ContentNodeId,
      targetNodeId: edge.target_node_id as ContentNodeId,
      relation: edge.relation as SemanticEdge["relation"],
      weight: edge.weight ?? undefined,
      metadata: edge.metadata ?? {},
      provenance: edge.provenance,
      createdAt: edge.created_at,
      updatedAt: edge.updated_at
    }))
  };
}

export function apiGraphActivityEvents(response?: ApiGraphActivityResponse): ApiGraphActivityEvent[] {
  return response?.events ?? response?.graph_activity_events ?? [];
}

export function apiGraphActivityEventToShared(event: ApiGraphActivityEvent): GraphActivityEvent {
  const payload = event.metadata ?? event.payload ?? {};
  const refs = event.object_refs ?? [];
  const subject = event.subject ?? refs[0] ?? { kind: "graph", id: event.graph_id ?? "project-default", label: "Graph activity" };
  const eventType = event.event_type ?? event.kind ?? "graph.activity";
  const sourceIds = event.source_ids ?? graphActivityIds(refs, "source", payload, "source_id");
  const sourceChunkIds = event.source_chunk_ids ?? graphActivityIds(refs, "chunk", payload, "source_chunk_id");
  const nodeIds = event.node_ids ?? graphActivityIds(refs, "node", payload, "node_id");
  const edgeIds = event.edge_ids ?? graphActivityIds(refs, "edge", payload, "edge_id");
  const proposalIds = event.proposal_ids ?? graphActivityIds(refs, "proposal", payload, "proposal_id");
  const reviewDecisionIds = event.review_decision_ids ?? graphActivityIds(refs, "review", payload, "review_decision_id");
  const agentRunId = event.agent_run_id ?? graphActivityId(refs, "agent_run", payload, "agent_run_id");
  const agentToolCallId = event.agent_tool_call_id ?? stringFromUnknown(payload.agent_tool_call_id);

  return {
    id: event.id as GraphActivityEvent["id"],
    projectId: event.project_id as GraphProjectId,
    graphId: event.graph_id ?? undefined,
    kind: event.kind ?? graphActivityKind(eventType, payload),
    status: event.status ?? graphActivityStatus(eventType, payload),
    subject: {
      kind: graphActivityObjectKind(subject.kind),
      id: subject.id,
      label: subject.label ?? undefined
    },
    actorId: event.actor_id ?? undefined,
    agentRunId: agentRunId as GraphActivityEvent["agentRunId"],
    agentToolCallId,
    sourceIds: sourceIds as GraphActivityEvent["sourceIds"],
    sourceChunkIds: sourceChunkIds as GraphActivityEvent["sourceChunkIds"],
    nodeIds: nodeIds as GraphActivityEvent["nodeIds"],
    edgeIds: edgeIds as GraphActivityEvent["edgeIds"],
    proposalIds: proposalIds as GraphActivityEvent["proposalIds"],
    reviewDecisionIds: reviewDecisionIds as GraphActivityEvent["reviewDecisionIds"],
    citations: (event.citations ?? []).map(apiCitationToShared),
    summary: event.summary,
    metadata: {
      ...payload,
      eventType,
      lenses: event.lenses ?? []
    },
    occurredAt: event.occurred_at ?? event.created_at ?? new Date().toISOString()
  };
}

export function graphActivityObjectKind(kind: string): GraphActivityEvent["subject"]["kind"] {
  if (
    kind === "graph" ||
    kind === "node" ||
    kind === "edge" ||
    kind === "source" ||
    kind === "chunk" ||
    kind === "proposal" ||
    kind === "review" ||
    kind === "agent_run" ||
    kind === "tool_call" ||
    kind === "signal" ||
    kind === "observation" ||
    kind === "alert" ||
    kind === "attention" ||
    kind === "owner" ||
    kind === "policy" ||
    kind === "decision" ||
    kind === "action_proposal" ||
    kind === "action_run" ||
    kind === "outcome" ||
    kind === "feedback"
  ) {
    return kind;
  }
  if (kind === "source_chunk") return "chunk";
  if (kind === "review_decision") return "review";
  if (kind === "agent_tool_call") return "tool_call";
  return "graph";
}

export function graphActivityKind(eventType: string, payload: Record<string, unknown>): GraphActivityEvent["kind"] {
  if (eventType.includes("signal.")) return "signal_sensed";
  if (eventType.includes("observation.")) return "observation_recorded";
  if (eventType.includes("alert.routed")) return "alert_routed";
  if (eventType.includes("alert.assigned") || eventType.includes("attention.assigned") || eventType.includes("attention.opened")) {
    return "attention_assigned";
  }
  if (eventType.includes("attention.transitioned")) {
    return stringFromUnknown(payload.status) === "reopened" ? "attention_reopened" : "attention_assigned";
  }
  if (eventType.includes("decision.")) return "decision_recorded";
  if (eventType.includes("action.proposed")) return "action_proposed";
  if (eventType.includes("action.approved")) return "action_approved";
  if (eventType.includes("action.rejected")) return "review_rejected";
  if (eventType.includes("action.run.failed")) return "outcome_failed";
  if (eventType.includes("action.run.succeeded")) return "outcome_succeeded";
  if (eventType.includes("action.run")) return "action_running";
  if (eventType.includes("outcome.waiting")) return "outcome_waiting";
  if (eventType.includes("outcome.succeeded") || eventType.includes("outcome.resolved")) return "outcome_succeeded";
  if (eventType.includes("outcome.failed") || eventType.includes("outcome.unresolved")) return "outcome_failed";
  if (eventType.includes("outcome.reopened")) return "attention_reopened";
  if (eventType.includes("feedback.")) return "feedback_applied";
  if (eventType.includes("action_rejected")) return "review_rejected";
  if (eventType.includes("action_applied")) return "review_accepted";
  if (eventType.includes("reviewed")) {
    const decision = stringFromUnknown(payload.decision);
    if (decision === "reject") return "review_rejected";
    if (decision === "edit") return "review_edited";
    if (decision === "defer") return "review_deferred";
    return "review_accepted";
  }
  if (eventType.includes("proposal_ready") || eventType.includes("proposal.created") || eventType.includes("action_proposed")) {
    return "proposal_candidate";
  }
  if (eventType.includes("node_committed") || eventType.includes("edge_committed")) return "review_accepted";
  if (eventType.includes("agent.run")) return "agent_scan";
  if (eventType.includes("research")) return "research_started";
  if (eventType.includes("source") || eventType.includes("sync") || eventType.includes("ingestion")) return "source_incoming";
  return "agent_scan";
}

export function graphActivityStatus(eventType: string, payload: Record<string, unknown>): GraphActivityEvent["status"] {
  const status = stringFromUnknown(payload.status);
  if (status === "failed" || eventType.includes("failed")) return "failed";
  if (status === "resolved" || eventType.includes("resolved")) return "succeeded";
  if (status === "reopened" || eventType.includes("reopened")) return "blocked";
  if (status === "cancelled" || eventType.includes("cancelled")) return "cancelled";
  if (status === "blocked") return "blocked";
  if (status === "pending_review" || status === "proposed") return "ready";
  if (status === "waiting_for_review" || eventType.includes("waiting_for_review")) return "ready";
  if (status === "running" || eventType.includes("running")) return "running";
  if (eventType.includes("proposal_ready") || eventType.includes("action_proposed")) return "ready";
  return "succeeded";
}

export function graphActivityIds(
  refs: Array<{ kind: string; id: string }>,
  kind: GraphActivityEvent["subject"]["kind"],
  payload: Record<string, unknown>,
  payloadKey: string
): string[] {
  const refIds = refs.filter((ref) => graphActivityObjectKind(ref.kind) === kind).map((ref) => ref.id);
  const payloadIds = stringsFromUnknown(payload[payloadKey]);
  return [...new Set([...refIds, ...payloadIds])];
}

export function graphActivityId(
  refs: Array<{ kind: string; id: string }>,
  kind: GraphActivityEvent["subject"]["kind"],
  payload: Record<string, unknown>,
  payloadKey: string
): string | undefined {
  return graphActivityIds(refs, kind, payload, payloadKey)[0];
}

export function stringsFromUnknown(value: unknown): string[] {
  if (typeof value === "string" && value) return [value];
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string" && item.length > 0);
  return [];
}

export function stringFromUnknown(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

export function apiSourceToShared(source: ApiSource | Source): Source {
  if ("projectId" in source) return source;
  return {
    id: source.id as Source["id"],
    projectId: "project-default" as GraphProjectId,
    kind: normalizeSourceKind(source.kind),
    title: source.title,
    uri: source.uri ?? undefined,
    connectorKind: source.connector_kind ?? undefined,
    remoteId: source.remote_id ?? undefined,
    remoteParentId: source.remote_parent_id ?? undefined,
    remoteUrl: source.remote_url ?? undefined,
    metadata: source.metadata ?? {},
    staleAt: source.stale_at ?? undefined,
    createdAt: "",
    updatedAt: source.stale_at ?? ""
  };
}

export function apiProposalToShared(proposal: ApiProposal): ExtractionProposal {
  return {
    id: proposal.id as ExtractionProposal["id"],
    projectId: "project-default" as GraphProjectId,
    ingestionRunId: "" as ExtractionProposal["ingestionRunId"],
    kind: proposal.kind,
    status: proposal.status as ExtractionProposal["status"],
    proposedValue: proposal.proposed_value,
    confidence: typeof proposal.proposed_value.weight === "number" ? proposal.proposed_value.weight : undefined,
    provenance: [],
    createdAt: ""
  };
}

export function apiReviewDecisionToShared(decision: ApiReviewActivity["items"][number]["decision"]): ReviewDecision {
  return {
    id: decision.id as ReviewDecision["id"],
    projectId: "project-default" as GraphProjectId,
    proposalId: "" as ReviewDecision["proposalId"],
    reviewerId: decision.reviewer_id,
    decision: decision.decision,
    decidedAt: decision.decided_at
  };
}

export function apiAgentRunToShared(run: ApiAgentRun): SharedAgentRun {
  return {
    id: run.id as SharedAgentRun["id"],
    projectId: "project-default" as GraphProjectId,
    kind: run.kind,
    mode: run.mode ?? "graph",
    status: run.status,
    provider: run.provider,
    model: run.model,
    input: {},
    output: run.output,
    traceId: run.trace_id,
    createdBy: "agent",
    startedAt: "",
    finishedAt: undefined,
    steps: [],
    toolCalls: run.tool_calls?.map(apiAgentToolCallToShared),
    generatedArtifacts: [],
    actionProposals: [],
    planningSessionId: undefined
  };
}

export function apiAgentToolCallToShared(toolCall: ApiAgentToolCall): SharedAgentToolCall {
  return {
    id: toolCall.id,
    kind: toolCall.kind,
    input: toolCall.input,
    status: toolCall.status,
    citations: toolCall.citations.map(apiCitationToShared),
    affectedGraphIds: toolCall.affected_graph_ids,
    resultingProposalId: toolCall.resulting_proposal_id as SharedAgentToolCall["resultingProposalId"],
    summary: toolCall.summary ?? undefined
  };
}

export function apiCitationToShared(citation: ApiAgentCitation): AgentCitation {
  return {
    id: citation.id,
    label: citation.label,
    sourceId: citation.source_id as AgentCitation["sourceId"],
    sourceTitle: citation.source_title ?? undefined,
    sourceChunkId: citation.source_chunk_id as AgentCitation["sourceChunkId"],
    nodeId: citation.node_id as AgentCitation["nodeId"],
    proposalId: citation.proposal_id as AgentCitation["proposalId"],
    locator: citation.locator ?? undefined,
    quote: citation.quote ?? undefined,
    url: citation.url ?? undefined,
    confidence: citation.confidence ?? undefined
  };
}

export function normalizeExtractionLens(data: ApiExtractionLens): ExtractionLensDescriptor {
  return {
    id: data.id,
    label: data.label,
    summary: data.summary,
    defaultProposalLimit: data.default_proposal_limit,
    sourceKinds: data.source_kinds,
    primaryNodeKinds: data.primary_node_kinds.map(normalizeContentNodeKind),
    provenanceFields: data.provenance_fields
  };
}

export function normalizeGraphLens(data: ApiGraphLens): GraphLensDescriptor {
  return {
    id: data.id,
    label: data.label,
    summary: data.summary,
    activeByDefault: data.active_by_default
  };
}
