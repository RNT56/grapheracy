import { useQuery } from "@tanstack/react-query";
import type { components } from "@graphview/api-client/schema";
import { normalizeContentNodeKind, type ContentNode, type ContentNodeId, type GraphBounds, type GraphProjectId, type SemanticEdge } from "@graphview/shared-types";
import type { GraphCanvasEdge } from "./GraphCanvas";

type GraphViewport = components["schemas"]["GraphViewportOut"];
type FetchJson = <T>(path: string, init?: RequestInit) => Promise<T>;

export function useViewportProjection(
  graphId: string,
  zoom: number,
  bounds: GraphBounds,
  fallbackNodes: ContentNode[],
  fallbackEdges: GraphCanvasEdge[],
  fetchJson: FetchJson
) {
  const viewport = useQuery({
    queryKey: [
      "graph-viewport",
      graphId,
      zoom.toFixed(2),
      bounds.minX.toFixed(4),
      bounds.minY.toFixed(4),
      bounds.maxX.toFixed(4),
      bounds.maxY.toFixed(4)
    ],
    queryFn: () => {
      const query = new URLSearchParams({
        zoom: zoom.toFixed(2),
        min_x: bounds.minX.toFixed(6),
        min_y: bounds.minY.toFixed(6),
        max_x: bounds.maxX.toFixed(6),
        max_y: bounds.maxY.toFixed(6),
        max_nodes: "20000",
        max_edges: "50000"
      });
      return fetchJson<GraphViewport>(`/graphs/${encodeURIComponent(graphId)}/viewport?${query}`);
    },
    placeholderData: (previous) => previous,
    retry: false
  });
  const projection = viewport.data;
  if (
    !projection ||
    !Array.isArray(projection.nodes) ||
    !Array.isArray(projection.edges) ||
    !Array.isArray(projection.clusters)
  ) {
    return {
      nodes: fallbackNodes,
      edges: fallbackEdges,
      omittedNodes: 0,
      omittedEdges: 0,
      graphVersion: 0,
      level: "nodes" as const
    };
  }
  const projectId = projection.project_id as GraphProjectId;
  const nodes: ContentNode[] = [
    ...projection.nodes.map(({ node, x, y, z }) => ({
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
    ...projection.clusters.map((cluster) => ({
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
  const edges: GraphCanvasEdge[] = projection.edges.flatMap((item) => {
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
  return {
    nodes,
    edges: [...edges, ...pending],
    omittedNodes: projection.omitted_node_count,
    omittedEdges: projection.omitted_edge_count,
    graphVersion: projection.graph_version,
    level: projection.level
  };
}
