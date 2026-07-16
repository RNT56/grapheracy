import type { GraphVisualStatus } from "@graphview/shared-types";

export interface GraphRendererNode {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
  z: number;
  radius: number;
  statuses: GraphVisualStatus[];
}

export interface GraphRendererEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  relation: string;
  statuses: GraphVisualStatus[];
}

export interface GraphRendererActiveNodePosition {
  nodeId: string;
  x: number;
  y: number;
  visible: boolean;
}

export interface GraphRendererRuntimeMetrics {
  kind: "sigma-2d" | "three-3d";
  visibleNodes: number;
  visibleEdges: number;
  framesPerSecond?: number;
  contextLost: boolean;
}

export interface GraphRendererSceneProps {
  nodes: GraphRendererNode[];
  edges: GraphRendererEdge[];
  selectedNodeId?: string;
  activeNodeId?: string;
  fitSequence: number;
  reducedMotion: boolean;
  onAvailabilityChange: (available: boolean) => void;
  onHoverObject: (objectId?: string) => void;
  onSelectNode: (nodeId: string) => void;
  onActiveNodePosition: (position?: GraphRendererActiveNodePosition) => void;
  onRenderMetrics: (metrics: GraphRendererRuntimeMetrics) => void;
}

export function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(window.WebGLRenderingContext && (canvas.getContext("webgl2") || canvas.getContext("webgl")));
  } catch {
    return false;
  }
}
