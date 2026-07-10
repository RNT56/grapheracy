import { useQuery } from "@tanstack/react-query";
import type { components } from "@graphview/api-client/schema";
import { normalizeContentNodeKind, type ContentNode, type ContentNodeId, type GraphProjectId, type SemanticEdge } from "@graphview/shared-types";
import type { GraphCanvasEdge } from "./GraphCanvas";

type GraphViewport = components["schemas"]["GraphViewportOut"];
type FetchJson = <T>(path: string, init?: RequestInit) => Promise<T>;

export function useViewportProjection(
  graphId: string,
  zoom: number,
  fallbackNodes: ContentNode[],
  fallbackEdges: GraphCanvasEdge[],
  fetchJson: FetchJson
) {
  const viewport = useQuery({
    queryKey: ["graph-viewport", graphId, zoom.toFixed(2)],
    queryFn: () => fetchJson<GraphViewport>(`/graphs/${encodeURIComponent(graphId)}/viewport?zoom=${zoom.toFixed(2)}&max_nodes=5000&max_edges=20000`),
    placeholderData: (previous) => previous,
    retry: false
  });
  if (!viewport.data) return { nodes: fallbackNodes, edges: fallbackEdges, omittedNodes: 0, omittedEdges: 0 };
  const projectId = viewport.data.project_id as GraphProjectId;
  const nodes: ContentNode[] = [
    ...viewport.data.nodes.map(({ node, x, y, z }) => ({
      id: node.id as ContentNode["id"],
      projectId: node.project_id as GraphProjectId,
      topicIds: node.topic_ids as ContentNode["topicIds"],
      label: node.label,
      kind: normalizeContentNodeKind(node.kind),
      summary: node.summary ?? undefined,
      metadata: { ...(node.metadata ?? {}), graphviewPosition: { x, y, z: z ?? 0 } },
      provenance: node.provenance as unknown as ContentNode["provenance"],
      createdAt: node.created_at,
      updatedAt: node.updated_at
    })),
    ...viewport.data.clusters.map((cluster) => ({
      id: cluster.id as ContentNode["id"],
      projectId,
      topicIds: [] as ContentNode["topicIds"],
      label: cluster.label,
      kind: normalizeContentNodeKind(cluster.dominant_kind),
      summary: `${cluster.node_count} nodes and ${cluster.edge_count} edges`,
      metadata: { graphviewCluster: true, nodeCount: cluster.node_count, nodeIds: cluster.node_ids, graphviewPosition: { x: cluster.x, y: cluster.y, z: 0 } },
      provenance: [],
      createdAt: new Date(0).toISOString(),
      updatedAt: new Date(0).toISOString()
    }))
  ];
  const visible = new Set(nodes.map((node) => node.id));
  const edges: GraphCanvasEdge[] = viewport.data.edges.flatMap((item) => {
    if (!visible.has(item.source_id as ContentNodeId) || !visible.has(item.target_id as ContentNodeId)) return [];
    if (item.edge) {
      return [{
        id: item.edge.id as SemanticEdge["id"],
        projectId: item.edge.project_id as GraphProjectId,
        sourceNodeId: item.edge.source_node_id as ContentNodeId,
        targetNodeId: item.edge.target_node_id as ContentNodeId,
        relation: item.edge.relation as SemanticEdge["relation"],
        weight: item.edge.weight ?? undefined,
        metadata: item.edge.metadata ?? {},
        provenance: item.edge.provenance as unknown as SemanticEdge["provenance"],
        createdAt: item.edge.created_at,
        updatedAt: item.edge.updated_at,
        reviewStatus: "accepted" as const
      }];
    }
    return [{
      id: item.id as SemanticEdge["id"],
      projectId,
      sourceNodeId: item.source_id as ContentNodeId,
      targetNodeId: item.target_id as ContentNodeId,
      relation: item.relation as SemanticEdge["relation"],
      weight: item.weight ?? undefined,
      metadata: { aggregateCount: item.count },
      provenance: [],
      createdAt: new Date(0).toISOString(),
      updatedAt: new Date(0).toISOString(),
      reviewStatus: "accepted" as const
    }];
  });
  const pending = fallbackEdges.filter((edge) => edge.reviewStatus === "pending_review" && visible.has(edge.sourceNodeId) && visible.has(edge.targetNodeId));
  return { nodes, edges: [...edges, ...pending], omittedNodes: viewport.data.omitted_node_count, omittedEdges: viewport.data.omitted_edge_count };
}
