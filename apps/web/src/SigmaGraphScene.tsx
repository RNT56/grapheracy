import { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import FA2Layout from "graphology-layout-forceatlas2/worker";
import Sigma from "sigma";
import type { GraphBounds, GraphVisualStatus } from "@graphview/shared-types";
import { supportsWebGL } from "./graphRendererContract";
import type { GraphRendererSceneProps } from "./graphRendererContract";

interface Props extends GraphRendererSceneProps {
  runForceLayout: boolean;
  onViewportProjection?: (zoom: number, bounds: GraphBounds) => void;
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
  fitSequence,
  runForceLayout,
  reducedMotion,
  onAvailabilityChange,
  onHoverObject,
  onSelectNode,
  onActiveNodePosition,
  onRenderMetrics,
  onViewportProjection
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef(new Graph({ multi: true, type: "directed", allowSelfLoops: false }));
  const rendererRef = useRef<Sigma | null>(null);
  const layoutRef = useRef<FA2Layout | null>(null);
  const callbacksRef = useRef({
    onHoverObject,
    onSelectNode,
    onActiveNodePosition,
    onRenderMetrics,
    onViewportProjection,
    onAvailabilityChange
  });
  const selectedRef = useRef(selectedNodeId);
  const activeRef = useRef(activeNodeId);
  const reducedMotionRef = useRef(reducedMotion);
  const semanticMotionRef = useRef(false);
  const contextLostRef = useRef(false);
  const [unavailable, setUnavailable] = useState(false);
  const topologyKey = useMemo(() => graphTopologyKey(nodes, edges), [edges, nodes]);
  callbacksRef.current = {
    onHoverObject,
    onSelectNode,
    onActiveNodePosition,
    onRenderMetrics,
    onViewportProjection,
    onAvailabilityChange
  };
  selectedRef.current = selectedNodeId;
  activeRef.current = activeNodeId;
  reducedMotionRef.current = reducedMotion;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const graph = graphRef.current;
    if (!supportsWebGL()) {
      setUnavailable(true);
      callbacksRef.current.onAvailabilityChange(false);
      callbacksRef.current.onRenderMetrics({
        kind: "sigma-2d",
        visibleNodes: nodes.length,
        visibleEdges: edges.length,
        contextLost: true
      });
      return;
    }
    let renderer: Sigma;
    try {
      renderer = new Sigma(graph, container, {
        allowInvalidContainer: true,
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
          const semanticPulse =
            !reducedMotionRef.current &&
            statuses.some((status) => ["scanning", "incoming", "action_running", "outcome_waiting"].includes(status))
              ? 1 + Math.sin(performance.now() / 180) * 0.12
              : 1;
          return {
            ...data,
            color: colorFor(statuses, "#7184ad"),
            size: (selected ? Number(data.size) * 1.65 : Number(data.size)) * semanticPulse,
            highlighted: selected || statuses.includes("hover"),
            forceLabel: selected
          };
        },
        edgeReducer: (edgeId, data) => {
          const statuses = (graph.getEdgeAttribute(edgeId, "statuses") ?? []) as GraphVisualStatus[];
          const traversing = statuses.some((status) => ["scanning", "cited", "action_running"].includes(status));
          const flowPulse =
            traversing && !reducedMotionRef.current ? 1 + Math.sin(performance.now() / 140) * 0.35 : 1;
          return {
            ...data,
            color: colorFor(statuses, statuses.includes("candidate") ? "#826ba2" : "#2e3a54"),
            size:
              (statuses.some((status) => ["focus", "scanning", "action_running"].includes(status)) ? 2.2 : 0.8) *
              flowPulse,
            hidden: statuses.includes("dimmed") && graph.size > 50_000
          };
        }
      });
    } catch {
      setUnavailable(true);
      callbacksRef.current.onAvailabilityChange(false);
      callbacksRef.current.onRenderMetrics({
        kind: "sigma-2d",
        visibleNodes: nodes.length,
        visibleEdges: edges.length,
        contextLost: true
      });
      return;
    }
    setUnavailable(false);
    callbacksRef.current.onAvailabilityChange(true);
    rendererRef.current = renderer;
    renderer.on("enterNode", ({ node }) => callbacksRef.current.onHoverObject(node));
    renderer.on("leaveNode", () => {
      callbacksRef.current.onHoverObject(undefined);
      callbacksRef.current.onActiveNodePosition(undefined);
    });
    renderer.on("clickNode", ({ node }) => callbacksRef.current.onSelectNode(node));
    let lastActivePositionKey = "";
    const reportActivePosition = () => {
      const nodeId = activeRef.current;
      if (!nodeId || !graph.hasNode(nodeId)) {
        if (lastActivePositionKey) {
          lastActivePositionKey = "";
          callbacksRef.current.onActiveNodePosition(undefined);
        }
        return;
      }
      const point = renderer.getNodeDisplayData(nodeId);
      const bounds = container.getBoundingClientRect();
      if (!point) return;
      const viewportPoint = renderer.framedGraphToViewport(point);
      const x = (viewportPoint.x / Math.max(1, bounds.width)) * 900;
      const y = (viewportPoint.y / Math.max(1, bounds.height)) * 640;
      const visible =
        viewportPoint.x >= 0 &&
        viewportPoint.y >= 0 &&
        viewportPoint.x <= bounds.width &&
        viewportPoint.y <= bounds.height;
      const key = `${nodeId}:${Math.round(x)}:${Math.round(y)}:${visible ? "v" : "h"}`;
      if (key === lastActivePositionKey) return;
      lastActivePositionKey = key;
      callbacksRef.current.onActiveNodePosition({ nodeId, x, y, visible });
    };
    let metricWindowStartedAt = performance.now();
    let metricFrameCount = 0;
    const reportAfterRender = () => {
      reportActivePosition();
      metricFrameCount += 1;
      const now = performance.now();
      if (now - metricWindowStartedAt < 750) return;
      callbacksRef.current.onRenderMetrics({
        kind: "sigma-2d",
        visibleNodes: graph.order,
        visibleEdges: graph.size,
        framesPerSecond: metricFrameCount / ((now - metricWindowStartedAt) / 1_000),
        contextLost: contextLostRef.current
      });
      metricWindowStartedAt = now;
      metricFrameCount = 0;
    };
    renderer.on("afterRender", reportAfterRender);
    let viewportTimer: number | undefined;
    let lastViewportKey = "";
    const reportViewport = (ratio: number) => {
      const bounds = projectedBounds(renderer, container);
      const zoom = clampNumber(0.25 - Math.log2(ratio), 0, 16);
      const key = `${zoom.toFixed(2)}:${bounds.minX.toFixed(3)}:${bounds.minY.toFixed(3)}:${bounds.maxX.toFixed(3)}:${bounds.maxY.toFixed(3)}`;
      if (key === lastViewportKey) return;
      lastViewportKey = key;
      callbacksRef.current.onViewportProjection?.(zoom, bounds);
    };
    renderer.getCamera().on("updated", (state) => {
      if (viewportTimer) window.clearTimeout(viewportTimer);
      viewportTimer = window.setTimeout(() => reportViewport(state.ratio), 120);
    });

    let savedCameraState = renderer.getCamera().getState();
    const handleContextLost = (event: Event) => {
      event.preventDefault();
      contextLostRef.current = true;
      savedCameraState = renderer.getCamera().getState();
      callbacksRef.current.onAvailabilityChange(false);
      callbacksRef.current.onRenderMetrics({
        kind: "sigma-2d",
        visibleNodes: graph.order,
        visibleEdges: graph.size,
        contextLost: true
      });
    };
    const handleContextRestored = () => {
      contextLostRef.current = false;
      requestAnimationFrame(() => {
        renderer.refresh();
        renderer.getCamera().setState(savedCameraState);
        callbacksRef.current.onAvailabilityChange(true);
        callbacksRef.current.onRenderMetrics({
          kind: "sigma-2d",
          visibleNodes: graph.order,
          visibleEdges: graph.size,
          contextLost: false
        });
      });
    };
    const canvases = [...container.querySelectorAll("canvas")];
    for (const canvas of canvases) {
      canvas.addEventListener("webglcontextlost", handleContextLost);
      canvas.addEventListener("webglcontextrestored", handleContextRestored);
    }

    let motionFrame = 0;
    let lastMotionRefresh = 0;
    const refreshSemanticMotion = (timestamp: number) => {
      motionFrame = requestAnimationFrame(refreshSemanticMotion);
      if (!semanticMotionRef.current || reducedMotionRef.current || timestamp - lastMotionRefresh < 80) return;
      lastMotionRefresh = timestamp;
      renderer.refresh();
    };
    motionFrame = requestAnimationFrame(refreshSemanticMotion);

    return () => {
      if (viewportTimer) window.clearTimeout(viewportTimer);
      cancelAnimationFrame(motionFrame);
      for (const canvas of canvases) {
        canvas.removeEventListener("webglcontextlost", handleContextLost);
        canvas.removeEventListener("webglcontextrestored", handleContextRestored);
      }
      layoutRef.current?.kill();
      layoutRef.current = null;
      renderer.kill();
      rendererRef.current = null;
      graph.clear();
    };
  }, []);

  useEffect(() => {
    const graph = graphRef.current;
    semanticMotionRef.current = [...nodes, ...edges].some((item) =>
      item.statuses.some((status) => ["scanning", "incoming", "cited", "action_running", "outcome_waiting"].includes(status))
    );
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
    const renderer = rendererRef.current;
    if (renderer) {
      renderer.setSetting("hideEdgesOnMove", graph.size > 20_000);
      renderer.setSetting("labelDensity", graph.order > 5_000 ? 0.04 : 0.12);
      renderer.setSetting("labelGridCellSize", graph.order > 5_000 ? 180 : 100);
      renderer.setSetting("labelRenderedSizeThreshold", graph.order > 20_000 ? 18 : 10);
      callbacksRef.current.onRenderMetrics({
        kind: "sigma-2d",
        visibleNodes: graph.order,
        visibleEdges: graph.size,
        contextLost: contextLostRef.current
      });
    }
  }, [edges, nodes]);

  useEffect(() => {
    const graph = graphRef.current;
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
  }, [reducedMotion, runForceLayout, topologyKey]);

  useEffect(() => {
    rendererRef.current?.refresh();
    if (selectedNodeId && graphRef.current.hasNode(selectedNodeId)) {
      const position = rendererRef.current?.getNodeDisplayData(selectedNodeId);
      if (position) rendererRef.current?.getCamera().animate({ x: position.x, y: position.y, ratio: 0.65 }, { duration: reducedMotion ? 0 : 240 });
    }
  }, [activeNodeId, reducedMotion, selectedNodeId]);

  useEffect(() => {
    const camera = rendererRef.current?.getCamera();
    if (!camera) return;
    camera.animatedReset({ duration: reducedMotion ? 0 : 240 });
  }, [fitSequence, reducedMotion]);

  return (
    <div className="sigma-graph-scene" data-renderer="sigma" data-testid="sigma-graph-scene" ref={containerRef}>
      {unavailable && <div className="graph-webgl-unavailable" role="status">WebGL unavailable. Use the accessible graph data view.</div>}
    </div>
  );
}

function projectedBounds(renderer: Sigma, container: HTMLElement): GraphBounds {
  const rect = container.getBoundingClientRect();
  const topLeft = renderer.viewportToGraph({ x: 0, y: 0 });
  const bottomRight = renderer.viewportToGraph({ x: Math.max(1, rect.width), y: Math.max(1, rect.height) });
  const minX = clampNumber((Math.min(topLeft.x, bottomRight.x) / 900) * 2 - 1, -1, 1);
  const maxX = clampNumber((Math.max(topLeft.x, bottomRight.x) / 900) * 2 - 1, -1, 1);
  const minY = clampNumber((Math.min(topLeft.y, bottomRight.y) / 640) * 2 - 1, -1, 1);
  const maxY = clampNumber((Math.max(topLeft.y, bottomRight.y) / 640) * 2 - 1, -1, 1);
  if (maxX - minX < 0.0001 || maxY - minY < 0.0001) {
    return { minX: -1, minY: -1, maxX: 1, maxY: 1 };
  }
  return { minX, minY, maxX, maxY };
}

function graphTopologyKey(nodes: GraphRendererSceneProps["nodes"], edges: GraphRendererSceneProps["edges"]) {
  let hash = 2166136261;
  for (const value of [...nodes.map((node) => node.id), ...edges.map((edge) => edge.id)]) {
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
  }
  return `${nodes.length}:${edges.length}:${hash >>> 0}`;
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
