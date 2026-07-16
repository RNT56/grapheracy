import type {
  ContentNode,
  ExtractionLensDescriptor,
  GraphLensDescriptor,
  GraphProject,
  GraphProjectId
} from "@graphview/shared-types";

export const DEFAULT_EXTRACTION_LENSES: ExtractionLensDescriptor[] = [
  {
    id: "research",
    label: "Research",
    summary: "Concepts, evidence, decisions, metrics, people, and organizations.",
    defaultProposalLimit: 6,
    sourceKinds: ["text", "markdown", "url", "pdf", "repository", "ops-document"],
    primaryNodeKinds: ["concept", "document", "decision", "term"],
    provenanceFields: ["source", "locator", "reviewer", "trace"]
  },
  {
    id: "engineering",
    label: "Engineering",
    summary: "Repositories, systems, components, dependencies, and delivery surfaces.",
    defaultProposalLimit: 8,
    sourceKinds: ["repository", "markdown", "text"],
    primaryNodeKinds: ["system", "repository", "file", "symbol", "package"],
    provenanceFields: ["repository", "path", "symbol", "dependency", "issue_or_pr"]
  },
  {
    id: "ops",
    label: "Operations",
    summary: "Policies, ownership, review cycles, incidents, and operational readiness.",
    defaultProposalLimit: 8,
    sourceKinds: ["ops-document", "markdown", "text"],
    primaryNodeKinds: ["document", "decision", "organization", "process", "policy", "owner"],
    provenanceFields: ["document", "owner", "review_cycle", "effective_date", "incident_or_project"]
  }
];

export const DEFAULT_GRAPH_LENSES: GraphLensDescriptor[] = [
  { id: "all", label: "All", summary: "Full reviewed graph.", activeByDefault: true },
  { id: "research", label: "Research", summary: "Concepts, documents, terms, and provenance.", activeByDefault: false },
  { id: "engineering", label: "Engineering", summary: "Systems, modules, dependencies, and architecture hotspots.", activeByDefault: false },
  { id: "ops", label: "Ops", summary: "Operations, ownership, policy, and review freshness.", activeByDefault: false }
];

export function emptyWorkspaceGraph(graphId: string, label?: string) {
  const project: GraphProject = {
    id: graphId as GraphProjectId,
    name: label ?? "Knowledge graph",
    description: "No reviewed graph data is available yet.",
    createdAt: "",
    updatedAt: ""
  };
  return { project, nodes: [] as ContentNode[], edges: [] };
}

export function emptyWorkspaceFocusNode(projectId: GraphProjectId): ContentNode {
  return {
    id: "workspace-empty-focus" as ContentNode["id"],
    projectId,
    topicIds: [],
    label: "No graph items yet",
    kind: "topic",
    summary: "Ingest a source, run extraction, and review proposals to populate this graph.",
    provenance: [],
    createdAt: "",
    updatedAt: ""
  };
}
