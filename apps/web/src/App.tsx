import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import type { ContentNode, GraphProject, SemanticEdge } from "@graphview/shared-types";
import { GraphCanvas } from "./GraphCanvas";
import "./styles.css";

const queryClient = new QueryClient();

const sampleProject: GraphProject = {
  id: "project-demo" as GraphProject["id"],
  name: "Research Knowledge Map",
  description: "Prototype-informed shell for reviewed concepts, sources, and provenance.",
  createdAt: "2026-06-04T00:00:00.000Z",
  updatedAt: "2026-06-04T00:00:00.000Z"
};

const sampleNodes: ContentNode[] = [
  {
    id: "node-sources" as ContentNode["id"],
    projectId: sampleProject.id,
    topicIds: [],
    label: "Mixed sources",
    kind: "concept",
    summary: "Markdown, PDFs, URLs, notes, and repository or ops documents.",
    provenance: [],
    createdAt: sampleProject.createdAt,
    updatedAt: sampleProject.updatedAt
  },
  {
    id: "node-proposals" as ContentNode["id"],
    projectId: sampleProject.id,
    topicIds: [],
    label: "Extraction proposals",
    kind: "concept",
    summary: "Worker-generated candidates that require review before graph updates.",
    provenance: [],
    createdAt: sampleProject.createdAt,
    updatedAt: sampleProject.updatedAt
  },
  {
    id: "node-provenance" as ContentNode["id"],
    projectId: sampleProject.id,
    topicIds: [],
    label: "Provenance",
    kind: "concept",
    summary: "Source location and trace metadata for every accepted node and edge.",
    provenance: [],
    createdAt: sampleProject.createdAt,
    updatedAt: sampleProject.updatedAt
  },
  {
    id: "node-review" as ContentNode["id"],
    projectId: sampleProject.id,
    topicIds: [],
    label: "Review decisions",
    kind: "decision",
    summary: "Accept, reject, edit, or defer proposals.",
    provenance: [],
    createdAt: sampleProject.createdAt,
    updatedAt: sampleProject.updatedAt
  }
];

const sampleEdges: SemanticEdge[] = [
  {
    id: "edge-source-proposal" as SemanticEdge["id"],
    projectId: sampleProject.id,
    sourceNodeId: sampleNodes[0].id,
    targetNodeId: sampleNodes[1].id,
    relation: "causes",
    provenance: [],
    createdAt: sampleProject.createdAt,
    updatedAt: sampleProject.updatedAt
  },
  {
    id: "edge-proposal-review" as SemanticEdge["id"],
    projectId: sampleProject.id,
    sourceNodeId: sampleNodes[1].id,
    targetNodeId: sampleNodes[3].id,
    relation: "depends_on",
    provenance: [],
    createdAt: sampleProject.createdAt,
    updatedAt: sampleProject.updatedAt
  },
  {
    id: "edge-review-provenance" as SemanticEdge["id"],
    projectId: sampleProject.id,
    sourceNodeId: sampleNodes[3].id,
    targetNodeId: sampleNodes[2].id,
    relation: "supports",
    provenance: [],
    createdAt: sampleProject.createdAt,
    updatedAt: sampleProject.updatedAt
  }
];

async function fetchHealth() {
  const baseUrl = import.meta.env.VITE_GRAPHVIEW_API_BASE_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(`${baseUrl}/health`);
  if (!response.ok) throw new Error(`API health returned ${response.status}`);
  return response.json() as Promise<{ status: string; service: string }>;
}

function Shell() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: false });

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Graphview navigation">
        <div className="brand">Graphview</div>
        <nav>
          <a aria-current="page">Graph</a>
          <a>Sources</a>
          <a>Proposals</a>
          <a>Review</a>
        </nav>
        <section className="status-panel" aria-label="Service status">
          <span>API</span>
          <strong>{health.data?.status ?? (health.isError ? "offline" : "checking")}</strong>
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p>{sampleProject.name}</p>
            <h1>Reviewed knowledge graph</h1>
          </div>
          <div className="topbar-actions" aria-label="Current project metrics">
            <span>{sampleNodes.length} nodes</span>
            <span>{sampleEdges.length} edges</span>
          </div>
        </header>

        <div className="content-grid">
          <section className="graph-surface" aria-label="Graph preview">
            <GraphCanvas nodes={sampleNodes} edges={sampleEdges} />
          </section>
          <section className="review-queue" aria-label="Review queue">
            <h2>Proposal queue</h2>
            <article>
              <span>Ready</span>
              <strong>12 candidate concepts</strong>
              <p>Review before commit keeps the graph explainable and reversible.</p>
            </article>
            <article>
              <span>Traceable</span>
              <strong>4 source batches</strong>
              <p>Each proposal links back to source location and ingestion run metadata.</p>
            </article>
            <article>
              <span>Next</span>
              <strong>Auth and persistence</strong>
              <p>The Phase 2 shell is wired for API health, shared types, and service boundaries.</p>
            </article>
          </section>
        </div>
      </section>
    </main>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell />
    </QueryClientProvider>
  );
}
