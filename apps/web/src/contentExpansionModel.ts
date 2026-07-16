import {
  normalizeContentNodeKind,
  type ContentNode,
  type ContentNodeId,
  type ContentNodeKind,
  type GraphProject,
  type GraphRenderEdge as GraphCanvasEdge,
  type SemanticEdge,
  type Source,
  type SourceKind
} from "@graphview/shared-types";
import { sourceOriginPrefix } from "./sourceContentModel";
import { normalizeSourceKind } from "./workspaceModel";
import type {
  ApiPlanningSession,
  ApiProposal,
  ApiReviewActivity,
  ApiReviewQueue,
  ApiSource,
  ApiSourceChunk,
  ContentExpansionRole,
  ReviewWorkItemKind,
  SourceContentBlock
} from "./workspaceTypes";

export type ContentExpansionAction =
  | { type: "source"; sourceId: string; label: string }
  | { type: "proposal"; proposalId: string; label: string }
  | { type: "planning"; sessionId: string; label: string };

export interface ContentExpansionGraph {
  nodes: ContentNode[];
  edges: GraphCanvasEdge[];
  actions: Map<string, ContentExpansionAction>;
  chunkCount: number;
  proposalCount: number;
  planningCount: number;
}

export function proposalToGraphEdge(
  proposal: ApiProposal,
  projectId: GraphProject["id"],
  nodes: ContentNode[]
): GraphCanvasEdge[] {
  if (proposal.kind !== "semantic_edge" || proposal.status !== "pending_review") return [];
  const sourceNodeId = proposal.proposed_value.sourceNodeId;
  const targetNodeId = proposal.proposed_value.targetNodeId;
  if (!sourceNodeId || !targetNodeId || sourceNodeId === targetNodeId) return [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  if (!nodeIds.has(sourceNodeId as ContentNodeId) || !nodeIds.has(targetNodeId as ContentNodeId)) return [];
  return [
    {
      id: (proposal.proposed_value.id ?? `proposal-${proposal.id}`) as SemanticEdge["id"],
      projectId,
      sourceNodeId: sourceNodeId as ContentNodeId,
      targetNodeId: targetNodeId as ContentNodeId,
      relation: normalizeRelation(proposal.proposed_value.relation),
      weight: proposal.proposed_value.weight,
      provenance: [],
      createdAt: "",
      updatedAt: "",
      reviewStatus: "pending_review"
    }
  ];
}

export function reviewWorkItemLabel(
  kind: ReviewWorkItemKind | null | undefined,
  fallback: ApiReviewQueue["items"][number]["action"]
) {
  if (kind === "new_entity") return "New entity";
  if (kind === "new_relation") return "New relation";
  if (kind === "source_extraction") return "Source extraction";
  if (kind === "research_result") return "Research result";
  if (kind === "conflicting_fact") return "Conflict";
  if (kind === "stale_source") return "Stale source";
  if (kind === "connector_issue") return "Connector issue";
  if (kind === "planning_action") return "Planning action";
  return fallback.replaceAll("_", " ");
}

export function emptyContentExpansionGraph(): ContentExpansionGraph {
  return { nodes: [], edges: [], actions: new Map(), chunkCount: 0, proposalCount: 0, planningCount: 0 };
}

export function buildContentExpansionGraph({
  projectId,
  graphNodes,
  graphEdges,
  selectedGraphNode,
  selectedSource,
  contextSource,
  contextBlocks,
  sourceChunks,
  sources,
  proposals,
  reviewActivity,
  reviewQueue,
  planningSessions
}: {
  projectId: GraphProject["id"];
  graphNodes: ContentNode[];
  graphEdges: GraphCanvasEdge[];
  selectedGraphNode?: ContentNode;
  selectedSource?: ApiSource | Source;
  contextSource?: ApiSource | Source;
  contextBlocks: SourceContentBlock[];
  sourceChunks: ApiSourceChunk[];
  sources: Array<ApiSource | Source>;
  proposals: ApiProposal[];
  reviewActivity?: ApiReviewActivity;
  reviewQueue?: ApiReviewQueue;
  planningSessions: ApiPlanningSession[];
}): ContentExpansionGraph {
  const output = emptyContentExpansionGraph();
  const existingNodeIds = new Set<ContentNode["id"]>(graphNodes.map((node) => node.id));
  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const edgeKeys = new Set(graphEdges.map((edge) => `${edge.sourceNodeId}->${edge.targetNodeId}:${edge.relation}`));
  const fallbackAnchor = selectedGraphNode?.id ?? graphNodes[0]?.id;
  const selectedSourceId = selectedSource?.id;
  const contextSourceId = contextSource?.id;

  const sourceAnchor = (sourceId: string | undefined, fallback?: ContentNode["id"]) => {
    if (!sourceId) return fallback ?? fallbackAnchor;
    const sourceNode = graphNodes.find((node) => node.provenance.some((item) => item.sourceId === sourceId));
    return sourceNode?.id ?? fallback ?? fallbackAnchor;
  };

  const addNode = (
    role: ContentExpansionRole,
    stableId: string,
    label: string,
    kind: ContentNodeKind,
    summary: string,
    action?: ContentExpansionAction,
    metadata: Record<string, unknown> = {}
  ) => {
    const nodeId = contentExpansionNodeId(role, stableId);
    if (existingNodeIds.has(nodeId)) return nodeId;
    existingNodeIds.add(nodeId);
    output.nodes.push({
      id: nodeId,
      projectId,
      topicIds: [],
      label: truncatePlainLabel(label, 72),
      kind,
      summary,
      metadata: { ...metadata, contentExpansion: { role, stableId } },
      provenance: [],
      createdAt: "",
      updatedAt: ""
    });
    if (action) output.actions.set(nodeId, action);
    return nodeId;
  };

  const addEdge = (
    sourceNodeId: ContentNode["id"] | undefined,
    targetNodeId: ContentNode["id"],
    relation: SemanticEdge["relation"]
  ) => {
    if (!sourceNodeId || sourceNodeId === targetNodeId) return;
    const edgeKey = `${sourceNodeId}->${targetNodeId}:${relation}`;
    if (edgeKeys.has(edgeKey)) return;
    edgeKeys.add(edgeKey);
    output.edges.push({
      id: contentExpansionEdgeId(sourceNodeId, targetNodeId, relation),
      projectId,
      sourceNodeId,
      targetNodeId,
      relation,
      metadata: { contentExpansion: { role: "edge" } },
      provenance: [],
      createdAt: "",
      updatedAt: "",
      reviewStatus: "accepted"
    });
  };

  const addSourceRoot = (source: ApiSource | Source | undefined, anchorId?: ContentNode["id"]) => {
    if (!source) return undefined;
    const sourceNodeId = addNode(
      "source",
      source.id,
      source.title,
      sourceKindToContentKind(normalizeSourceKind(source.kind)),
      `${sourceOriginPrefix(source)}${source.kind} source`.trim(),
      { type: "source", sourceId: source.id, label: source.title },
      { sourceId: source.id }
    );
    addEdge(anchorId ?? sourceAnchor(source.id), sourceNodeId, "contains");
    return sourceNodeId;
  };

  const sourceRoots = new Map<string, ContentNode["id"]>();
  const ensureSourceRoot = (sourceId: string | undefined, preferredAnchor?: ContentNode["id"]) => {
    if (!sourceId) return undefined;
    const existing = sourceRoots.get(sourceId);
    if (existing) return existing;
    const root = addSourceRoot(sourceById.get(sourceId), preferredAnchor);
    if (root) sourceRoots.set(sourceId, root);
    return root;
  };

  const focusedSource = selectedSource ?? contextSource;
  if (focusedSource) {
    ensureSourceRoot(focusedSource.id, selectedGraphNode?.id ?? sourceAnchor(focusedSource.id));
  } else {
    sources.slice(0, 4).forEach((source, index) => {
      ensureSourceRoot(source.id, graphNodes[index % Math.max(1, graphNodes.length)]?.id ?? fallbackAnchor);
    });
  }

  const selectedChunkSourceIds = new Set([selectedSourceId, contextSourceId].filter(Boolean));
  const focusedChunks = sourceChunks
    .filter((chunk) => selectedChunkSourceIds.size === 0 || selectedChunkSourceIds.has(chunk.source_id))
    .sort((left, right) => left.ordinal - right.ordinal || left.id.localeCompare(right.id));
  const chunkCandidates = (focusedChunks.length > 0 ? focusedChunks : sourceChunks).slice(0, selectedSourceId ? 10 : 14);
  for (const chunk of chunkCandidates) {
    const source = sourceById.get(chunk.source_id);
    const sourceRoot = ensureSourceRoot(chunk.source_id, sourceAnchor(chunk.source_id));
    const heading = chunk.heading_path.at(-1) ?? chunk.heading_path[0];
    const label = heading || firstLine(chunk.text) || `${chunk.block_type} ${chunk.ordinal + 1}`;
    const chunkNodeId = addNode(
      "chunk",
      chunk.id,
      label,
      sourceKindToContentKind(normalizeSourceKind(source?.kind)),
      `${chunk.block_type} / ${chunk.locator}\n${truncatePlainLabel(chunk.text, 180)}`,
      source ? { type: "source", sourceId: source.id, label: source.title } : undefined,
      { sourceId: chunk.source_id, chunkId: chunk.id, locator: chunk.locator }
    );
    addEdge(sourceRoot ?? sourceAnchor(chunk.source_id), chunkNodeId, "contains");
    output.chunkCount += 1;
  }

  if (chunkCandidates.length === 0 && focusedSource) {
    contextBlocks.slice(0, 8).forEach((block) => {
      const sourceRoot = ensureSourceRoot(focusedSource.id, selectedGraphNode?.id ?? sourceAnchor(focusedSource.id));
      const label = block.heading_path.at(-1) ?? firstLine(block.text) ?? `${block.block_type} ${block.ordinal + 1}`;
      const blockNodeId = addNode(
        "chunk",
        block.id,
        label,
        sourceKindToContentKind(normalizeSourceKind(focusedSource.kind)),
        `${block.block_type} / ${block.locator}\n${truncatePlainLabel(block.text, 180)}`,
        { type: "source", sourceId: focusedSource.id, label: focusedSource.title },
        { sourceId: focusedSource.id, locator: block.locator }
      );
      addEdge(sourceRoot ?? selectedGraphNode?.id ?? fallbackAnchor, blockNodeId, "contains");
      output.chunkCount += 1;
    });
  }

  const proposalCandidates = [
    ...(reviewQueue?.items.map((item) => item.proposal) ?? []),
    ...proposals.filter((proposal) => proposal.status === "pending_review")
  ]
    .filter(uniqueById)
    .filter((proposal) => proposalMatchesFocus(proposal, selectedGraphNode, selectedSourceId) || !selectedGraphNode)
    .slice(0, selectedGraphNode ? 4 : 6);
  for (const proposal of proposalCandidates) {
    const anchor = proposalAnchor(proposal, graphNodes) ?? selectedGraphNode?.id ?? fallbackAnchor;
    const label = proposal.proposed_value.label ?? proposal.proposed_value.relation ?? "Pending proposal";
    const proposalNodeId = addNode(
      "proposal",
      proposal.id,
      label,
      proposal.kind === "semantic_edge" ? "decision" : normalizeContentNodeKind(proposal.proposed_value.kind),
      `${proposal.kind.replace("_", " ")} / ${proposal.status}`,
      { type: "proposal", proposalId: proposal.id, label },
      { proposalId: proposal.id, status: proposal.status }
    );
    addEdge(anchor, proposalNodeId, proposal.status === "pending_review" ? "has_review_cycle" : "references");
    output.proposalCount += 1;
  }

  for (const item of (reviewActivity?.items ?? []).slice(0, 3)) {
    const label = item.summary || `${item.decision.decision} review`;
    const anchor = item.proposal ? proposalAnchor(item.proposal, graphNodes) : undefined;
    const decisionNodeId = addNode(
      "decision",
      item.decision.id,
      label,
      "decision",
      `${item.decision.decision} by ${item.decision.reviewer_id}`,
      item.proposal ? { type: "proposal", proposalId: item.proposal.id, label } : undefined,
      { proposalId: item.proposal?.id, decisionId: item.decision.id }
    );
    addEdge(anchor ?? selectedGraphNode?.id ?? fallbackAnchor, decisionNodeId, "governs");
  }

  const planningTaskCandidates = planningSessions
    .flatMap((session) => {
      const tasks = session.build_spec?.spec.research_tasks ?? [];
      const questions = session.build_spec?.spec.open_questions ?? [];
      return [
        ...tasks.map((task, index) => ({
          id: `${session.id}-task-${index}`,
          session,
          label: task.query ?? "Research task",
          summary: `${task.priority ?? "review"} / ${task.source_policy ?? "mixed sources"}`
        })),
        ...questions.slice(0, Math.max(0, 3 - tasks.length)).map((question, index) => ({
          id: `${session.id}-question-${index}`,
          session,
          label: question,
          summary: "Open planning question"
        }))
      ];
    })
    .slice(0, 4);
  for (const task of planningTaskCandidates) {
    const taskNodeId = addNode(
      "task",
      task.id,
      task.label,
      "task",
      task.summary,
      { type: "planning", sessionId: task.session.id, label: task.label },
      { planningSessionId: task.session.id }
    );
    addEdge(selectedGraphNode?.id ?? fallbackAnchor, taskNodeId, "contains");
    output.planningCount += 1;
  }

  return output;
}

function normalizeRelation(relation?: string): SemanticEdge["relation"] {
  const relations: ReadonlySet<string> = new Set([
    "supports", "contradicts", "depends_on", "causes", "mentions", "defines", "relates_to", "contains",
    "part_of", "references", "imports", "implements", "owned_by", "has_review_cycle", "governs"
  ]);
  return relations.has(relation ?? "") ? relation as SemanticEdge["relation"] : "relates_to";
}

function contentExpansionNodeId(role: ContentExpansionRole, stableId: string): ContentNode["id"] {
  return `contents-${role}-${stableId.replaceAll(/[^a-zA-Z0-9_-]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 96)}` as ContentNode["id"];
}

function contentExpansionEdgeId(
  sourceNodeId: ContentNode["id"],
  targetNodeId: ContentNode["id"],
  relation: SemanticEdge["relation"]
): SemanticEdge["id"] {
  return `contents-edge-${sourceNodeId}-${targetNodeId}-${relation}`.replaceAll(/[^a-zA-Z0-9_-]+/g, "-").slice(0, 180) as SemanticEdge["id"];
}

function sourceKindToContentKind(kind: SourceKind | undefined): ContentNodeKind {
  if (kind === "markdown") return "markdown";
  if (kind === "url") return "url";
  if (kind === "pdf") return "pdf";
  if (kind === "repository") return "file";
  if (kind === "ops-document") return "ops_document";
  return "text";
}

export function firstLine(value: string) {
  return value.split(/\r?\n/).map((line) => line.trim()).find(Boolean);
}

export function truncatePlainLabel(value: string, limit: number) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > limit ? `${normalized.slice(0, Math.max(0, limit - 1)).trim()}…` : normalized;
}

export function uniqueById<T extends { id: string }>(item: T, index: number, items: T[]) {
  return items.findIndex((candidate) => candidate.id === item.id) === index;
}

function proposalMatchesFocus(
  proposal: ApiProposal,
  selectedGraphNode: ContentNode | undefined,
  selectedSourceId: string | undefined
) {
  if (!selectedGraphNode && !selectedSourceId) return true;
  if (selectedGraphNode) {
    const proposed = proposal.proposed_value;
    if (
      proposed.id === selectedGraphNode.id ||
      proposed.sourceNodeId === selectedGraphNode.id ||
      proposed.targetNodeId === selectedGraphNode.id
    ) {
      return true;
    }
    const label = `${proposed.label ?? ""} ${proposed.sourceLabel ?? ""} ${proposed.targetLabel ?? ""}`.toLowerCase();
    if (selectedGraphNode.label && label.includes(selectedGraphNode.label.toLowerCase())) return true;
  }
  return !selectedSourceId;
}

function proposalAnchor(proposal: ApiProposal, graphNodes: ContentNode[]) {
  const proposed = proposal.proposed_value;
  const idCandidates = [proposed.id, proposed.sourceNodeId, proposed.targetNodeId].filter(Boolean);
  for (const id of idCandidates) {
    const node = graphNodes.find((candidate) => candidate.id === id);
    if (node) return node.id;
  }
  const labelCandidates = [proposed.label, proposed.sourceLabel, proposed.targetLabel]
    .filter(Boolean)
    .map((label) => String(label).toLowerCase());
  return graphNodes.find((node) =>
    labelCandidates.some((label) => node.label.toLowerCase().includes(label) || label.includes(node.label.toLowerCase()))
  )?.id;
}
