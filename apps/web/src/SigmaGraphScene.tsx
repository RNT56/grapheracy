import { useEffect, useRef } from "react";
import Graph from "graphology";
import FA2Layout from "graphology-layout-forceatlas2/worker";
import Sigma from "sigma";
import type { GraphVisualStatus } from "@graphview/shared-types";

export interface SigmaSceneNode {
  id: string;
  label: string;
  x: number;
  y: number;
  radius: number;
  statuses: GraphVisualStatus[];
}

export interface SigmaSceneEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  statuses: GraphVisualStatus[];
}

interface Props {
  nodes: SigmaSceneNode[];
  edges: SigmaSceneEdge[];
  selectedNodeId?: string;
  activeNodeId?: string;
  runForceLayout: boolean;
  reducedMotion: boolean;
  onHoverObject: (nodeId?: string) => void;
  onSelectNode: (nodeId: string) => void;
  onActiveNodePosition: (position?: { nodeId: string; x: number; y: number; visible: boolean }) => void;
  onCameraRatio: (ratio: number) => void;
}

const STATUS_COLORS: Partial<Record<GraphVisualStatus, string>> = {
  focus: "#f5f7ff",
  hover: "#f5f7ff",
  cited: "#77e6bc",
  scanning: "#8da8ff",
  candidate: "#c5a4ff",
  accepted: "#70dfab",
  rejected: "#ff7f8f",
  stale: "#d69b5b",
  action_running: "#7ec8ff",
  outcome_succeeded: "#70dfab",
  outcome_failed: "#ff7f8f"
};

function colorFor(statuses: GraphVisualStatus[], fallback: string) {
  for (const status of statuses) {
    const color = STATUS_COLORS[status];
    if (color) return color;
  }
  return fallback;
}

export function SigmaGraphScene({
  nodes,
  edges,
  selectedNodeId,
  activeNodeId,
  runForceLayout,
  reducedMotion,
  onHoverObject,
  onSelectNode,
  onActiveNodePosition,
  onCameraRatio
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef(new Graph({ multi: true, type: "directed", allowSelfLoops: false }));
  const rendererRef = useRef<Sigma | null>(null);
  const layoutRef = useRef<FA2Layout | null>(null);
  const callbacksRef = useRef({ onHoverObject, onSelectNode, onActiveNodePosition, onCameraRatio });
  const selectedRef = useRef(selectedNodeId);
  const activeRef = useRef(activeNodeId);
  callbacksRef.current = { onHoverObject, onSelectNode, onActiveNodePosition, onCameraRatio };
  selectedRef.current = selectedNodeId;
  activeRef.current = activeNodeId;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const graph = graphRef.current;
    const renderer = new Sigma(graph, container, {
      allowInvalidContainer: false,
      hideEdgesOnMove: graph.size > 20_000,
      labelDensity: graph.order > 5_000 ? 0.04 : 0.12,
      labelGridCellSize: graph.order > 5_000 ? 180 : 100,
      labelRenderedSizeThreshold: graph.order > 20_000 ? 18 : 10,
      minCameraRatio: 0.03,
      maxCameraRatio: 12,
      renderEdgeLabels: false,
      nodeReducer: (nodeId, data) => {
        const statuses = (graph.getNodeAttribute(nodeId, "statuses") ?? []) as GraphVisualStatus[];
        const selected = nodeId === selectedRef.current || statuses.includes("focus");
        return {
          ...data,
          color: colorFor(statuses, "#7184ad"),
          size: selected ? Number(data.size) * 1.65 : data.size,
          highlighted: selected || statuses.includes("hover"),
          forceLabel: selected
        };
      },
      edgeReducer: (edgeId, data) => {
        const statuses = (graph.getEdgeAttribute(edgeId, "statuses") ?? []) as GraphVisualStatus[];
        return {
          ...data,
          color: colorFor(statuses, statuses.includes("candidate") ? "#826ba2" : "#2e3a54"),
          size: statuses.some((status) => ["focus", "scanning", "action_running"].includes(status)) ? 2.2 : 0.8,
          hidden: statuses.includes("dimmed") && graph.size > 50_000
        };
      }
    });
    rendererRef.current = renderer;
    renderer.on("enterNode", ({ node }) => callbacksRef.current.onHoverObject(node));
    renderer.on("leaveNode", () => {
      callbacksRef.current.onHoverObject(undefined);
      callbacksRef.current.onActiveNodePosition(undefined);
    });
    renderer.on("clickNode", ({ node }) => callbacksRef.current.onSelectNode(node));
    const reportActivePosition = () => {
      const nodeId = activeRef.current;
      if (!nodeId || !graph.hasNode(nodeId)) return callbacksRef.current.onActiveNodePosition(undefined);
      const point = renderer.getNodeDisplayData(nodeId);
      const bounds = container.getBoundingClientRect();
      callbacksRef.current.onActiveNodePosition(
        point
          ? {
              nodeId,
              x: (point.x / Math.max(1, bounds.width)) * 900,
              y: (point.y / Math.max(1, bounds.height)) * 640,
              visible: point.x >= 0 && point.y >= 0 && point.x <= bounds.width && point.y <= bounds.height
            }
          : undefined
      );
    };
    renderer.on("afterRender", reportActivePosition);
    let lastRatio = renderer.getCamera().getState().ratio;
    renderer.getCamera().on("updated", (state) => {
      if (Math.abs(state.ratio - lastRatio) < 0.08) return;
      lastRatio = state.ratio;
      callbacksRef.current.onCameraRatio(state.ratio);
    });

    const canvas = container.querySelector("canvas:last-of-type");
    const recover = (event: Event) => {
      event.preventDefault();
      const cameraState = renderer.getCamera().getState();
      requestAnimationFrame(() => {
        renderer.refresh();
        renderer.getCamera().setState(cameraState);
      });
    };
    canvas?.addEventListener("webglcontextlost", recover);
    canvas?.addEventListener("webglcontextrestored", recover);

    return () => {
      canvas?.removeEventListener("webglcontextlost", recover);
      canvas?.removeEventListener("webglcontextrestored", recover);
      layoutRef.current?.kill();
      layoutRef.current = null;
      renderer.kill();
      rendererRef.current = null;
      graph.clear();
    };
  }, []);

  useEffect(() => {
    const graph = graphRef.current;
    const nodeIds = new Set(nodes.map((node) => node.id));
    graph.forEachNode((nodeId) => {
      if (!nodeIds.has(nodeId)) graph.dropNode(nodeId);
    });
    for (const node of nodes) {
      const attributes = {
        label: node.label,
        x: node.x,
        y: node.y,
        size: Math.max(2.5, Math.min(12, node.radius / 2.8)),
        color: colorFor(node.statuses, "#7184ad"),
        statuses: node.statuses
      };
      if (graph.hasNode(node.id)) graph.mergeNodeAttributes(node.id, attributes);
      else graph.addNode(node.id, attributes);
    }
    const edgeIds = new Set(edges.map((edge) => edge.id));
    graph.forEachEdge((edgeId) => {
      if (!edgeIds.has(edgeId)) graph.dropEdge(edgeId);
    });
    for (const edge of edges) {
      if (!graph.hasNode(edge.sourceNodeId) || !graph.hasNode(edge.targetNodeId)) continue;
      const attributes = { size: 0.8, color: "#2e3a54", statuses: edge.statuses };
      if (graph.hasEdge(edge.id)) graph.mergeEdgeAttributes(edge.id, attributes);
      else graph.addDirectedEdgeWithKey(edge.id, edge.sourceNodeId, edge.targetNodeId, attributes);
    }
    rendererRef.current?.refresh();

    layoutRef.current?.kill();
    layoutRef.current = null;
    if (runForceLayout && !reducedMotion && graph.order > 1 && graph.order <= 20_000) {
      const layout = new FA2Layout(graph, {
        settings: { barnesHutOptimize: graph.order > 1_000, gravity: 1, scalingRatio: 8, slowDown: 4 }
      });
      layoutRef.current = layout;
      layout.start();
      const timeout = window.setTimeout(() => {
        layout.stop();
        rendererRef.current?.refresh();
      }, Math.min(2_500, 350 + graph.order * 1.5));
      return () => window.clearTimeout(timeout);
    }
  }, [edges, nodes, reducedMotion, runForceLayout]);

  useEffect(() => {
    rendererRef.current?.refresh();
    if (selectedNodeId && graphRef.current.hasNode(selectedNodeId)) {
      const position = rendererRef.current?.getNodeDisplayData(selectedNodeId);
      if (position) rendererRef.current?.getCamera().animate({ x: position.x, y: position.y, ratio: 0.65 }, { duration: reducedMotion ? 0 : 240 });
    }
  }, [activeNodeId, reducedMotion, selectedNodeId]);

  return <div className="sigma-graph-scene" data-renderer="sigma" data-testid="sigma-graph-scene" ref={containerRef} />;
}
