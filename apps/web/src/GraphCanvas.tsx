import { lazy, Suspense, useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import {
  buildGraphTetherPlan,
  buildGraphTooltipModel,
  planGraphRender,
  resolveGraphVisualStates,
  selectGraphAnimationBudget
} from "@graphview/graph-core";
import {
  NODE_KIND_DEFINITIONS,
  type AgentCitation,
  type ContentNode,
  type GraphBounds,
  type GraphActivityEvent,
  type GraphRenderEdge,
  type GraphVisualState,
  type GraphVisualStatus,
  type SemanticEdge
} from "@graphview/shared-types";
import { SigmaGraphScene } from "./SigmaGraphScene";
import { AccessibleGraphData } from "./AccessibleGraphData";
import { GraphTooltipLayer } from "./GraphTooltipLayer";
import { projectedGraphPositions } from "./projectedGraphPositions";
import type { GraphRendererEdge, GraphRendererNode, GraphRendererRuntimeMetrics } from "./graphRendererContract";

export type GraphLayoutMode = "force" | "radial" | "arc";
export type GraphDimensionMode = "2d" | "3d";
export type GraphCanvasEdge = GraphRenderEdge;

export interface GraphCanvasSource {
  id: string;
  title: string;
  kind?: string | null;
  uri?: string | null;
  remoteUrl?: string | null;
  remote_url?: string | null;
  staleAt?: string | null;
  stale_at?: string | null;
}

interface Props {
  nodes: ContentNode[];
  edges: GraphCanvasEdge[];
  sources?: GraphCanvasSource[];
  citations?: AgentCitation[];
  activityEvents?: GraphActivityEvent[];
  layout: GraphLayoutMode;
  dimension: GraphDimensionMode;
  showContents: boolean;
  query: string;
  selectedNodeId?: ContentNode["id"];
  fitSequence: number;
  graphVersion?: number;
  projectionLevel?: "clusters" | "mixed" | "nodes";
  serverOmittedNodeCount?: number;
  serverOmittedEdgeCount?: number;
  onSelectNode?: (nodeId: ContentNode["id"]) => void;
  onViewportProjection?: (zoom: number, bounds: GraphBounds) => void;
}

interface ViewNode {
  node: ContentNode;
  x: number;
  y: number;
  z: number;
  sx: number;
  sy: number;
  scale: number;
  depth: number;
  radius: number;
  degree: number;
  label: string;
  truncated: boolean;
  matched: boolean;
  selected: boolean;
  related: boolean;
  dimmed: boolean;
  labelVisible: boolean;
  kindIndex: number;
  statuses: GraphVisualStatus[];
  contentRole?: string;
}

interface ViewEdge {
  edge: GraphCanvasEdge;
  source: ViewNode;
  target: ViewNode;
  path: string;
  labelX: number;
  labelY: number;
  selected: boolean;
  dimmed: boolean;
  statuses: GraphVisualStatus[];
}

interface CameraState {
  panX: number;
  panY: number;
  zoom: number;
  yaw: number;
  pitch: number;
}

interface DragState {
  mode: "pan" | "orbit";
  pointerId: number;
  x: number;
  y: number;
}

interface TooltipAnchor {
  x: number;
  y: number;
  placement: "right" | "left" | "top" | "bottom";
}

interface TooltipSourcePoint {
  nodeId: ContentNode["id"];
  sx: number;
  sy: number;
  radius: number;
}

interface ThreeActiveNodePosition {
  nodeId: string;
  x: number;
  y: number;
  visible: boolean;
}

const VIEWBOX = { width: 900, height: 640 };
const DEFAULT_CAMERA: CameraState = { panX: 0, panY: 0, zoom: 1, yaw: -0.58, pitch: 0.58 };
const NODE_KIND_ORDER = NODE_KIND_DEFINITIONS.map((definition) => definition.id);
const NODE_KIND_INDEX = new Map(NODE_KIND_ORDER.map((kind, index) => [kind, index]));
const LazyThreeGraphScene = lazy(async () => {
  const module = await import("./ThreeGraphScene");
  return { default: module.ThreeGraphScene };
});

export function GraphCanvas({
  nodes,
  edges,
  sources = [],
  citations = [],
  activityEvents = [],
  layout,
  dimension,
  showContents,
  query,
  selectedNodeId,
  fitSequence,
  graphVersion = 0,
  projectionLevel = "nodes",
  serverOmittedNodeCount = 0,
  serverOmittedEdgeCount = 0,
  onSelectNode,
  onViewportProjection
}: Props) {
  const [camera, setCamera] = useState<CameraState>(DEFAULT_CAMERA);
  const [hoveredObjectId, setHoveredObjectId] = useState<string | undefined>();
  const [keyboardFocusObjectId, setKeyboardFocusObjectId] = useState<string | undefined>();
  const [threeActiveNodePosition, setThreeActiveNodePosition] = useState<ThreeActiveNodePosition | undefined>();
  const [rendererAvailable, setRendererAvailable] = useState<boolean>();
  const [rendererMetrics, setRendererMetrics] = useState<GraphRendererRuntimeMetrics>();
  const dragRef = useRef<DragState | null>(null);
  const effectiveDimension = layout === "arc" ? "2d" : dimension;
  const use3d = effectiveDimension === "3d";
  const useSigma2d = !use3d;
  const renderLimits = useMemo(
    () => effectiveDimension === "2d"
      ? { maxNodes: 20_000, maxEdges: 50_000, labelMaxLength: 64 }
      : { maxNodes: 2_000, maxEdges: 5_000, labelMaxLength: 48 },
    [effectiveDimension]
  );
  const renderBudget = useMemo(() => planGraphRender({ nodes, edges }, renderLimits), [edges, nodes, renderLimits]);
  const animationBudget = useMemo(
    () =>
      selectGraphAnimationBudget(
        { nodes, edges },
        { reducedMotion: typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches }
      ),
    [edges, nodes]
  );
  const hasPersistedPositions = useMemo(
    () => nodes.length > 0 && nodes.every((node) => {
      const position = node.metadata?.graphviewPosition as { x?: unknown; y?: unknown } | undefined;
      return typeof position?.x === "number" && typeof position.y === "number";
    }),
    [nodes]
  );
  const activityHints = useMemo(() => graphActivityHints(activityEvents, edges), [activityEvents, edges]);
  const visualStates = useMemo(
    () =>
      resolveGraphVisualStates(
        { nodes, edges },
        {
          hoveredObjectId,
          focusedObjectId: keyboardFocusObjectId ?? selectedNodeId,
          selectedNodeId,
          queryMatchedIds: nodes
            .filter((node) => {
              const text = query.trim().toLowerCase();
              return text && `${node.label} ${node.kind} ${node.summary ?? ""}`.toLowerCase().includes(text);
            })
            .map((node) => node.id),
          ...activityHints
        }
      ),
    [activityHints, edges, hoveredObjectId, keyboardFocusObjectId, nodes, query, selectedNodeId]
  );
  const visualStateById = useMemo(() => new Map(visualStates.map((state) => [state.object.id, state])), [visualStates]);

  useEffect(() => {
    setCamera(DEFAULT_CAMERA);
    dragRef.current = null;
  }, [dimension, fitSequence, layout]);

  const view = useMemo(
    () =>
      buildGraphView({
        nodes: renderBudget.nodes.map((node) => node.node),
        edges: renderBudget.edges.map((edge) => edge.edge),
        layout,
        dimension,
        showContents,
        query,
        selectedNodeId,
        camera,
        visualStateById
      }),
    [camera, dimension, layout, query, renderBudget.edges, renderBudget.nodes, selectedNodeId, showContents, visualStateById]
  );
  const hasOmissions =
    serverOmittedNodeCount > 0 || serverOmittedEdgeCount > 0 ||
    renderBudget.omittedNodeCount > 0 || renderBudget.omittedEdgeCount > 0 || renderBudget.orphanEdgeCount > 0;
  const rendererNodes = useMemo<GraphRendererNode[]>(
    () =>
      view.nodes.map((viewNode) => ({
        id: viewNode.node.id,
        label: viewNode.node.label,
        kind: viewNode.node.kind,
        x: viewNode.x,
        y: viewNode.y,
        z: viewNode.z,
        radius: viewNode.radius,
        statuses: viewNode.statuses
      })),
    [view.nodes]
  );
  const rendererEdges = useMemo<GraphRendererEdge[]>(
    () =>
      view.edges.map((viewEdge) => ({
        id: viewEdge.edge.id,
        sourceNodeId: viewEdge.edge.sourceNodeId,
        targetNodeId: viewEdge.edge.targetNodeId,
        relation: viewEdge.edge.relation,
        statuses: viewEdge.statuses
      })),
    [view.edges]
  );
  const worldTransform = `translate(${camera.panX.toFixed(1)} ${camera.panY.toFixed(1)}) scale(${camera.zoom.toFixed(3)})`;
  const activeTooltipNode = useMemo(
    () => view.nodes.find((node) => node.node.id === hoveredObjectId) ?? view.nodes.find((node) => node.node.id === selectedNodeId),
    [hoveredObjectId, selectedNodeId, view.nodes]
  );
  const activeTooltipPoint = useMemo<TooltipSourcePoint | undefined>(() => {
    if (!activeTooltipNode) return undefined;
    if (
      threeActiveNodePosition?.visible &&
      threeActiveNodePosition.nodeId === activeTooltipNode.node.id
    ) {
      return {
        nodeId: activeTooltipNode.node.id,
        sx: threeActiveNodePosition.x,
        sy: threeActiveNodePosition.y,
        radius: activeTooltipNode.radius * activeTooltipNode.scale
      };
    }
    if (use3d || useSigma2d) return undefined;
    return {
      nodeId: activeTooltipNode.node.id,
      sx: activeTooltipNode.sx,
      sy: activeTooltipNode.sy,
      radius: activeTooltipNode.radius * activeTooltipNode.scale
    };
  }, [activeTooltipNode, threeActiveNodePosition, use3d, useSigma2d]);
  const tooltip = useMemo(
    () =>
      activeTooltipNode
        ? buildNodeTooltip({
            viewNode: activeTooltipNode,
            nodes,
            edges,
            sources,
            citations,
            visualState: visualStateById.get(activeTooltipNode.node.id)
          })
        : undefined,
    [activeTooltipNode, citations, edges, nodes, sources, visualStateById]
  );
  const tooltipTether = useMemo(() => {
    if (!activeTooltipNode || !activeTooltipPoint) return undefined;
    const anchor = tooltipAnchorForPoint(activeTooltipPoint, view.nodes);
    return buildGraphTetherPlan(
      { object: { kind: "node", id: activeTooltipNode.node.id, label: activeTooltipNode.node.label }, x: activeTooltipPoint.sx, y: activeTooltipPoint.sy, z: activeTooltipNode.z },
      { object: { kind: "graph", id: "tooltip", label: "Tooltip" }, x: anchor.x, y: anchor.y },
      tooltip?.statuses[0] ?? "related"
    );
  }, [activeTooltipNode, activeTooltipPoint, tooltip, view.nodes]);
  const tooltipAnchor = useMemo(
    () => (activeTooltipPoint ? tooltipAnchorForPoint(activeTooltipPoint, view.nodes) : undefined),
    [activeTooltipPoint, view.nodes]
  );

  useEffect(() => {
    if (use3d) setThreeActiveNodePosition(undefined);
  }, [use3d]);

  const handleWheel = (event: WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const cursor = svgPoint(event);
    const zoomFactor = event.deltaY < 0 ? 1.12 : 0.89;
    setCamera((current) => {
      const nextZoom = clamp(current.zoom * zoomFactor, 0.48, 3.4);
      const worldX = (cursor.x - current.panX) / current.zoom;
      const worldY = (cursor.y - current.panY) / current.zoom;
      return {
        ...current,
        zoom: nextZoom,
        panX: cursor.x - worldX * nextZoom,
        panY: cursor.y - worldY * nextZoom
      };
    });
  };

  const handlePointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if ((event.target as Element).closest(".graph-node-item")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { mode: use3d ? "orbit" : "pan", pointerId: event.pointerId, x: event.clientX, y: event.clientY };
  };

  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      if (!use3d) {
        const cursor = svgPoint(event);
        const worldX = (cursor.x - camera.panX) / camera.zoom;
        const worldY = (cursor.y - camera.panY) / camera.zoom;
        setHoveredObjectId(nearestViewNodeAt(view.nodes, worldX, worldY)?.node.id);
      }
      return;
    }
    const deltaX = event.clientX - drag.x;
    const deltaY = event.clientY - drag.y;
    dragRef.current = { ...drag, x: event.clientX, y: event.clientY };
    if (drag.mode === "orbit") {
      setCamera((current) => ({
        ...current,
        yaw: current.yaw + deltaX * 0.008,
        pitch: clamp(current.pitch - deltaY * 0.008, -1.18, 1.18)
      }));
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    setCamera((current) => ({
      ...current,
      panX: current.panX + deltaX * (VIEWBOX.width / Math.max(1, rect.width)),
      panY: current.panY + deltaY * (VIEWBOX.height / Math.max(1, rect.height))
    }));
  };

  const handlePointerUp = (event: PointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  };

  return (
    <div
      className={`graph-canvas-wrap graph-view-${layout} graph-view-${effectiveDimension} ${rendererAvailable === false ? "graph-webgl-fallback" : ""} ${use3d ? "can-orbit" : `${rendererAvailable === false ? "" : "has-sigma"} can-pan`}`}
      data-testid="graph-canvas-root"
      data-fit-sequence={fitSequence}
      data-graph-version={graphVersion}
      data-projection-level={projectionLevel}
      data-motion-tier={animationBudget.tier}
      data-renderer-kind={rendererMetrics?.kind ?? (use3d ? "three-3d" : "sigma-2d")}
      data-renderer-fps={rendererMetrics?.framesPerSecond?.toFixed(1)}
      data-renderer-context={rendererMetrics?.contextLost ? "lost" : "ready"}
      data-renderer-visible-nodes={rendererMetrics?.visibleNodes}
      data-renderer-visible-edges={rendererMetrics?.visibleEdges}
      role="region"
      aria-label="Interactive graph viewer"
      onPointerLeave={() => setHoveredObjectId(undefined)}
    >
      {use3d && (
        <Suspense fallback={<div className="three-graph-loading" role="status" aria-label="Preparing 3D graph" />}>
          <LazyThreeGraphScene
            nodes={rendererNodes}
            edges={rendererEdges}
            selectedNodeId={selectedNodeId}
            activeNodeId={activeTooltipNode?.node.id}
            fitSequence={fitSequence}
            reducedMotion={animationBudget.tier !== "full_motion"}
            onAvailabilityChange={setRendererAvailable}
            onHoverObject={setHoveredObjectId}
            onSelectNode={(nodeId) => onSelectNode?.(nodeId as ContentNode["id"])}
            onActiveNodePosition={setThreeActiveNodePosition}
            onRenderMetrics={setRendererMetrics}
          />
        </Suspense>
      )}
      {useSigma2d && (
        <SigmaGraphScene
          nodes={rendererNodes}
          edges={rendererEdges}
          selectedNodeId={selectedNodeId}
          activeNodeId={activeTooltipNode?.node.id}
          fitSequence={fitSequence}
          runForceLayout={layout === "force" && !hasPersistedPositions}
          reducedMotion={animationBudget.tier !== "full_motion"}
          onAvailabilityChange={setRendererAvailable}
          onHoverObject={setHoveredObjectId}
          onSelectNode={(nodeId) => onSelectNode?.(nodeId as ContentNode["id"])}
          onActiveNodePosition={setThreeActiveNodePosition}
          onRenderMetrics={setRendererMetrics}
          onViewportProjection={onViewportProjection}
        />
      )}
      <svg
        className={`graph-canvas ${use3d || useSigma2d ? "graph-canvas-overlay" : ""}`}
        data-testid="graph-canvas-surface"
        role="img"
        aria-label={`${view.nodes.length} rendered graph nodes and ${view.edges.length} rendered graph edges`}
        onPointerCancel={handlePointerUp}
        onPointerDown={use3d ? undefined : handlePointerDown}
        onPointerMove={use3d ? undefined : handlePointerMove}
        onPointerUp={handlePointerUp}
        onWheel={use3d ? undefined : handleWheel}
        viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`}
      >
        <defs>
          <filter id="node-glow" x="-70%" y="-70%" width="240%" height="240%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g className="graph-world" transform={worldTransform}>
          {rendererAvailable === false && layout === "arc" && <ArcRuler nodes={view.nodes} />}
          {rendererAvailable === false && layout === "radial" && !use3d && <RadialRings />}

          <g className="graph-edge-layer">
            {(rendererAvailable === false ? view.edges : []).map((viewEdge) => (
              <g
                className={[
                  "relationship",
                  viewEdge.edge.reviewStatus === "pending_review" ? "is-proposed" : "",
                  contentExpansionRole(viewEdge.edge) ? "is-content-edge" : "",
                  viewEdge.selected ? "is-selected" : "",
                  viewEdge.dimmed ? "is-muted" : "",
                  ...viewEdge.statuses.map((status) => `is-${status}`)
                ].join(" ")}
                key={viewEdge.edge.id}
              >
                <path className="graph-edge" d={viewEdge.path} />
                <path className="graph-edge-flow" d={viewEdge.path} />
                <title>{formatRelation(viewEdge.edge.relation)}</title>
              </g>
            ))}
          </g>
          <g className="graph-activity-layer" aria-hidden="true">
            {(rendererAvailable === false ? view.edges : [])
              .filter((viewEdge) =>
                viewEdge.statuses.some((status) =>
                  [
                    "scanning",
                    "cited",
                    "incoming",
                    "sensed",
                    "routed",
                    "assigned",
                    "sla_at_risk",
                    "action_proposed",
                    "action_running",
                    "outcome_waiting",
                    "outcome_succeeded",
                    "outcome_failed",
                    "feedback_applied",
                    "reopened"
                  ].includes(status)
                )
              )
              .map((viewEdge) => (
                <path
                  className={`graph-activity-path ${viewEdge.statuses.map((status) => `is-${status}`).join(" ")}`}
                  d={viewEdge.path}
                  key={`activity-${viewEdge.edge.id}`}
                />
              ))}
          </g>
          <g className="graph-candidate-layer" aria-hidden="true">
            {(rendererAvailable === false ? view.edges : [])
              .filter((viewEdge) => viewEdge.statuses.includes("candidate"))
              .map((viewEdge) => (
                <path className="graph-candidate-path" d={viewEdge.path} key={`candidate-${viewEdge.edge.id}`} />
              ))}
          </g>

          <g className="graph-node-layer">
            {(rendererAvailable === false ? view.nodes : []).map((viewNode) => {
              return (
                <g
                  aria-label={viewNode.node.label}
                  className={[
                    "graph-node-item",
                    `graph-kind-${viewNode.node.kind}`,
                    viewNode.contentRole ? "is-content-node" : "",
                    viewNode.contentRole ? `content-role-${viewNode.contentRole}` : "",
                    viewNode.selected ? "is-selected" : "",
                    viewNode.related ? "is-related" : "",
                    viewNode.matched ? "is-matched" : "",
                    viewNode.dimmed ? "is-muted" : "",
                    ...viewNode.statuses.map((status) => `is-${status}`)
                  ].join(" ")}
                  key={viewNode.node.id}
                  onClick={() => onSelectNode?.(viewNode.node.id)}
                  onFocus={() => {
                    setKeyboardFocusObjectId(viewNode.node.id);
                    setHoveredObjectId(viewNode.node.id);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectNode?.(viewNode.node.id);
                    }
                  }}
                  onBlur={() => setKeyboardFocusObjectId(undefined)}
                  onPointerEnter={() => setHoveredObjectId(viewNode.node.id)}
                  role="button"
                  tabIndex={0}
                  transform={`translate(${viewNode.sx.toFixed(1)} ${viewNode.sy.toFixed(1)}) scale(${viewNode.scale.toFixed(3)})`}
                >
                  <rect
                    className="graph-node-hitbox"
                    x={-(viewNode.radius + 12)}
                    y={-(viewNode.radius + 12)}
                    width={(viewNode.radius + 12) * 2}
                    height={(viewNode.radius + 12) * 2}
                    rx="10"
                  />
                  <circle className="graph-node-halo" r={viewNode.radius + 8} />
                  <circle className={`graph-node graph-node-${viewNode.kindIndex + 1}`} r={viewNode.radius} />
                  {viewNode.labelVisible && (
                    <text className="graph-node-label" x={viewNode.radius + 5} y="3">
                      {viewNode.label}
                    </text>
                  )}
                  <title>{viewNode.node.summary ? `${viewNode.node.label} - ${viewNode.node.summary}` : viewNode.node.label}</title>
                </g>
              );
            })}
          </g>
          {tooltipTether && (
            <g
              className={`graph-tooltip-tether is-${tooltipTether.status}`}
              data-testid="graph-tooltip-tether"
              aria-hidden="true"
            >
              <path d={tooltipTether.path} />
              <circle cx={tooltipTether.from.x} cy={tooltipTether.from.y} r="3.5" />
            </g>
          )}
        </g>
      </svg>

      {tooltip && tooltipTether && tooltipAnchor && (
        <GraphTooltipLayer
          tooltip={tooltip}
          left={(tooltipTether.to.x / VIEWBOX.width) * 100}
          top={(tooltipTether.to.y / VIEWBOX.height) * 100}
          placement={tooltipAnchor.placement}
        />
      )}

      <AccessibleGraphData
        nodes={view.nodes.map((item) => item.node)}
        edges={view.edges.map((item) => item.edge)}
        onSelectNode={onSelectNode}
      />

      {hasOmissions && (
        <div className="graph-render-budget" aria-label="Graph render budget">
          <strong>{renderBudget.nodes.length} shown</strong>
          <span>{serverOmittedNodeCount + renderBudget.omittedNodeCount} nodes hidden</span>
          <span>{serverOmittedEdgeCount + renderBudget.omittedEdgeCount + renderBudget.orphanEdgeCount} edges hidden</span>
          <small>Zoom or focus to load more.</small>
        </div>
      )}
    </div>
  );
}

function tooltipAnchorForPoint(point: TooltipSourcePoint, nodes: ViewNode[]): TooltipAnchor {
  const tooltipWidth = 276;
  const tooltipHeight = 178;
  const edgePadding = 18;
  const gap = Math.max(28, point.radius + 22);
  const candidates = [
    tooltipPlacementCandidate("right", point, tooltipWidth, tooltipHeight, gap, edgePadding),
    tooltipPlacementCandidate("left", point, tooltipWidth, tooltipHeight, gap, edgePadding),
    tooltipPlacementCandidate("top", point, tooltipWidth, tooltipHeight, gap, edgePadding),
    tooltipPlacementCandidate("bottom", point, tooltipWidth, tooltipHeight, gap, edgePadding)
  ];

  return candidates
    .map((candidate, index) => ({
      ...candidate,
      score: tooltipPlacementScore(candidate, point, nodes) + index * 0.8
    }))
    .sort((left, right) => left.score - right.score)[0];
}

function tooltipPlacementCandidate(
  placement: TooltipAnchor["placement"],
  point: TooltipSourcePoint,
  width: number,
  height: number,
  gap: number,
  edgePadding: number
): TooltipAnchor & { box: { left: number; top: number; right: number; bottom: number }; score: number } {
  let left = point.sx + gap + 8;
  let top = point.sy - height / 2;

  if (placement === "left") {
    left = point.sx - gap - width - 8;
    top = point.sy - height / 2;
  } else if (placement === "top") {
    left = point.sx - width / 2;
    top = point.sy - gap - height - 8;
  } else if (placement === "bottom") {
    left = point.sx - width / 2;
    top = point.sy + gap + 8;
  }

  left = clamp(left, edgePadding, VIEWBOX.width - width - edgePadding);
  top = clamp(top, edgePadding, VIEWBOX.height - height - edgePadding);

  let x = left - 8;
  let y = top + height / 2;
  if (placement === "left") {
    x = left + width + 8;
    y = top + height / 2;
  } else if (placement === "top") {
    x = left + width / 2;
    y = top + height + 8;
  } else if (placement === "bottom") {
    x = left + width / 2;
    y = top - 8;
  }

  return {
    x,
    y,
    placement,
    box: { left, top, right: left + width, bottom: top + height },
    score: 0
  };
}

function tooltipPlacementScore(
  candidate: TooltipAnchor & { box: { left: number; top: number; right: number; bottom: number } },
  point: TooltipSourcePoint,
  nodes: ViewNode[]
) {
  const box = candidate.box;
  let score = 0;
  for (const node of nodes) {
    const radius = Math.max(12, node.radius * node.scale + 8);
    const inside =
      node.sx + radius > box.left &&
      node.sx - radius < box.right &&
      node.sy + radius > box.top &&
      node.sy - radius < box.bottom;
    if (inside) score += node.node.id === point.nodeId ? 1200 : 420;
  }
  score += Math.abs(candidate.x - point.sx) * 0.08;
  score += Math.abs(candidate.y - point.sy) * 0.12;
  return score;
}

function buildNodeTooltip({
  viewNode,
  nodes,
  edges,
  sources,
  citations,
  visualState
}: {
  viewNode: ViewNode;
  nodes: ContentNode[];
  edges: GraphCanvasEdge[];
  sources: GraphCanvasSource[];
  citations: AgentCitation[];
  visualState?: GraphVisualState;
}) {
  const node = viewNode.node;
  const sourceId = sourceIdForNode(node);
  const source = sources.find((candidate) => candidate.id === sourceId);
  const relatedLabels = edges
    .filter((edge) => edge.sourceNodeId === node.id || edge.targetNodeId === node.id)
    .slice(0, 5)
    .flatMap((edge) => {
      const neighborId = edge.sourceNodeId === node.id ? edge.targetNodeId : edge.sourceNodeId;
      const neighbor = nodes.find((candidate) => candidate.id === neighborId);
      return neighbor ? [`${formatRelation(edge.relation)} ${neighbor.label}`] : [];
    });
  const nodeCitations = citations.filter((citation) => citation.nodeId === node.id || citation.sourceId === sourceId).slice(0, 4);
  const url = sourceUrl(source) ?? sourceUrlFromNode(node);
  return buildGraphTooltipModel({
    object: { kind: "node", id: node.id, label: node.label },
    title: node.label,
    kindLabel: nodeKindLabel(node.kind, viewNode.contentRole),
    summary: node.summary ?? source?.title,
    contains: relatedLabels,
    url,
    citations: nodeCitations,
    statuses: visualState?.statuses ?? viewNode.statuses,
    metadata: node.metadata ?? {}
  });
}

function graphActivityHints(activityEvents: GraphActivityEvent[], edges: GraphCanvasEdge[]) {
  const hints = {
    scanningIds: [] as string[],
    citedIds: [] as string[],
    incomingIds: [] as string[],
    candidateIds: [] as string[],
    readyIds: [] as string[],
    blockedIds: [] as string[],
    acceptedIds: [] as string[],
    rejectedIds: [] as string[],
    editedIds: [] as string[],
    deferredIds: [] as string[],
    staleIds: [] as string[],
    sensedIds: [] as string[],
    routedIds: [] as string[],
    assignedIds: [] as string[],
    slaAtRiskIds: [] as string[],
    actionProposedIds: [] as string[],
    actionRunningIds: [] as string[],
    outcomeWaitingIds: [] as string[],
    outcomeSucceededIds: [] as string[],
    outcomeFailedIds: [] as string[],
    feedbackAppliedIds: [] as string[],
    reopenedIds: [] as string[]
  };
  for (const edge of edges) {
    if (edge.reviewStatus === "pending_review") hints.candidateIds.push(edge.id);
  }
  for (const event of activityEvents) {
    const ids = [
      event.subject.id,
      ...event.nodeIds,
      ...event.edgeIds,
      ...event.sourceIds,
      ...event.sourceChunkIds,
      ...event.proposalIds
    ];
    if (event.kind === "agent_scan" || event.kind === "agent_tool_call" || event.kind === "research_started") {
      hints.scanningIds.push(...ids);
    }
    if (event.kind === "evidence_cited") hints.citedIds.push(...ids);
    if (event.kind === "source_incoming") hints.incomingIds.push(...ids);
    if (event.kind === "proposal_candidate") hints.candidateIds.push(...ids);
    if (event.kind === "review_ready") hints.readyIds.push(...ids);
    if (event.kind === "review_blocked") hints.blockedIds.push(...ids);
    if (event.kind === "review_accepted") hints.acceptedIds.push(...ids);
    if (event.kind === "review_rejected") hints.rejectedIds.push(...ids);
    if (event.kind === "review_edited") hints.editedIds.push(...ids);
    if (event.kind === "review_deferred") hints.deferredIds.push(...ids);
    if (event.kind === "knowledge_stale") hints.staleIds.push(...ids);
    if (event.kind === "signal_sensed") hints.sensedIds.push(...ids);
    if (event.kind === "observation_recorded" || event.kind === "alert_routed") hints.routedIds.push(...ids);
    if (event.kind === "attention_assigned") hints.assignedIds.push(...ids);
    if (event.kind === "decision_recorded") hints.readyIds.push(...ids);
    if (event.kind === "action_proposed") hints.actionProposedIds.push(...ids);
    if (event.kind === "action_approved" || event.kind === "action_running") hints.actionRunningIds.push(...ids);
    if (event.kind === "outcome_waiting") hints.outcomeWaitingIds.push(...ids);
    if (event.kind === "outcome_succeeded") hints.outcomeSucceededIds.push(...ids);
    if (event.kind === "outcome_failed") hints.outcomeFailedIds.push(...ids);
    if (event.kind === "feedback_applied") hints.feedbackAppliedIds.push(...ids);
    if (event.kind === "attention_reopened") hints.reopenedIds.push(...ids);
    if (event.status === "blocked" || event.status === "failed") hints.outcomeFailedIds.push(...ids);
  }
  return Object.fromEntries(Object.entries(hints).map(([key, ids]) => [key, [...new Set(ids)]]));
}

function ArcRuler({ nodes }: { nodes: ViewNode[] }) {
  const groups = NODE_KIND_ORDER.flatMap((kind) => {
    const items = nodes.filter((node) => node.node.kind === kind);
    if (items.length === 0) return [];
    const xs = items.map((node) => node.sx);
    return [{ kind, x1: Math.min(...xs), x2: Math.max(...xs) }];
  });

  return (
    <g className="arc-ruler" aria-hidden="true">
      <line x1="70" x2={VIEWBOX.width - 70} y1="430" y2="430" />
      {groups.map((group) => (
        <g key={group.kind}>
          <path d={`M ${group.x1 - 20} 462 L ${group.x1 - 20} 468 L ${group.x2 + 20} 468 L ${group.x2 + 20} 462`} />
          <text x={(group.x1 + group.x2) / 2} y="486" textAnchor="middle">
            {group.kind}
          </text>
        </g>
      ))}
    </g>
  );
}

function buildGraphView({
  nodes,
  edges,
  layout,
  dimension,
  showContents,
  query,
  selectedNodeId,
  camera,
  visualStateById
}: {
  nodes: ContentNode[];
  edges: SemanticEdge[];
  layout: GraphLayoutMode;
  dimension: GraphDimensionMode;
  showContents: boolean;
  query: string;
  selectedNodeId?: ContentNode["id"];
  camera: CameraState;
  visualStateById: Map<string, GraphVisualState>;
}): { nodes: ViewNode[]; edges: ViewEdge[] } {
  const validNodeIds = new Set(nodes.map((node) => node.id));
  const validEdges = edges.filter((edge) => validNodeIds.has(edge.sourceNodeId) && validNodeIds.has(edge.targetNodeId));
  const degreeByNodeId = new Map<ContentNode["id"], number>();
  for (const node of nodes) degreeByNodeId.set(node.id, 0);
  for (const edge of validEdges) {
    degreeByNodeId.set(edge.sourceNodeId, (degreeByNodeId.get(edge.sourceNodeId) ?? 0) + 1);
    degreeByNodeId.set(edge.targetNodeId, (degreeByNodeId.get(edge.targetNodeId) ?? 0) + 1);
  }

  const queryText = query.trim().toLowerCase();
  const matchedIds = new Set(
    queryText
      ? nodes.filter((node) => `${node.label} ${node.kind} ${node.summary ?? ""}`.toLowerCase().includes(queryText)).map((node) => node.id)
      : []
  );
  const relatedIds = new Set<ContentNode["id"]>();
  if (selectedNodeId) {
    relatedIds.add(selectedNodeId);
    for (const edge of validEdges) {
      if (edge.sourceNodeId === selectedNodeId) relatedIds.add(edge.targetNodeId);
      if (edge.targetNodeId === selectedNodeId) relatedIds.add(edge.sourceNodeId);
    }
  }

  const visibleNodes = selectVisibleNodes(nodes, showContents, matchedIds, relatedIds, selectedNodeId);
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const positions = computePositions(visibleNodes, validEdges.filter((edge) => visibleIds.has(edge.sourceNodeId) && visibleIds.has(edge.targetNodeId)), layout);
  const maxDegree = Math.max(1, ...visibleNodes.map((node) => degreeByNodeId.get(node.id) ?? 0));
  const use3d = dimension === "3d" && layout !== "arc";

  const viewNodes = visibleNodes.map((node, index) => {
    const point = positions.get(node.id) ?? {
      x: VIEWBOX.width / 2,
      y: VIEWBOX.height / 2,
      z: 0
    };
    const projected = use3d
      ? project3d(point.x, point.y, point.z, camera.yaw, camera.pitch)
      : { sx: point.x, sy: point.y, scale: 1, depth: 0 };
    const degree = degreeByNodeId.get(node.id) ?? 0;
    const kindIndex = kindIndexFor(node.kind);
    const contentRole = contentExpansionRole(node);
    const matched = matchedIds.has(node.id);
    const selected = node.id === selectedNodeId;
    const related = relatedIds.has(node.id);
    const statuses = visualStateById.get(node.id)?.statuses ?? [];
    const hasFocus = Boolean(selectedNodeId || queryText);
    const dimmed = statuses.includes("dimmed") || (hasFocus && !selected && !related && !matched);
    const dense = visibleNodes.length > 18;
    const baseRadius = use3d ? (dense ? 3.6 : 5.4) : (dense ? 4.2 : 6.4);
    const maxRadius = use3d ? (dense ? 7.2 : 11) : (dense ? 8.6 : 13);
    const degreeBoost = (degree / maxDegree) * (use3d ? 3.2 : 4.4);
    const rawRadius = clamp(
      baseRadius + degreeBoost + kindWeight(node.kind) * (use3d ? 0.18 : 0.28),
      baseRadius,
      maxRadius
    );
    const radius = contentRole ? Math.max(baseRadius * 0.62, rawRadius * 0.68) : rawRadius;
    const label = truncateLabel(node.label, use3d ? 24 : dense ? 24 : 36);
    const compact3dLabels = use3d;
    const priorityLabelLimit = compact3dLabels ? 5 : dense ? 8 : 10;
    const kindLabel = !compact3dLabels && kindWeight(node.kind) >= 5.4;
    const labelVisible =
      Boolean(contentRole && showContents) ||
      showContents ||
      selected ||
      matched ||
      related ||
      kindLabel ||
      index < priorityLabelLimit;

    return {
      node,
      x: point.x,
      y: point.y,
      z: point.z,
      sx: projected.sx,
      sy: projected.sy,
      scale: projected.scale,
      depth: projected.depth,
      radius,
      degree,
      label,
      truncated: label !== node.label,
      matched,
      selected,
      related,
      dimmed,
      labelVisible,
      kindIndex,
      statuses,
      contentRole
    };
  });
  const nodeById = new Map(viewNodes.map((node) => [node.node.id, node]));
  const viewEdges = validEdges
    .flatMap((edge) => {
      const source = nodeById.get(edge.sourceNodeId);
      const target = nodeById.get(edge.targetNodeId);
      if (!source || !target) return [];
      const selected = Boolean(selectedNodeId && (edge.sourceNodeId === selectedNodeId || edge.targetNodeId === selectedNodeId));
      const statuses = visualStateById.get(edge.id)?.statuses ?? [];
      const dimmed = statuses.includes("dimmed") || Boolean((selectedNodeId || queryText) && !selected && !source.matched && !target.matched);
      const pathInfo = edgePath(source, target, edge, layout);
      return [{ edge, source, target, selected, dimmed, statuses, ...pathInfo }];
    })
    .sort((left, right) => left.source.depth + left.target.depth - (right.source.depth + right.target.depth));

  return { nodes: viewNodes.sort((left, right) => right.depth - left.depth), edges: viewEdges };
}

function selectVisibleNodes(
  nodes: ContentNode[],
  showContents: boolean,
  matchedIds: Set<ContentNode["id"]>,
  relatedIds: Set<ContentNode["id"]>,
  selectedNodeId?: ContentNode["id"]
) {
  const mustKeep = new Set<ContentNode["id"]>([...matchedIds, ...relatedIds]);
  if (selectedNodeId) mustKeep.add(selectedNodeId);
  if (showContents) return nodes;
  return nodes.filter((node) => !contentExpansionRole(node) || mustKeep.has(node.id));
}

function contentExpansionRole(entity: ContentNode | SemanticEdge): string | undefined {
  const metadata = entity.metadata as { contentExpansion?: { role?: unknown } } | undefined;
  const role = metadata?.contentExpansion?.role;
  return typeof role === "string" ? role : undefined;
}

function computePositions(nodes: ContentNode[], edges: SemanticEdge[], layout: GraphLayoutMode) {
  const projected = projectedGraphPositions(nodes, VIEWBOX.width, VIEWBOX.height);
  if (projected) return projected;
  if (layout === "radial") return radialPositions(nodes, edges);
  if (layout === "arc") return arcPositions(nodes);
  return forcePositions(nodes, edges);
}

function forcePositions(nodes: ContentNode[], edges: SemanticEdge[]) {
  const points = new Map<ContentNode["id"], { x: number; y: number; z: number; vx: number; vy: number; vz: number }>();
  const centerX = VIEWBOX.width / 2;
  const centerY = VIEWBOX.height / 2;
  nodes.forEach((node, index) => {
    const seed = hashString(node.id);
    const angle = ((index / Math.max(1, nodes.length)) * Math.PI * 2 + (seed % 90) / 90) - Math.PI / 2;
    const ring = 130 + (seed % 120);
    points.set(node.id, {
      x: centerX + Math.cos(angle) * ring,
      y: centerY + Math.sin(angle) * ring * 0.72,
      z: ((seed % 220) - 110) * 0.8,
      vx: 0,
      vy: 0,
      vz: 0
    });
  });

  // Large unsaved graphs receive deterministic seeds and move immediately to the
  // ForceAtlas2 worker. The quadratic refinement below is reserved for small graphs.
  if (nodes.length > 400) return stripVelocity(points);

  for (let tick = 0; tick < 82; tick += 1) {
    const alpha = 1 - tick / 90;
    for (let left = 0; left < nodes.length; left += 1) {
      const a = points.get(nodes[left].id);
      if (!a) continue;
      for (let right = left + 1; right < nodes.length; right += 1) {
        const b = points.get(nodes[right].id);
        if (!b) continue;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dz = a.z - b.z;
        const distanceSquared = Math.max(64, dx * dx + dy * dy + dz * dz * 0.25);
        const force = (1700 / distanceSquared) * alpha;
        const distance = Math.sqrt(distanceSquared);
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        const fz = (dz / distance) * force * 0.35;
        a.vx += fx;
        a.vy += fy;
        a.vz += fz;
        b.vx -= fx;
        b.vy -= fy;
        b.vz -= fz;
      }
    }

    for (const edge of edges) {
      const source = points.get(edge.sourceNodeId);
      const target = points.get(edge.targetNodeId);
      if (!source || !target) continue;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dz = target.z - source.z;
      const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy + dz * dz * 0.3));
      const spring = (distance - 185) * 0.012 * alpha;
      const fx = (dx / distance) * spring;
      const fy = (dy / distance) * spring;
      const fz = (dz / distance) * spring * 0.4;
      source.vx += fx;
      source.vy += fy;
      source.vz += fz;
      target.vx -= fx;
      target.vy -= fy;
      target.vz -= fz;
    }

    for (const point of points.values()) {
      point.vx += (centerX - point.x) * 0.004 * alpha;
      point.vy += (centerY - point.y) * 0.004 * alpha;
      point.vz += (0 - point.z) * 0.002 * alpha;
      point.vx *= 0.82;
      point.vy *= 0.82;
      point.vz *= 0.82;
      point.x = clamp(point.x + point.vx, 92, VIEWBOX.width - 92);
      point.y = clamp(point.y + point.vy, 86, VIEWBOX.height - 96);
      point.z = clamp(point.z + point.vz, -190, 190);
    }
  }

  return stripVelocity(points);
}

function radialPositions(nodes: ContentNode[], edges: SemanticEdge[]) {
  const points = new Map<ContentNode["id"], { x: number; y: number; z: number }>();
  const centerX = VIEWBOX.width / 2;
  const centerY = VIEWBOX.height / 2;
  if (nodes.length === 0) return points;
  if (nodes.length === 1) {
    points.set(nodes[0].id, { x: centerX, y: centerY, z: 0 });
    return points;
  }

  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const adjacency = new Map<ContentNode["id"], Set<ContentNode["id"]>>();
  const degreeByNodeId = new Map<ContentNode["id"], number>();
  for (const node of nodes) {
    adjacency.set(node.id, new Set());
    degreeByNodeId.set(node.id, 0);
  }

  for (const edge of edges) {
    if (!nodeById.has(edge.sourceNodeId) || !nodeById.has(edge.targetNodeId)) continue;
    adjacency.get(edge.sourceNodeId)?.add(edge.targetNodeId);
    adjacency.get(edge.targetNodeId)?.add(edge.sourceNodeId);
    degreeByNodeId.set(edge.sourceNodeId, (degreeByNodeId.get(edge.sourceNodeId) ?? 0) + 1);
    degreeByNodeId.set(edge.targetNodeId, (degreeByNodeId.get(edge.targetNodeId) ?? 0) + 1);
  }

  const connectedEdges = edges.filter((edge) => nodeById.has(edge.sourceNodeId) && nodeById.has(edge.targetNodeId));
  if (connectedEdges.length === 0) return radialFallbackPositions(nodes);

  const compareNodes = (left: ContentNode, right: ContentNode) => {
    const degreeDelta = (degreeByNodeId.get(right.id) ?? 0) - (degreeByNodeId.get(left.id) ?? 0);
    if (degreeDelta !== 0) return degreeDelta;
    const kindDelta = kindWeight(right.kind) - kindWeight(left.kind);
    if (kindDelta !== 0) return kindDelta;
    return left.label.localeCompare(right.label) || left.id.localeCompare(right.id);
  };
  const compareNodeIds = (leftId: ContentNode["id"], rightId: ContentNode["id"]) => {
    const left = nodeById.get(leftId);
    const right = nodeById.get(rightId);
    if (!left || !right) return leftId.localeCompare(rightId);
    return compareNodes(left, right);
  };

  const root = [...nodes].sort(compareNodes)[0];
  const depthByNodeId = new Map<ContentNode["id"], number>([[root.id, 0]]);
  const parentByNodeId = new Map<ContentNode["id"], ContentNode["id"]>();
  const childrenByParentId = new Map<ContentNode["id"], ContentNode["id"][]>();
  const queue = [root.id];

  for (let index = 0; index < queue.length; index += 1) {
    const nodeId = queue[index];
    const nextDepth = (depthByNodeId.get(nodeId) ?? 0) + 1;
    const neighbors = [...(adjacency.get(nodeId) ?? [])].sort(compareNodeIds);
    for (const neighborId of neighbors) {
      if (depthByNodeId.has(neighborId)) continue;
      depthByNodeId.set(neighborId, nextDepth);
      parentByNodeId.set(neighborId, nodeId);
      childrenByParentId.set(nodeId, [...(childrenByParentId.get(nodeId) ?? []), neighborId]);
      queue.push(neighborId);
    }
  }

  const angleByNodeId = new Map<ContentNode["id"], number>([[root.id, -Math.PI / 2]]);
  const rootChildren = [...(childrenByParentId.get(root.id) ?? [])].sort(compareNodeIds);
  rootChildren.forEach((childId, index) => {
    const angle = rootChildren.length === 1 ? -Math.PI / 2 : -Math.PI / 2 + (Math.PI * 2 * index) / rootChildren.length;
    angleByNodeId.set(childId, angle);
  });

  const maxDepth = Math.max(1, ...[...depthByNodeId.values()]);
  for (let depth = 2; depth <= maxDepth; depth += 1) {
    const parents = [...childrenByParentId.keys()]
      .filter((parentId) => (depthByNodeId.get(parentId) ?? 0) === depth - 1)
      .sort((leftId, rightId) => (angleByNodeId.get(leftId) ?? 0) - (angleByNodeId.get(rightId) ?? 0));

    for (const parentId of parents) {
      const children = [...(childrenByParentId.get(parentId) ?? [])].sort(compareNodeIds);
      const parentAngle = angleByNodeId.get(parentId) ?? angleForNode(parentId);
      const spread = clamp(0.28 + children.length * 0.13, 0.34, 1.08);
      children.forEach((childId, index) => {
        const offset = children.length === 1 ? 0 : (index / (children.length - 1) - 0.5) * spread;
        angleByNodeId.set(childId, parentAngle + offset);
      });
    }
  }

  points.set(root.id, { x: centerX, y: centerY, z: 0 });
  for (const nodeId of queue.slice(1)) {
    const nodeDepth = depthByNodeId.get(nodeId) ?? 1;
    const angle = angleByNodeId.get(nodeId) ?? angleForNode(nodeId);
    const ring = radialRingRadius(nodeDepth, maxDepth, nodes.length) + radialJitter(nodeId, 12);
    points.set(nodeId, radialPoint(centerX, centerY, angle, ring, nodeDepth));
  }

  const unvisitedIds = nodes.map((node) => node.id).filter((nodeId) => !points.has(nodeId));
  const disconnectedComponents = disconnectedRadialComponents(unvisitedIds, adjacency, compareNodeIds);
  disconnectedComponents.forEach((component, componentIndex) => {
    const baseAngle = -Math.PI / 2 + (Math.PI * 2 * (componentIndex + 0.5)) / disconnectedComponents.length;
    const componentRoot = component[0];
    const componentRing = 282 + radialJitter(componentRoot, 18);
    points.set(componentRoot, radialPoint(centerX, centerY, baseAngle, componentRing, 2));

    const members = component.slice(1);
    members.forEach((nodeId, index) => {
      const spread = clamp(0.34 + members.length * 0.1, 0.42, 1.18);
      const offset = members.length === 1 ? 0 : (index / (members.length - 1) - 0.5) * spread;
      const ring = 324 + (index % 2) * 22 + radialJitter(nodeId, 10);
      points.set(nodeId, radialPoint(centerX, centerY, baseAngle + offset, ring, 3));
    });
  });

  return points;
}

function RadialRings() {
  return (
    <g className="radial-rings" aria-hidden="true">
      <circle cx={VIEWBOX.width / 2} cy={VIEWBOX.height / 2} r="126" />
      <circle cx={VIEWBOX.width / 2} cy={VIEWBOX.height / 2} r="224" />
      <circle cx={VIEWBOX.width / 2} cy={VIEWBOX.height / 2} r="314" />
    </g>
  );
}

function radialFallbackPositions(nodes: ContentNode[]) {
  const points = new Map<ContentNode["id"], { x: number; y: number; z: number }>();
  const centerX = VIEWBOX.width / 2;
  const centerY = VIEWBOX.height / 2;
  const sortedNodes = [...nodes].sort((left, right) => {
    const kindDelta = kindIndexFor(left.kind) - kindIndexFor(right.kind);
    if (kindDelta !== 0) return kindDelta;
    return left.label.localeCompare(right.label) || left.id.localeCompare(right.id);
  });

  sortedNodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / sortedNodes.length;
    const ring = isPrimaryNodeKind(node.kind) ? 146 : 266;
    points.set(node.id, radialPoint(centerX, centerY, angle, ring + radialJitter(node.id, 24), 1));
  });

  return points;
}

function disconnectedRadialComponents(
  nodeIds: ContentNode["id"][],
  adjacency: Map<ContentNode["id"], Set<ContentNode["id"]>>,
  compareNodeIds: (leftId: ContentNode["id"], rightId: ContentNode["id"]) => number
) {
  const remaining = new Set(nodeIds);
  const components: ContentNode["id"][][] = [];

  while (remaining.size > 0) {
    const start = [...remaining].sort(compareNodeIds)[0];
    const component: ContentNode["id"][] = [];
    const queue = [start];
    remaining.delete(start);

    for (let index = 0; index < queue.length; index += 1) {
      const nodeId = queue[index];
      component.push(nodeId);
      const neighbors = [...(adjacency.get(nodeId) ?? [])].filter((neighborId) => remaining.has(neighborId)).sort(compareNodeIds);
      for (const neighborId of neighbors) {
        remaining.delete(neighborId);
        queue.push(neighborId);
      }
    }

    components.push(component.sort(compareNodeIds));
  }

  return components.sort((left, right) => right.length - left.length || compareNodeIds(left[0], right[0]));
}

function radialRingRadius(depth: number, maxDepth: number, nodeCount: number) {
  const innerRadius = nodeCount > 44 ? 112 : 128;
  const outerRadius = nodeCount > 84 ? 328 : nodeCount > 44 ? 318 : 306;
  if (maxDepth <= 1) return Math.min(outerRadius, 218);
  const visibleRingCount = Math.min(4, Math.max(2, maxDepth));
  const ringStep = (outerRadius - innerRadius) / Math.max(1, visibleRingCount - 1);
  const clampedDepth = Math.min(depth, visibleRingCount);
  return Math.min(outerRadius, innerRadius + (clampedDepth - 1) * ringStep + Math.max(0, depth - visibleRingCount) * 16);
}

function radialPoint(centerX: number, centerY: number, angle: number, ring: number, depth: number) {
  return {
    x: centerX + Math.cos(angle) * ring,
    y: centerY + Math.sin(angle) * ring * 0.76,
    z: Math.sin(angle) * 148 + (depth - 1) * 34
  };
}

function radialJitter(nodeId: ContentNode["id"], amount: number) {
  return ((hashString(`${nodeId}:radial`) % 1000) / 1000 - 0.5) * amount;
}

function angleForNode(nodeId: ContentNode["id"]) {
  return -Math.PI + ((hashString(`${nodeId}:angle`) % 3600) / 3600) * Math.PI * 2;
}

function arcPositions(nodes: ContentNode[]) {
  const points = new Map<ContentNode["id"], { x: number; y: number; z: number }>();
  const groups = NODE_KIND_ORDER.flatMap((kind) => {
    const members = nodes.filter((node) => node.kind === kind);
    return members.length > 0 ? [{ kind, members }] : [];
  });
  const margin = 82;
  const groupGap = 34;
  const itemCount = Math.max(1, nodes.length - 1);
  const step = (VIEWBOX.width - margin * 2 - Math.max(0, groups.length - 1) * groupGap) / itemCount;
  let x = margin;
  groups.forEach((group) => {
    group.members.forEach((node) => {
      points.set(node.id, { x, y: 430, z: 0 });
      x += step;
    });
    x += groupGap;
  });
  return points;
}

function stripVelocity(
  points: Map<ContentNode["id"], { x: number; y: number; z: number; vx: number; vy: number; vz: number }>
) {
  return new Map([...points].map(([id, point]) => [id, { x: point.x, y: point.y, z: point.z }]));
}

function project3d(pointX: number, pointY: number, pointZ: number, yaw: number, pitch: number) {
  const ox = pointX - VIEWBOX.width / 2;
  const oy = pointY - VIEWBOX.height / 2;
  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const cosPitch = Math.cos(pitch);
  const sinPitch = Math.sin(pitch);
  const x = ox * cosYaw - pointZ * sinYaw;
  const z = ox * sinYaw + pointZ * cosYaw;
  const y = oy * cosPitch - z * sinPitch;
  const depth = oy * sinPitch + z * cosPitch;
  const perspective = clamp(620 / (620 + depth), 0.56, 1.52);
  return {
    sx: VIEWBOX.width / 2 + x * perspective,
    sy: VIEWBOX.height / 2 + y * perspective,
    scale: perspective,
    depth
  };
}

function svgPoint(event: WheelEvent<SVGSVGElement> | PointerEvent<SVGSVGElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / Math.max(1, rect.width)) * VIEWBOX.width,
    y: ((event.clientY - rect.top) / Math.max(1, rect.height)) * VIEWBOX.height
  };
}

function nearestViewNodeAt(nodes: ViewNode[], x: number, y: number) {
  let nearest: ViewNode | undefined;
  let nearestScore = Number.POSITIVE_INFINITY;
  for (const node of nodes) {
    const dx = x - node.sx;
    const dy = y - node.sy;
    const distance = Math.sqrt(dx * dx + dy * dy);
    const threshold = Math.max(13, node.radius * node.scale + 10);
    if (distance > threshold) continue;
    const score = distance - node.radius * node.scale;
    if (score < nearestScore) {
      nearest = node;
      nearestScore = score;
    }
  }
  return nearest;
}

function edgePath(source: ViewNode, target: ViewNode, edge: SemanticEdge, layout: GraphLayoutMode) {
  const endpoints = edgeEndpoints(source, target);
  if (layout === "arc") {
    const dx = Math.abs(endpoints.targetX - endpoints.sourceX);
    const lift = Math.max(44, Math.min(260, dx * 0.38 + 26 + (hashString(edge.id) % 34)));
    const midX = (endpoints.sourceX + endpoints.targetX) / 2;
    const labelY = Math.min(endpoints.sourceY, endpoints.targetY) - lift + 14;
    return {
      path: `M ${endpoints.sourceX.toFixed(1)} ${endpoints.sourceY.toFixed(1)} Q ${midX.toFixed(1)} ${labelY.toFixed(1)} ${endpoints.targetX.toFixed(1)} ${endpoints.targetY.toFixed(1)}`,
      labelX: midX,
      labelY
    };
  }
  if (layout === "radial") {
    const midX = (endpoints.sourceX + endpoints.targetX) / 2;
    const midY = (endpoints.sourceY + endpoints.targetY) / 2;
    return {
      path: `M ${endpoints.sourceX.toFixed(1)} ${endpoints.sourceY.toFixed(1)} L ${endpoints.targetX.toFixed(1)} ${endpoints.targetY.toFixed(1)}`,
      labelX: midX,
      labelY: midY
    };
  }

  const midX = (endpoints.sourceX + endpoints.targetX) / 2;
  const midY = (endpoints.sourceY + endpoints.targetY) / 2;
  const dx = endpoints.targetX - endpoints.sourceX;
  const dy = endpoints.targetY - endpoints.sourceY;
  const length = Math.max(1, Math.sqrt(dx * dx + dy * dy));
  const curve = ((hashString(edge.id) % 2 === 0 ? 1 : -1) * Math.min(42, length * 0.12)) / 1.6;
  const cx = midX + (-dy / length) * curve;
  const cy = midY + (dx / length) * curve;
  return {
    path: `M ${endpoints.sourceX.toFixed(1)} ${endpoints.sourceY.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${endpoints.targetX.toFixed(1)} ${endpoints.targetY.toFixed(1)}`,
    labelX: cx,
    labelY: cy - 8
  };
}

function edgeEndpoints(source: ViewNode, target: ViewNode) {
  const dx = target.sx - source.sx;
  const dy = target.sy - source.sy;
  const length = Math.max(1, Math.sqrt(dx * dx + dy * dy));
  const ux = dx / length;
  const uy = dy / length;
  const sourceRadius = Math.min(source.radius * source.scale + 8, length * 0.38);
  const targetRadius = Math.min(target.radius * target.scale + 11, length * 0.38);
  return {
    sourceX: source.sx + ux * sourceRadius,
    sourceY: source.sy + uy * sourceRadius,
    targetX: target.sx - ux * targetRadius,
    targetY: target.sy - uy * targetRadius
  };
}

function splitLabel(label: string, maxLines: number, maxLineLength: number): string[] {
  const words = label.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [label];

  const lines: string[] = [];
  for (const word of words) {
    const current = lines.at(-1);
    if (!current || current.length + word.length + 1 > maxLineLength) {
      if (lines.length < maxLines) lines.push(word);
      continue;
    }
    lines[lines.length - 1] = `${current} ${word}`;
  }
  return lines.length > 0 ? lines : [label];
}

function truncateLabel(label: string, maxLength: number) {
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 1).trimEnd()}...`;
}

function sourceIdForNode(node: ContentNode) {
  const metadata = node.metadata as { sourceId?: unknown; contentExpansion?: { stableId?: unknown } } | undefined;
  if (typeof metadata?.sourceId === "string") return metadata.sourceId;
  if (node.provenance[0]?.sourceId) return node.provenance[0].sourceId;
  if (node.kind === "source" && typeof metadata?.contentExpansion?.stableId === "string") return metadata.contentExpansion.stableId;
  return undefined;
}

function sourceUrl(source: GraphCanvasSource | undefined) {
  const url = source?.remoteUrl ?? source?.remote_url ?? source?.uri;
  return typeof url === "string" && /^https?:\/\//i.test(url) ? url : undefined;
}

function sourceUrlFromNode(node: ContentNode) {
  const metadata = node.metadata as { url?: unknown; uri?: unknown; remoteUrl?: unknown } | undefined;
  const candidate = metadata?.url ?? metadata?.remoteUrl ?? metadata?.uri ?? (node.kind === "url" ? node.provenance[0]?.sourceUri : undefined);
  return typeof candidate === "string" && /^https?:\/\//i.test(candidate) ? candidate : undefined;
}

function nodeKindLabel(kind: ContentNode["kind"], contentRole?: string) {
  if (contentRole) return `${contentRole} ${kind}`.replaceAll("_", " ");
  return kind.replaceAll("_", " ");
}

function formatRelation(relation: SemanticEdge["relation"]) {
  return relation.replaceAll("_", " ");
}

function kindIndexFor(kind: ContentNode["kind"]) {
  return NODE_KIND_INDEX.get(kind) ?? 0;
}

function isPrimaryNodeKind(kind: ContentNode["kind"]) {
  return [
    "concept",
    "topic",
    "system",
    "component",
    "service",
    "api",
    "repository",
    "workflow",
    "process",
    "decision",
    "product",
    "feature"
  ].includes(kind);
}

function kindWeight(kind: ContentNode["kind"]) {
  if (["system", "repository", "product"].includes(kind)) return 6;
  if (["topic", "component", "service", "api", "feature", "workflow", "process", "decision"].includes(kind)) return 5.5;
  if (["concept", "requirement", "risk", "metric", "event"].includes(kind)) return 5;
  if (["team", "organization", "person"].includes(kind)) return 4;
  if (["document", "source", "dataset", "module", "package", "file", "symbol", "task"].includes(kind)) return 2;
  return 1;
}

function hashString(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
