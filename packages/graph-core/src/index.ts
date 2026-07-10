import type {
  AgentCitation,
  AgentRun,
  AgentToolCall,
  ContentNode,
  ExtractionProposal,
  GraphActivityEvent,
  GraphActivityEventKind,
  GraphActivityEventStatus,
  GraphDelta,
  GraphLensId,
  GraphObjectRef,
  GraphProjectId,
  GraphTooltipModel,
  GraphVisualState,
  GraphVisualStatus,
  ReviewDecision,
  ReviewQueueItem,
  SemanticEdge,
  Source
} from "@graphview/shared-types";

export interface GraphViewport {
  width: number;
  height: number;
  zoom: number;
  offsetX: number;
  offsetY: number;
}

export interface RenderableGraph {
  nodes: ContentNode[];
  edges: SemanticEdge[];
}

export interface GraphLensPlan {
  lens: GraphLensId;
  nodes: ContentNode[];
  edges: SemanticEdge[];
  omittedNodeCount: number;
  omittedEdgeCount: number;
}

export interface GraphRenderLimits {
  maxNodes: number;
  maxEdges: number;
  labelMaxLength: number;
}

export interface RenderPlanNode {
  node: ContentNode;
  x: number;
  y: number;
  degree: number;
  label: string;
  truncated: boolean;
}

export interface RenderPlanEdge {
  edge: SemanticEdge;
  source: RenderPlanNode;
  target: RenderPlanNode;
}

export interface GraphRenderPlan {
  nodes: RenderPlanNode[];
  edges: RenderPlanEdge[];
  omittedNodeCount: number;
  omittedEdgeCount: number;
  orphanEdgeCount: number;
  truncatedLabelCount: number;
}

export interface GraphSummaryCount {
  name: string;
  count: number;
}

export interface GraphSummaryTopNode {
  node: ContentNode;
  degree: number;
}

export interface GraphSummary {
  nodeCount: number;
  edgeCount: number;
  connectedEdgeCount: number;
  orphanEdgeCount: number;
  nodeKindCounts: GraphSummaryCount[];
  relationCounts: GraphSummaryCount[];
  topNodes: GraphSummaryTopNode[];
}

export interface GraphNeighborhoodOptions {
  depth: number;
  maxNodes: number;
  maxEdges: number;
}

export interface GraphNeighborhood {
  centerNode: ContentNode;
  depth: number;
  nodes: ContentNode[];
  edges: SemanticEdge[];
  omittedNodeCount: number;
  omittedEdgeCount: number;
}

export interface GraphPathOptions {
  maxDepth: number;
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

export interface GraphRendererAdapter {
  readonly kind: "sigma-2d" | "three-3d" | "accessible";
  mount(container: HTMLElement): void;
  unmount(): void;
  setData(data: RenderableGraph): void;
  focusNode(nodeId: string): void;
  fitGraph(options?: { animated?: boolean }): void;
  hitTest(point: { x: number; y: number }): GraphObjectRef | undefined;
  applyDelta(delta: GraphDelta): void;
  setVisualStates(states: GraphVisualState[]): void;
  getCameraState(): { x: number; y: number; ratio: number; angle?: number };
  setCameraState(state: { x: number; y: number; ratio: number; angle?: number }): void;
  exportImage(options?: { pixelRatio?: number; background?: string }): Promise<Blob>;
  recoverContext(): void | Promise<void>;
  metrics(): GraphRendererMetrics;
}

export interface GraphRendererMetrics {
  visibleNodes: number;
  visibleEdges: number;
  framesPerSecond?: number;
  renderDurationMs?: number;
  contextLost: boolean;
}

export type GraphMotionTier = "full_motion" | "reduced_motion" | "static_state" | "sampled_graph";

export interface GraphAnimationBudget {
  tier: GraphMotionTier;
  maxAnimatedNodes: number;
  maxAnimatedEdges: number;
  enableScanWaves: boolean;
  enableFlowAnimation: boolean;
  reason: string;
}

export interface GraphAnimationBudgetOptions {
  reducedMotion?: boolean;
  forceStatic?: boolean;
}

export interface GraphVisualStateOptions {
  hoveredObjectId?: string;
  focusedObjectId?: string;
  selectedNodeId?: string;
  queryMatchedIds?: string[];
  scanningIds?: string[];
  citedIds?: string[];
  incomingIds?: string[];
  candidateIds?: string[];
  readyIds?: string[];
  blockedIds?: string[];
  acceptedIds?: string[];
  rejectedIds?: string[];
  editedIds?: string[];
  deferredIds?: string[];
  staleIds?: string[];
  sensedIds?: string[];
  routedIds?: string[];
  assignedIds?: string[];
  slaAtRiskIds?: string[];
  actionProposedIds?: string[];
  actionRunningIds?: string[];
  outcomeWaitingIds?: string[];
  outcomeSucceededIds?: string[];
  outcomeFailedIds?: string[];
  feedbackAppliedIds?: string[];
  reopenedIds?: string[];
  now?: string;
}

export interface GraphActivityDerivationInput {
  projectId: GraphProjectId;
  graphId?: string;
  sources?: Source[];
  proposals?: ExtractionProposal[];
  reviewQueueItems?: ReviewQueueItem[];
  reviewDecisions?: ReviewDecision[];
  agentRuns?: AgentRun[];
  toolCalls?: AgentToolCall[];
  citations?: AgentCitation[];
  occurredAt?: string;
}

export interface GraphOverlayAnchor {
  object: GraphObjectRef;
  x: number;
  y: number;
  z?: number;
}

export interface GraphTetherPlan {
  from: GraphOverlayAnchor;
  to: GraphOverlayAnchor;
  path: string;
  status: GraphVisualStatus;
}

export const DEFAULT_GRAPH_RENDER_LIMITS: GraphRenderLimits = {
  maxNodes: 120,
  maxEdges: 240,
  labelMaxLength: 28
};

export const DEFAULT_GRAPH_NEIGHBORHOOD_OPTIONS: GraphNeighborhoodOptions = {
  depth: 1,
  maxNodes: 25,
  maxEdges: 50
};

export const DEFAULT_GRAPH_PATH_OPTIONS: GraphPathOptions = {
  maxDepth: 4
};

export const DEFAULT_GRAPH_ANIMATION_BUDGET: GraphAnimationBudget = {
  tier: "full_motion",
  maxAnimatedNodes: 80,
  maxAnimatedEdges: 140,
  enableScanWaves: true,
  enableFlowAnimation: true,
  reason: "Graph is within full-motion budget."
};

const VISUAL_STATUS_PRIORITY: GraphVisualStatus[] = [
  "blocked",
  "rejected",
  "accepted",
  "edited",
  "deferred",
  "outcome_failed",
  "sla_at_risk",
  "reopened",
  "action_running",
  "action_proposed",
  "outcome_waiting",
  "outcome_succeeded",
  "feedback_applied",
  "routed",
  "assigned",
  "sensed",
  "ready",
  "candidate",
  "incoming",
  "scanning",
  "cited",
  "focus",
  "hover",
  "related",
  "stale",
  "dimmed"
];

const ENGINEERING_NODE_KINDS = new Set([
  "system",
  "component",
  "service",
  "api",
  "repository",
  "module",
  "package",
  "file",
  "symbol"
]);
const OPS_NODE_KINDS = new Set([
  "workflow",
  "policy",
  "process",
  "vendor",
  "decision",
  "requirement",
  "risk",
  "event",
  "incident",
  "project",
  "owner",
  "review_cycle",
  "task",
  "team",
  "organization"
]);
const RESEARCH_NODE_KINDS = new Set(["concept", "topic", "term", "document", "source", "dataset"]);
const ENGINEERING_RELATIONS = new Set(["depends_on", "defines", "imports", "implements", "contains", "references"]);
const OPS_RELATIONS = new Set(["owned_by", "has_review_cycle", "governs", "supports", "depends_on"]);
const RESEARCH_RELATIONS = new Set(["supports", "contradicts", "causes", "mentions", "defines", "relates_to", "references"]);

export function selectGraphAnimationBudget(
  data: RenderableGraph,
  options: GraphAnimationBudgetOptions = {}
): GraphAnimationBudget {
  if (options.forceStatic) {
    return {
      tier: "static_state",
      maxAnimatedNodes: 0,
      maxAnimatedEdges: 0,
      enableScanWaves: false,
      enableFlowAnimation: false,
      reason: "Static rendering was requested."
    };
  }
  if (options.reducedMotion) {
    return {
      tier: "reduced_motion",
      maxAnimatedNodes: 24,
      maxAnimatedEdges: 36,
      enableScanWaves: false,
      enableFlowAnimation: false,
      reason: "Reduced-motion preference disables continuous graph animation."
    };
  }
  if (data.nodes.length > DEFAULT_GRAPH_RENDER_LIMITS.maxNodes || data.edges.length > DEFAULT_GRAPH_RENDER_LIMITS.maxEdges) {
    return {
      tier: "sampled_graph",
      maxAnimatedNodes: 32,
      maxAnimatedEdges: 48,
      enableScanWaves: false,
      enableFlowAnimation: false,
      reason: "Large graph uses sampled static activity to stay readable."
    };
  }
  if (data.nodes.length > 80 || data.edges.length > 140) {
    return {
      tier: "reduced_motion",
      maxAnimatedNodes: 40,
      maxAnimatedEdges: 64,
      enableScanWaves: false,
      enableFlowAnimation: true,
      reason: "Medium graph limits scan animation to preserve frame budget."
    };
  }
  return DEFAULT_GRAPH_ANIMATION_BUDGET;
}

export function resolveGraphVisualStates(data: RenderableGraph, options: GraphVisualStateOptions = {}): GraphVisualState[] {
  const nodeIds = new Set(data.nodes.map((node) => node.id));
  const edgeIds = new Set(data.edges.map((edge) => edge.id));
  const statusSets = {
    matched: new Set(options.queryMatchedIds ?? []),
    scanning: new Set(options.scanningIds ?? []),
    cited: new Set(options.citedIds ?? []),
    incoming: new Set(options.incomingIds ?? []),
    candidate: new Set(options.candidateIds ?? []),
    ready: new Set(options.readyIds ?? []),
    blocked: new Set(options.blockedIds ?? []),
    accepted: new Set(options.acceptedIds ?? []),
    rejected: new Set(options.rejectedIds ?? []),
    edited: new Set(options.editedIds ?? []),
    deferred: new Set(options.deferredIds ?? []),
    stale: new Set(options.staleIds ?? []),
    sensed: new Set(options.sensedIds ?? []),
    routed: new Set(options.routedIds ?? []),
    assigned: new Set(options.assignedIds ?? []),
    sla_at_risk: new Set(options.slaAtRiskIds ?? []),
    action_proposed: new Set(options.actionProposedIds ?? []),
    action_running: new Set(options.actionRunningIds ?? []),
    outcome_waiting: new Set(options.outcomeWaitingIds ?? []),
    outcome_succeeded: new Set(options.outcomeSucceededIds ?? []),
    outcome_failed: new Set(options.outcomeFailedIds ?? []),
    feedback_applied: new Set(options.feedbackAppliedIds ?? []),
    reopened: new Set(options.reopenedIds ?? [])
  };
  const relatedIds = new Set<string>();
  const focusId = options.focusedObjectId ?? options.selectedNodeId;
  if (focusId && nodeIds.has(focusId as ContentNode["id"])) {
    relatedIds.add(focusId);
    for (const edge of data.edges) {
      if (edge.sourceNodeId === focusId) relatedIds.add(edge.targetNodeId);
      if (edge.targetNodeId === focusId) relatedIds.add(edge.sourceNodeId);
    }
  }
  const hasFocus = Boolean(focusId || options.hoveredObjectId || statusSets.matched.size > 0);
  const states: GraphVisualState[] = [];

  for (const node of data.nodes) {
    states.push(
      graphVisualState({
        object: { kind: "node", id: node.id, label: node.label },
        statuses: statusesForObject(node.id, {
          hovered: node.id === options.hoveredObjectId,
          focused: node.id === focusId,
          related: relatedIds.has(node.id),
          dimmed: hasFocus && !relatedIds.has(node.id) && !statusSets.matched.has(node.id) && node.id !== options.hoveredObjectId,
          statusSets
        }),
        now: options.now
      })
    );
  }

  for (const edge of data.edges) {
    const edgeRelated = relatedIds.has(edge.sourceNodeId) && relatedIds.has(edge.targetNodeId);
    states.push(
      graphVisualState({
        object: { kind: "edge", id: edge.id, label: edge.relation },
        statuses: statusesForObject(edge.id, {
          hovered: edge.id === options.hoveredObjectId,
          focused: edge.id === focusId,
          related: edgeRelated,
          dimmed: hasFocus && !edgeRelated && !statusSets.matched.has(edge.id) && edge.id !== options.hoveredObjectId,
          statusSets
        }),
        now: options.now
      })
    );
  }

  return states.filter((state) => nodeIds.has(state.object.id as ContentNode["id"]) || edgeIds.has(state.object.id as SemanticEdge["id"]));
}

export function buildGraphTooltipModel({
  object,
  title,
  kindLabel,
  summary,
  contains = [],
  url,
  citations = [],
  statuses = [],
  metadata = {}
}: {
  object: GraphObjectRef;
  title: string;
  kindLabel: string;
  summary?: string;
  contains?: string[];
  url?: string;
  citations?: AgentCitation[];
  statuses?: GraphVisualStatus[];
  metadata?: Record<string, unknown>;
}): GraphTooltipModel {
  return {
    object,
    title,
    kindLabel,
    summary,
    contains: contains.filter(Boolean).slice(0, 6),
    url: url && /^https?:\/\//i.test(url) ? url : undefined,
    citations: citations.slice(0, 6),
    statuses: uniqueStatuses(statuses),
    metadata
  };
}

export function buildGraphTetherPlan(from: GraphOverlayAnchor, to: GraphOverlayAnchor, status: GraphVisualStatus = "related"): GraphTetherPlan {
  const midX = (from.x + to.x) / 2;
  const midY = (from.y + to.y) / 2 - Math.min(42, Math.abs(from.x - to.x) * 0.08 + 18);
  return {
    from,
    to,
    status,
    path: `M ${from.x.toFixed(1)} ${from.y.toFixed(1)} Q ${midX.toFixed(1)} ${midY.toFixed(1)} ${to.x.toFixed(1)} ${to.y.toFixed(1)}`
  };
}

export function deriveGraphActivityEvents(input: GraphActivityDerivationInput): GraphActivityEvent[] {
  const occurredAt = input.occurredAt ?? new Date(0).toISOString();
  const events: GraphActivityEvent[] = [];

  for (const source of input.sources ?? []) {
    events.push(
      graphActivityEvent({
        projectId: input.projectId,
        graphId: input.graphId,
        kind: source.staleAt ? "knowledge_stale" : "source_incoming",
        status: source.staleAt ? "blocked" : "succeeded",
        subject: { kind: "source", id: source.id, label: source.title },
        sourceIds: [source.id],
        summary: source.staleAt ? `${source.title} is stale.` : `${source.title} is available as graph evidence.`,
        occurredAt: source.staleAt ?? source.updatedAt ?? occurredAt
      })
    );
  }

  for (const proposal of input.proposals ?? []) {
    const value = proposalValue(proposal);
    const label = stringValue(value.label) ?? stringValue(value.relation) ?? proposal.kind.replace("_", " ");
    events.push(
      graphActivityEvent({
        projectId: input.projectId,
        graphId: input.graphId,
        kind: proposal.status === "pending_review" ? "proposal_candidate" : reviewKindForProposalStatus(proposal.status),
        status: proposal.status === "pending_review" ? "ready" : "succeeded",
        subject: { kind: "proposal", id: proposal.id, label },
        sourceIds: proposal.provenance.flatMap((item) => item.sourceId ?? []),
        nodeIds: [stringValue(value.id), stringValue(value.sourceNodeId), stringValue(value.targetNodeId)].filter(Boolean) as ContentNode["id"][],
        proposalIds: [proposal.id],
        summary: `${label} is ${proposal.status.replaceAll("_", " ")}.`,
        occurredAt: proposal.createdAt || occurredAt,
        citations: proposal.provenance.map((item, index) => ({
          id: `citation-${proposal.id}-${index}`,
          label,
          sourceId: item.sourceId,
          locator: item.locator,
          url: item.sourceUri,
          confidence: proposal.confidence
        }))
      })
    );
  }

  for (const item of input.reviewQueueItems ?? []) {
    events.push(
      graphActivityEvent({
        projectId: input.projectId,
        graphId: input.graphId,
        kind: item.blocked ? "review_blocked" : "review_ready",
        status: item.blocked ? "blocked" : "ready",
        subject: { kind: "proposal", id: item.proposal.id, label: item.changeSummary ?? item.proposal.kind },
        sourceIds: item.source ? [item.source.id] : [],
        nodeIds: item.affectedGraphIds?.filter((id) => id.startsWith("node-")) as ContentNode["id"][] | undefined,
        proposalIds: [item.proposal.id],
        citations: item.citations ?? [],
        summary: item.reason,
        occurredAt
      })
    );
  }

  for (const decision of input.reviewDecisions ?? []) {
    events.push(
      graphActivityEvent({
        projectId: input.projectId,
        graphId: input.graphId,
        kind: reviewKindForDecision(decision.decision),
        status: "succeeded",
        subject: { kind: "review", id: decision.id, label: decision.decision },
        proposalIds: [decision.proposalId],
        reviewDecisionIds: [decision.id],
        summary: `${decision.decision} review decision recorded.`,
        occurredAt: decision.decidedAt || occurredAt
      })
    );
  }

  for (const run of input.agentRuns ?? []) {
    events.push(
      graphActivityEvent({
        projectId: input.projectId,
        graphId: input.graphId,
        kind: run.kind === "research" ? "research_started" : "agent_scan",
        status: agentStatus(run.status),
        subject: { kind: "agent_run", id: run.id, label: run.kind },
        agentRunId: run.id,
        sourceIds: stringArray(run.output.source_id),
        proposalIds: stringArray(run.output.proposal_ids) as ExtractionProposal["id"][],
        citations: citationsFromUnknown(run.output.citations),
        summary: stringValue(run.output.message) ?? stringValue(run.output.answer) ?? `${run.kind} agent run ${run.status}.`,
        occurredAt: run.finishedAt ?? run.startedAt ?? occurredAt
      })
    );
  }

  for (const call of input.toolCalls ?? []) {
    events.push(
      graphActivityEvent({
        projectId: input.projectId,
        graphId: input.graphId,
        kind: "agent_tool_call",
        status: agentToolStatus(call.status),
        subject: { kind: "tool_call", id: call.id, label: call.kind },
        agentToolCallId: call.id,
        nodeIds: call.affectedGraphIds.filter((id) => id.startsWith("node-")) as ContentNode["id"][],
        sourceIds: call.affectedGraphIds.filter((id) => id.startsWith("src") || id.startsWith("source")) as Source["id"][],
        proposalIds: call.resultingProposalId ? [call.resultingProposalId as ExtractionProposal["id"]] : [],
        citations: call.citations,
        summary: call.summary ?? `${call.kind} ${call.status}.`,
        occurredAt: call.finishedAt ?? call.startedAt ?? occurredAt
      })
    );
  }

  for (const citation of input.citations ?? []) {
    events.push(
      graphActivityEvent({
        projectId: input.projectId,
        graphId: input.graphId,
        kind: "evidence_cited",
        status: "succeeded",
        subject: { kind: citation.nodeId ? "node" : citation.sourceId ? "source" : "graph", id: citation.nodeId ?? citation.sourceId ?? citation.id, label: citation.label },
        sourceIds: citation.sourceId ? [citation.sourceId] : [],
        sourceChunkIds: citation.sourceChunkId ? [citation.sourceChunkId] : [],
        nodeIds: citation.nodeId ? [citation.nodeId] : [],
        proposalIds: citation.proposalId ? [citation.proposalId] : [],
        citations: [citation],
        summary: `${citation.label} cited as graph evidence.`,
        occurredAt
      })
    );
  }

  return events.sort((left, right) => right.occurredAt.localeCompare(left.occurredAt) || left.id.localeCompare(right.id));
}

export function applyGraphLens(data: RenderableGraph, lens: GraphLensId = "all"): GraphLensPlan {
  if (lens === "all") {
    return { lens, nodes: data.nodes, edges: data.edges, omittedNodeCount: 0, omittedEdgeCount: 0 };
  }

  const initialNodeIds = new Set(
    data.nodes.filter((node) => nodeMatchesLens(node, lens)).map((node) => node.id)
  );
  const lensEdgeIds = new Set(
    data.edges
      .filter(
        (edge) =>
          edgeMatchesLens(edge, lens) ||
          (initialNodeIds.has(edge.sourceNodeId) && initialNodeIds.has(edge.targetNodeId))
      )
      .map((edge) => edge.id)
  );
  const includedNodeIds = new Set(initialNodeIds);
  for (const edge of data.edges) {
    if (!lensEdgeIds.has(edge.id)) continue;
    includedNodeIds.add(edge.sourceNodeId);
    includedNodeIds.add(edge.targetNodeId);
  }

  const nodes = data.nodes.filter((node) => includedNodeIds.has(node.id));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = data.edges.filter(
    (edge) => lensEdgeIds.has(edge.id) && nodeIds.has(edge.sourceNodeId) && nodeIds.has(edge.targetNodeId)
  );

  return {
    lens,
    nodes,
    edges,
    omittedNodeCount: Math.max(0, data.nodes.length - nodes.length),
    omittedEdgeCount: Math.max(0, data.edges.length - edges.length)
  };
}

export function nodeMatchesLens(node: ContentNode, lens: Exclude<GraphLensId, "all">): boolean {
  if (metadataHasLens(node.metadata, lens)) return true;
  if (legacyModeMatchesLens(node.metadata, lens)) return true;
  if (lens === "engineering") {
    return ENGINEERING_NODE_KINDS.has(node.kind) || /^(Repository|Path|Symbol|Dependency|Issue|PR)\b/i.test(node.label);
  }
  if (lens === "ops") {
    return OPS_NODE_KINDS.has(node.kind) || /\b(policy|process|vendor|incident|project|owner|review)\b/i.test(node.label);
  }
  return RESEARCH_NODE_KINDS.has(node.kind);
}

export function edgeMatchesLens(edge: SemanticEdge, lens: Exclude<GraphLensId, "all">): boolean {
  if (metadataHasLens(edge.metadata, lens)) return true;
  if (legacyModeMatchesLens(edge.metadata, lens)) return true;
  if (lens === "engineering") return ENGINEERING_RELATIONS.has(edge.relation);
  if (lens === "ops") return OPS_RELATIONS.has(edge.relation);
  return RESEARCH_RELATIONS.has(edge.relation);
}

export function summarizeGraph(data: RenderableGraph): GraphSummary {
  const nodeIds = new Set(data.nodes.map((node) => node.id));
  const connectedEdges = data.edges.filter(
    (edge) => nodeIds.has(edge.sourceNodeId) && nodeIds.has(edge.targetNodeId)
  );
  const degreeByNodeId = new Map<string, number>();

  for (const edge of connectedEdges) {
    degreeByNodeId.set(edge.sourceNodeId, (degreeByNodeId.get(edge.sourceNodeId) ?? 0) + 1);
    degreeByNodeId.set(edge.targetNodeId, (degreeByNodeId.get(edge.targetNodeId) ?? 0) + 1);
  }

  return {
    nodeCount: data.nodes.length,
    edgeCount: data.edges.length,
    connectedEdgeCount: connectedEdges.length,
    orphanEdgeCount: data.edges.length - connectedEdges.length,
    nodeKindCounts: countBy(data.nodes, (node) => node.kind),
    relationCounts: countBy(connectedEdges, (edge) => edge.relation),
    topNodes: [...data.nodes]
      .sort((left, right) => {
        const degreeDelta = (degreeByNodeId.get(right.id) ?? 0) - (degreeByNodeId.get(left.id) ?? 0);
        if (degreeDelta !== 0) return degreeDelta;
        const labelDelta = left.label.localeCompare(right.label);
        if (labelDelta !== 0) return labelDelta;
        return left.id.localeCompare(right.id);
      })
      .slice(0, 5)
      .map((node) => ({ node, degree: degreeByNodeId.get(node.id) ?? 0 }))
  };
}

export function findShortestPath(
  data: RenderableGraph,
  sourceNodeId: string,
  targetNodeId: string,
  options: GraphPathOptions = DEFAULT_GRAPH_PATH_OPTIONS
): GraphPath | undefined {
  const maxDepth = Math.min(6, Math.max(1, options.maxDepth));
  const sourceId = sourceNodeId as ContentNode["id"];
  const targetId = targetNodeId as ContentNode["id"];
  const nodesById = new Map<ContentNode["id"], ContentNode>(data.nodes.map((node) => [node.id, node]));
  const sourceNode = nodesById.get(sourceId);
  const targetNode = nodesById.get(targetId);
  if (!sourceNode || !targetNode) return undefined;
  if (sourceId === targetId) {
    return { sourceNode, targetNode, maxDepth, pathFound: true, distance: 0, nodes: [sourceNode], edges: [] };
  }

  const edgesById = new Map<SemanticEdge["id"], SemanticEdge>(data.edges.map((edge) => [edge.id, edge]));
  const adjacency = new Map<ContentNode["id"], Array<{ neighborId: ContentNode["id"]; edgeId: SemanticEdge["id"] }>>();
  for (const node of data.nodes) adjacency.set(node.id, []);
  for (const edge of data.edges) {
    if (!nodesById.has(edge.sourceNodeId) || !nodesById.has(edge.targetNodeId)) continue;
    adjacency.get(edge.sourceNodeId)?.push({ neighborId: edge.targetNodeId, edgeId: edge.id });
    adjacency.get(edge.targetNodeId)?.push({ neighborId: edge.sourceNodeId, edgeId: edge.id });
  }
  for (const neighbors of adjacency.values()) {
    neighbors.sort((left, right) => {
      const leftNode = nodesById.get(left.neighborId);
      const rightNode = nodesById.get(right.neighborId);
      const leftEdge = edgesById.get(left.edgeId);
      const rightEdge = edgesById.get(right.edgeId);
      return (
        (leftNode?.label ?? left.neighborId).localeCompare(rightNode?.label ?? right.neighborId) ||
        left.neighborId.localeCompare(right.neighborId) ||
        (leftEdge?.relation ?? "").localeCompare(rightEdge?.relation ?? "") ||
        left.edgeId.localeCompare(right.edgeId)
      );
    });
  }

  const queue: ContentNode["id"][] = [sourceId];
  const distanceByNodeId = new Map<ContentNode["id"], number>([[sourceId, 0]]);
  const parentByNodeId = new Map<ContentNode["id"], { parentId: ContentNode["id"]; edgeId: SemanticEdge["id"] }>();
  let found = false;
  for (let index = 0; index < queue.length && !found; index += 1) {
    const currentId = queue[index];
    const currentDistance = distanceByNodeId.get(currentId) ?? 0;
    if (currentDistance >= maxDepth) continue;
    for (const { neighborId, edgeId } of adjacency.get(currentId) ?? []) {
      if (distanceByNodeId.has(neighborId)) continue;
      distanceByNodeId.set(neighborId, currentDistance + 1);
      parentByNodeId.set(neighborId, { parentId: currentId, edgeId });
      if (neighborId === targetId) {
        found = true;
        break;
      }
      queue.push(neighborId);
    }
  }

  if (!parentByNodeId.has(targetId)) {
    return { sourceNode, targetNode, maxDepth, pathFound: false, nodes: [], edges: [] };
  }

  const pathNodeIds: Array<ContentNode["id"]> = [targetId];
  const pathEdgeIds: Array<SemanticEdge["id"]> = [];
  let currentId = targetId;
  while (currentId !== sourceId) {
    const parent = parentByNodeId.get(currentId);
    if (!parent) break;
    pathNodeIds.push(parent.parentId);
    pathEdgeIds.push(parent.edgeId);
    currentId = parent.parentId;
  }
  pathNodeIds.reverse();
  pathEdgeIds.reverse();

  return {
    sourceNode,
    targetNode,
    maxDepth,
    pathFound: true,
    distance: pathEdgeIds.length,
    nodes: pathNodeIds.flatMap((nodeId) => {
      const node = nodesById.get(nodeId);
      return node ? [node] : [];
    }),
    edges: pathEdgeIds.flatMap((edgeId) => {
      const edge = edgesById.get(edgeId);
      return edge ? [edge] : [];
    })
  };
}

export function extractNeighborhood(
  data: RenderableGraph,
  centerNodeId: string,
  options: GraphNeighborhoodOptions = DEFAULT_GRAPH_NEIGHBORHOOD_OPTIONS
): GraphNeighborhood | undefined {
  const normalizedDepth = Math.min(2, Math.max(1, options.depth));
  const maxNodes = Math.max(1, options.maxNodes);
  const maxEdges = Math.max(0, options.maxEdges);
  const centerId = centerNodeId as ContentNode["id"];
  const nodesById = new Map<ContentNode["id"], ContentNode>(data.nodes.map((node) => [node.id, node]));
  const centerNode = nodesById.get(centerId);
  if (!centerNode) return undefined;

  const adjacency = new Map<ContentNode["id"], Set<ContentNode["id"]>>();
  const degreeByNodeId = new Map<ContentNode["id"], number>();
  for (const node of data.nodes) {
    adjacency.set(node.id, new Set());
    degreeByNodeId.set(node.id, 0);
  }
  for (const edge of data.edges) {
    if (!nodesById.has(edge.sourceNodeId) || !nodesById.has(edge.targetNodeId)) continue;
    adjacency.get(edge.sourceNodeId)?.add(edge.targetNodeId);
    adjacency.get(edge.targetNodeId)?.add(edge.sourceNodeId);
    degreeByNodeId.set(edge.sourceNodeId, (degreeByNodeId.get(edge.sourceNodeId) ?? 0) + 1);
    degreeByNodeId.set(edge.targetNodeId, (degreeByNodeId.get(edge.targetNodeId) ?? 0) + 1);
  }

  const distanceByNodeId = new Map<ContentNode["id"], number>([[centerNode.id, 0]]);
  let frontier = new Set<ContentNode["id"]>([centerNode.id]);
  for (let distance = 1; distance <= normalizedDepth; distance += 1) {
    const nextIds = new Set<ContentNode["id"]>();
    for (const nodeId of frontier) {
      for (const neighborId of adjacency.get(nodeId) ?? []) {
        if (!distanceByNodeId.has(neighborId)) nextIds.add(neighborId);
      }
    }
    for (const nextId of nextIds) distanceByNodeId.set(nextId, distance);
    frontier = nextIds;
  }

  const rankedNodeIds = [...distanceByNodeId.keys()].sort((left, right) => {
    const distanceDelta = (distanceByNodeId.get(left) ?? 0) - (distanceByNodeId.get(right) ?? 0);
    if (distanceDelta !== 0) return distanceDelta;
    const degreeDelta = (degreeByNodeId.get(right) ?? 0) - (degreeByNodeId.get(left) ?? 0);
    if (degreeDelta !== 0) return degreeDelta;
    const leftNode = nodesById.get(left);
    const rightNode = nodesById.get(right);
    return (leftNode?.label ?? left).localeCompare(rightNode?.label ?? right) || left.localeCompare(right);
  });
  const includedIds = new Set(rankedNodeIds.slice(0, maxNodes));
  includedIds.add(centerNode.id);
  const nodes = rankedNodeIds.flatMap((nodeId) => {
    const node = nodesById.get(nodeId);
    return node && includedIds.has(nodeId) ? [node] : [];
  });
  const neighborhoodEdges = data.edges
    .filter((edge) => includedIds.has(edge.sourceNodeId) && includedIds.has(edge.targetNodeId))
    .sort(
      (left, right) =>
        left.sourceNodeId.localeCompare(right.sourceNodeId) ||
        left.targetNodeId.localeCompare(right.targetNodeId) ||
        left.relation.localeCompare(right.relation) ||
        left.id.localeCompare(right.id)
    );

  return {
    centerNode,
    depth: normalizedDepth,
    nodes,
    edges: neighborhoodEdges.slice(0, maxEdges),
    omittedNodeCount: Math.max(0, rankedNodeIds.length - includedIds.size),
    omittedEdgeCount: Math.max(0, neighborhoodEdges.length - maxEdges)
  };
}

export function planGraphRender(
  data: RenderableGraph,
  limits: GraphRenderLimits = DEFAULT_GRAPH_RENDER_LIMITS,
  viewport: Pick<GraphViewport, "width" | "height"> = { width: 620, height: 460 }
): GraphRenderPlan {
  const normalizedLimits = {
    maxNodes: Math.max(1, limits.maxNodes),
    maxEdges: Math.max(0, limits.maxEdges),
    labelMaxLength: Math.max(8, limits.labelMaxLength)
  };
  const nodeIds = new Set(data.nodes.map((node) => node.id));
  const validEdges = data.edges.filter((edge) => nodeIds.has(edge.sourceNodeId) && nodeIds.has(edge.targetNodeId));
  const degreeByNodeId = new Map<string, number>();

  for (const edge of validEdges) {
    degreeByNodeId.set(edge.sourceNodeId, (degreeByNodeId.get(edge.sourceNodeId) ?? 0) + 1);
    degreeByNodeId.set(edge.targetNodeId, (degreeByNodeId.get(edge.targetNodeId) ?? 0) + 1);
  }

  const selectedNodes = [...data.nodes]
    .sort((left, right) => {
      const degreeDelta = (degreeByNodeId.get(right.id) ?? 0) - (degreeByNodeId.get(left.id) ?? 0);
      if (degreeDelta !== 0) return degreeDelta;
      const labelDelta = left.label.localeCompare(right.label);
      if (labelDelta !== 0) return labelDelta;
      return left.id.localeCompare(right.id);
    })
    .slice(0, normalizedLimits.maxNodes);
  const selectedNodeIds = new Set(selectedNodes.map((node) => node.id));
  const radiusX = Math.max(120, viewport.width * 0.37);
  const radiusY = Math.max(100, viewport.height * 0.33);
  const centerX = viewport.width / 2;
  const centerY = viewport.height / 2;
  const plannedNodes = selectedNodes.map((node, index) => {
    const angle = selectedNodes.length === 1 ? 0 : (Math.PI * 2 * index) / selectedNodes.length - Math.PI / 2;
    const label = truncateLabel(node.label, normalizedLimits.labelMaxLength);
    return {
      node,
      x: Math.round(centerX + Math.cos(angle) * radiusX),
      y: Math.round(centerY + Math.sin(angle) * radiusY),
      degree: degreeByNodeId.get(node.id) ?? 0,
      label,
      truncated: label !== node.label
    };
  });
  const plannedByNodeId = new Map(plannedNodes.map((node) => [node.node.id, node]));
  const renderableEdges = validEdges
    .filter((edge) => selectedNodeIds.has(edge.sourceNodeId) && selectedNodeIds.has(edge.targetNodeId))
    .slice(0, normalizedLimits.maxEdges)
    .flatMap((edge) => {
      const source = plannedByNodeId.get(edge.sourceNodeId);
      const target = plannedByNodeId.get(edge.targetNodeId);
      return source && target ? [{ edge, source, target }] : [];
    });

  return {
    nodes: plannedNodes,
    edges: renderableEdges,
    omittedNodeCount: Math.max(0, data.nodes.length - plannedNodes.length),
    omittedEdgeCount: Math.max(0, validEdges.length - renderableEdges.length),
    orphanEdgeCount: data.edges.length - validEdges.length,
    truncatedLabelCount: plannedNodes.filter((node) => node.truncated).length
  };
}

function truncateLabel(label: string, maxLength: number): string {
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 1).trimEnd()}...`;
}

function statusesForObject(
  id: string,
  {
    hovered,
    focused,
    related,
    dimmed,
    statusSets
  }: {
    hovered: boolean;
    focused: boolean;
    related: boolean;
    dimmed: boolean;
    statusSets: {
      matched: Set<string>;
      scanning: Set<string>;
      cited: Set<string>;
      incoming: Set<string>;
      candidate: Set<string>;
      ready: Set<string>;
      blocked: Set<string>;
      accepted: Set<string>;
      rejected: Set<string>;
      edited: Set<string>;
      deferred: Set<string>;
      stale: Set<string>;
      sensed: Set<string>;
      routed: Set<string>;
      assigned: Set<string>;
      sla_at_risk: Set<string>;
      action_proposed: Set<string>;
      action_running: Set<string>;
      outcome_waiting: Set<string>;
      outcome_succeeded: Set<string>;
      outcome_failed: Set<string>;
      feedback_applied: Set<string>;
      reopened: Set<string>;
    };
  }
): GraphVisualStatus[] {
  return uniqueStatuses([
    hovered ? "hover" : undefined,
    focused || statusSets.matched.has(id) ? "focus" : undefined,
    related ? "related" : undefined,
    statusSets.scanning.has(id) ? "scanning" : undefined,
    statusSets.cited.has(id) ? "cited" : undefined,
    statusSets.incoming.has(id) ? "incoming" : undefined,
    statusSets.candidate.has(id) ? "candidate" : undefined,
    statusSets.ready.has(id) ? "ready" : undefined,
    statusSets.blocked.has(id) ? "blocked" : undefined,
    statusSets.accepted.has(id) ? "accepted" : undefined,
    statusSets.rejected.has(id) ? "rejected" : undefined,
    statusSets.edited.has(id) ? "edited" : undefined,
    statusSets.deferred.has(id) ? "deferred" : undefined,
    statusSets.stale.has(id) ? "stale" : undefined,
    statusSets.sensed.has(id) ? "sensed" : undefined,
    statusSets.routed.has(id) ? "routed" : undefined,
    statusSets.assigned.has(id) ? "assigned" : undefined,
    statusSets.sla_at_risk.has(id) ? "sla_at_risk" : undefined,
    statusSets.action_proposed.has(id) ? "action_proposed" : undefined,
    statusSets.action_running.has(id) ? "action_running" : undefined,
    statusSets.outcome_waiting.has(id) ? "outcome_waiting" : undefined,
    statusSets.outcome_succeeded.has(id) ? "outcome_succeeded" : undefined,
    statusSets.outcome_failed.has(id) ? "outcome_failed" : undefined,
    statusSets.feedback_applied.has(id) ? "feedback_applied" : undefined,
    statusSets.reopened.has(id) ? "reopened" : undefined,
    dimmed ? "dimmed" : undefined
  ]);
}

function uniqueStatuses(statuses: Array<GraphVisualStatus | undefined>): GraphVisualStatus[] {
  const seen = new Set<GraphVisualStatus>();
  const filtered = statuses.filter((status): status is GraphVisualStatus => Boolean(status));
  for (const status of filtered) seen.add(status);
  return [...seen].sort((left, right) => VISUAL_STATUS_PRIORITY.indexOf(left) - VISUAL_STATUS_PRIORITY.indexOf(right));
}

function graphVisualState({
  object,
  statuses,
  now
}: {
  object: GraphObjectRef;
  statuses: GraphVisualStatus[];
  now?: string;
}): GraphVisualState {
  const primary = statuses[0];
  const dimmedOnly = statuses.length === 1 && primary === "dimmed";
  return {
    object,
    statuses,
    active: statuses.length > 0 && !dimmedOnly,
    intensity: primary ? Math.max(0.18, 1 - VISUAL_STATUS_PRIORITY.indexOf(primary) / VISUAL_STATUS_PRIORITY.length) : 0,
    reason: primary?.replaceAll("_", " "),
    updatedAt: now
  };
}

function graphActivityEvent({
  projectId,
  graphId,
  kind,
  status,
  subject,
  actorId,
  agentRunId,
  agentToolCallId,
  sourceIds = [],
  sourceChunkIds = [],
  nodeIds = [],
  edgeIds = [],
  proposalIds = [],
  reviewDecisionIds = [],
  citations = [],
  summary,
  metadata = {},
  occurredAt
}: {
  projectId: GraphProjectId;
  graphId?: string;
  kind: GraphActivityEvent["kind"];
  status: GraphActivityEvent["status"];
  subject: GraphObjectRef;
  actorId?: string;
  agentRunId?: AgentRun["id"];
  agentToolCallId?: string;
  sourceIds?: string[];
  sourceChunkIds?: string[];
  nodeIds?: string[];
  edgeIds?: string[];
  proposalIds?: string[];
  reviewDecisionIds?: string[];
  citations?: AgentCitation[];
  summary: string;
  metadata?: Record<string, unknown>;
  occurredAt: string;
}): GraphActivityEvent {
  const idParts = [kind, subject.kind, subject.id, occurredAt].filter(Boolean).join(":");
  return {
    id: `activity-${hashText(idParts)}` as GraphActivityEvent["id"],
    projectId,
    graphId,
    kind,
    status,
    subject,
    actorId,
    agentRunId,
    agentToolCallId,
    sourceIds: uniqueStrings(sourceIds) as GraphActivityEvent["sourceIds"],
    sourceChunkIds: uniqueStrings(sourceChunkIds) as GraphActivityEvent["sourceChunkIds"],
    nodeIds: uniqueStrings(nodeIds) as GraphActivityEvent["nodeIds"],
    edgeIds: uniqueStrings(edgeIds) as GraphActivityEvent["edgeIds"],
    proposalIds: uniqueStrings(proposalIds) as GraphActivityEvent["proposalIds"],
    reviewDecisionIds: uniqueStrings(reviewDecisionIds) as GraphActivityEvent["reviewDecisionIds"],
    citations,
    summary,
    metadata,
    occurredAt
  };
}

function proposalValue(proposal: ExtractionProposal): Record<string, unknown> {
  return typeof proposal.proposedValue === "object" && proposal.proposedValue !== null
    ? (proposal.proposedValue as Record<string, unknown>)
    : {};
}

function reviewKindForProposalStatus(status: ExtractionProposal["status"]): GraphActivityEventKind {
  if (status === "accepted") return "review_accepted";
  if (status === "rejected") return "review_rejected";
  if (status === "edited") return "review_edited";
  if (status === "deferred") return "review_deferred";
  return "proposal_candidate";
}

function reviewKindForDecision(decision: ReviewDecision["decision"]): GraphActivityEventKind {
  if (decision === "accept") return "review_accepted";
  if (decision === "reject") return "review_rejected";
  if (decision === "edit") return "review_edited";
  return "review_deferred";
}

function agentStatus(status: AgentRun["status"]): GraphActivityEventStatus {
  if (status === "queued" || status === "running") return "running";
  if (status === "waiting_for_review") return "ready";
  if (status === "completed") return "succeeded";
  if (status === "cancelled") return "cancelled";
  return "failed";
}

function agentToolStatus(status: AgentToolCall["status"]): GraphActivityEventStatus {
  if (status === "running") return "running";
  if (status === "pending_review") return "ready";
  if (status === "succeeded") return "succeeded";
  if (status === "blocked") return "blocked";
  return "failed";
}

function citationsFromUnknown(value: unknown): AgentCitation[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is AgentCitation => {
    return typeof item === "object" && item !== null && typeof (item as { id?: unknown }).id === "string";
  });
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function stringArray(value: unknown): string[] {
  if (typeof value === "string" && value.trim()) return [value];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function hashText(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash).toString(36);
}

function metadataHasLens(metadata: Record<string, unknown> | undefined, lens: Exclude<GraphLensId, "all">): boolean {
  const lenses = metadata?.extractionLenses;
  return Array.isArray(lenses) && lenses.some((value) => value === lens);
}

function legacyModeMatchesLens(metadata: Record<string, unknown> | undefined, lens: Exclude<GraphLensId, "all">): boolean {
  const mode = metadata?.mode;
  if (mode === "engineering-repository") return lens === "engineering";
  if (mode === "ops-document-map") return lens === "ops";
  if (mode === "research") return lens === "research";
  return false;
}

function countBy<TItem>(items: TItem[], getName: (item: TItem) => string): GraphSummaryCount[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const name = getName(item) || "unknown";
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts]
    .sort(([leftName, leftCount], [rightName, rightCount]) => rightCount - leftCount || leftName.localeCompare(rightName))
    .map(([name, count]) => ({ name, count }));
}
