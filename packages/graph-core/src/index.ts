import type { ContentNode, SemanticEdge } from "@graphview/shared-types";

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

export interface GraphRendererAdapter {
  mount(container: HTMLElement): void;
  unmount(): void;
  setData(data: RenderableGraph): void;
  focusNode(nodeId: string): void;
}

export function summarizeGraph(data: RenderableGraph) {
  const nodeIds = new Set(data.nodes.map((node) => node.id));
  const connectedEdges = data.edges.filter(
    (edge) => nodeIds.has(edge.sourceNodeId) && nodeIds.has(edge.targetNodeId)
  );

  return {
    nodeCount: data.nodes.length,
    edgeCount: data.edges.length,
    connectedEdgeCount: connectedEdges.length,
    orphanEdgeCount: data.edges.length - connectedEdges.length
  };
}
