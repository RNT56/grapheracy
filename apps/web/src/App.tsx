import { useState } from "react";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
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

interface ApiSource {
  id: string;
  title: string;
  kind: string;
  uri?: string | null;
}

interface ApiProposal {
  id: string;
  status: string;
  proposed_value: {
    label?: string;
    kind?: string;
    summary?: string;
  };
}

interface ApiGraph {
  project: GraphProject;
  nodes: ContentNode[];
  edges: SemanticEdge[];
}

const apiBaseUrl = import.meta.env.VITE_GRAPHVIEW_API_BASE_URL ?? "http://127.0.0.1:8000";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Graphview-User": "maintainer",
      ...init?.headers
    }
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function fetchHealth() {
  return fetchJson<{ status: string; service: string }>("/health");
}

function Shell() {
  const [sourceTitle, setSourceTitle] = useState("Research memo");
  const [searchText, setSearchText] = useState("");
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: false });
  const graph = useQuery({
    queryKey: ["graph"],
    queryFn: () => fetchJson<ApiGraph>("/graph"),
    retry: false
  });
  const sources = useQuery({
    queryKey: ["sources", searchText],
    queryFn: () =>
      fetchJson<{ sources: ApiSource[] }>(`/sources${searchText ? `?q=${encodeURIComponent(searchText)}` : ""}`),
    retry: false
  });
  const proposals = useQuery({
    queryKey: ["proposals"],
    queryFn: () => fetchJson<{ proposals: ApiProposal[] }>("/proposals"),
    retry: false
  });
  const reviewDecisions = useQuery({
    queryKey: ["review-decisions"],
    queryFn: () => fetchJson<{ review_decisions: unknown[] }>("/review-decisions"),
    retry: false
  });

  const createSource = useMutation({
    mutationFn: (title: string) =>
      fetchJson<ApiSource>("/sources", {
        method: "POST",
        body: JSON.stringify({ kind: "markdown", title, uri: `local://${title.toLowerCase().replaceAll(" ", "-")}` })
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      setSourceTitle("");
    }
  });

  const createProposal = useMutation({
    mutationFn: (sourceId: string) =>
      fetchJson<ApiProposal>("/proposals", {
        method: "POST",
        body: JSON.stringify({
          source_id: sourceId,
          kind: "content_node",
          confidence: 0.82,
          locator: "web shell",
          proposed_value: {
            label: "Reviewed concept",
            kind: "concept",
            summary: "Candidate concept created from the Phase 3 web shell."
          }
        })
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
      await queryClient.invalidateQueries({ queryKey: ["review-decisions"] });
    }
  });

  const reviewProposal = useMutation({
    mutationFn: (proposalId: string) =>
      fetchJson("/review-decisions", {
        method: "POST",
        body: JSON.stringify({ proposal_id: proposalId, decision: "accept", rationale: "Accepted from web shell" })
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
      await queryClient.invalidateQueries({ queryKey: ["review-decisions"] });
      await queryClient.invalidateQueries({ queryKey: ["graph"] });
    }
  });

  const graphData = graph.data ?? { project: sampleProject, nodes: sampleNodes, edges: sampleEdges };
  const sourceList = sources.data?.sources ?? [];
  const proposalList = proposals.data?.proposals ?? [];
  const pendingProposal = proposalList.find((proposal) => proposal.status === "pending_review");

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
            <p>{graphData.project.name}</p>
            <h1>Reviewed knowledge graph</h1>
          </div>
          <div className="topbar-actions" aria-label="Current project metrics">
            <span>{graphData.nodes.length} nodes</span>
            <span>{graphData.edges.length} edges</span>
          </div>
        </header>

        <div className="content-grid">
          <section className="graph-surface" aria-label="Graph preview">
            <GraphCanvas
              nodes={graphData.nodes.length > 0 ? graphData.nodes : sampleNodes}
              edges={graphData.edges.length > 0 ? graphData.edges : sampleEdges}
            />
          </section>
          <section className="review-queue" aria-label="Review queue">
            <h2>Proposal queue</h2>
            <form
              className="source-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (sourceTitle.trim()) createSource.mutate(sourceTitle.trim());
              }}
            >
              <label>
                Source title
                <input value={sourceTitle} onChange={(event) => setSourceTitle(event.target.value)} />
              </label>
              <button type="submit" disabled={createSource.isPending || !sourceTitle.trim()}>
                Add source
              </button>
            </form>
            <label className="search-field">
              Search sources
              <input value={searchText} onChange={(event) => setSearchText(event.target.value)} />
            </label>
            <article>
              <span>Ready</span>
              <strong>{proposalList.filter((proposal) => proposal.status === "pending_review").length} proposals</strong>
              <p>Review before commit keeps the graph explainable and reversible.</p>
            </article>
            <article>
              <span>Traceable</span>
              <strong>{sourceList.length} sources</strong>
              <p>{sourceList[0]?.title ?? "Add a source to create traceable proposals."}</p>
            </article>
            <article>
              <span>Review</span>
              <strong>{reviewDecisions.data?.review_decisions.length ?? 0} decisions</strong>
              <p>{pendingProposal?.proposed_value.label ?? "Accepted proposals commit graph nodes with provenance."}</p>
              <div className="queue-actions">
                <button
                  type="button"
                  disabled={!sourceList[0] || createProposal.isPending}
                  onClick={() => sourceList[0] && createProposal.mutate(sourceList[0].id)}
                >
                  Propose
                </button>
                <button
                  type="button"
                  disabled={!pendingProposal || reviewProposal.isPending}
                  onClick={() => pendingProposal && reviewProposal.mutate(pendingProposal.id)}
                >
                  Accept
                </button>
              </div>
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
