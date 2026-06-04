export type Id<T extends string> = string & { readonly __type: T };

export type GraphProjectId = Id<"GraphProject">;
export type TopicId = Id<"Topic">;
export type SourceId = Id<"Source">;
export type ContentNodeId = Id<"ContentNode">;
export type SemanticEdgeId = Id<"SemanticEdge">;
export type IngestionRunId = Id<"IngestionRun">;
export type ExtractionProposalId = Id<"ExtractionProposal">;
export type ReviewDecisionId = Id<"ReviewDecision">;

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
  kind: "text" | "markdown" | "url" | "pdf" | "repository" | "ops-document";
  title: string;
  uri?: string;
  objectKey?: string;
  checksum?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ContentNode {
  id: ContentNodeId;
  projectId: GraphProjectId;
  topicIds: TopicId[];
  label: string;
  kind: "concept" | "person" | "organization" | "document" | "system" | "decision" | "term";
  summary?: string;
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
    | "relates_to";
  weight?: number;
  provenance: Provenance[];
  createdAt: string;
  updatedAt: string;
}

export interface IngestionRun {
  id: IngestionRunId;
  projectId: GraphProjectId;
  sourceId: SourceId;
  status: "queued" | "running" | "proposal_ready" | "committed" | "failed" | "cancelled";
  stage: "fetch" | "extract" | "analyze" | "propose" | "commit";
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
