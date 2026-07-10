import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { GraphVisualStatus } from "@graphview/shared-types";
import { supportsWebGL } from "./graphRendererContract";
import type {
  GraphRendererActiveNodePosition,
  GraphRendererEdge,
  GraphRendererNode,
  GraphRendererSceneProps
} from "./graphRendererContract";

type Props = GraphRendererSceneProps;

interface ThreeGraphHandlers {
  activeNodeId?: string;
  selectedNodeId?: string;
  onActiveNodePosition: (position?: GraphRendererActiveNodePosition) => void;
  onHoverObject: (objectId?: string) => void;
  onSelectNode: (nodeId: string) => void;
  onRenderMetrics: GraphRendererSceneProps["onRenderMetrics"];
  visualSignature: string;
  currentNodes: Map<string, GraphRendererNode>;
  currentEdges: Map<string, GraphRendererEdge>;
}

const NODE_COLORS: Record<string, number> = {
  api: 0xb6d3ff,
  component: 0x8fe2ce,
  concept: 0x8ee3d1,
  decision: 0xf2cf7b,
  document: 0xc6d6ef,
  feature: 0x9fe7bd,
  repository: 0xc6b8ff,
  source: 0xdce4ee,
  system: 0x9ab8ff,
  task: 0x9fe7bd,
  topic: 0x67d5a5,
  url: 0x8fe2ce
};

export function ThreeGraphScene({
  nodes,
  edges,
  selectedNodeId,
  activeNodeId,
  fitSequence,
  reducedMotion,
  onAvailabilityChange,
  onHoverObject,
  onSelectNode,
  onActiveNodePosition,
  onRenderMetrics
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const orbitRef = useRef({ yaw: -0.36, pitch: 0.36 });
  const fitSequenceRef = useRef(fitSequence);
  if (fitSequenceRef.current !== fitSequence) {
    fitSequenceRef.current = fitSequence;
    orbitRef.current = { yaw: -0.36, pitch: 0.36 };
  }
  const [rendererUnavailable, setRendererUnavailable] = useState(false);
  const [contextLost, setContextLost] = useState(false);
  const graphSignature = useMemo(() => sceneSignature(nodes, edges), [edges, nodes]);
  const visualSignature = useMemo(() => sceneVisualSignature(nodes, edges), [edges, nodes]);
  const currentNodes = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const currentEdges = useMemo(() => new Map(edges.map((edge) => [edge.id, edge])), [edges]);
  const handlersRef = useRef<ThreeGraphHandlers>({
    activeNodeId,
    selectedNodeId,
    onActiveNodePosition,
    onHoverObject,
    onSelectNode,
    onRenderMetrics,
    visualSignature,
    currentNodes,
    currentEdges
  });
  handlersRef.current = {
    activeNodeId,
    selectedNodeId,
    onActiveNodePosition,
    onHoverObject,
    onSelectNode,
    onRenderMetrics,
    visualSignature,
    currentNodes,
    currentEdges
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setRendererUnavailable(false);

    if (!supportsWebGL()) {
      setRendererUnavailable(true);
      onAvailabilityChange(false);
      handlersRef.current.onRenderMetrics({
        kind: "three-3d",
        visibleNodes: nodes.length,
        visibleEdges: edges.length,
        contextLost: true
      });
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x080a0e);
    const camera = new THREE.PerspectiveCamera(48, 1, 1, 3200);
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    } catch {
      setRendererUnavailable(true);
      onAvailabilityChange(false);
      handlersRef.current.onRenderMetrics({
        kind: "three-3d",
        visibleNodes: nodes.length,
        visibleEdges: edges.length,
        contextLost: true
      });
      return;
    }
    onAvailabilityChange(true);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x080a0e, 1);
    renderer.domElement.className = "three-graph-canvas";
    container.appendChild(renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 1.25);
    scene.add(ambient);
    const key = new THREE.DirectionalLight(0xb6d3ff, 1.4);
    key.position.set(180, -220, 360);
    scene.add(key);

    const root = new THREE.Group();
    scene.add(root);
    const nodeObjects: THREE.Mesh[] = [];
    const semanticNodeObjects: THREE.Mesh[] = [];
    const semanticEdgeMaterials: THREE.LineBasicMaterial[] = [];
    const nodeObjectById = new Map<string, THREE.Mesh>();
    const edgeMaterialById = new Map<string, THREE.LineBasicMaterial>();
    const nodePositions = new Map<string, THREE.Vector3>();

    const normalizeX = (value: number) => value - 450;
    const normalizeY = (value: number) => 320 - value;

    for (const node of nodes) {
      const position = new THREE.Vector3(normalizeX(node.x), normalizeY(node.y), node.z * 1.1);
      nodePositions.set(node.id, position);
      const sphere = new THREE.SphereGeometry(Math.max(4.5, node.radius * 1.25), 22, 16);
      const color = colorForNode(node);
      const material = new THREE.MeshStandardMaterial({
        color,
        emissive: new THREE.Color(color).multiplyScalar(statusBoost(node.statuses)),
        metalness: 0.18,
        roughness: 0.42,
        transparent: true,
        opacity: node.statuses.includes("dimmed") ? 0.26 : 0.96
      });
      const mesh = new THREE.Mesh(sphere, material);
      mesh.position.copy(position);
      mesh.userData = { id: node.id };
      const baseScale = node.id === selectedNodeId || node.statuses.includes("focus") ? 1.32 : 1;
      mesh.scale.setScalar(baseScale);
      mesh.userData.baseScale = baseScale;
      if (node.statuses.some((status) => ["scanning", "incoming", "action_running", "outcome_waiting"].includes(status))) {
        semanticNodeObjects.push(mesh);
      }
      root.add(mesh);
      nodeObjects.push(mesh);
      nodeObjectById.set(node.id, mesh);
    }

    for (const edge of edges) {
      const source = nodePositions.get(edge.sourceNodeId);
      const target = nodePositions.get(edge.targetNodeId);
      if (!source || !target) continue;
      const geometry = new THREE.BufferGeometry().setFromPoints([source, target]);
      const material = new THREE.LineBasicMaterial({
        color: colorForEdge(edge),
        transparent: true,
        opacity: opacityForEdge(edge)
      });
      if (edge.statuses.some((status) => ["scanning", "cited", "action_running"].includes(status))) {
        semanticEdgeMaterials.push(material);
      }
      edgeMaterialById.set(edge.id, material);
      root.add(new THREE.Line(geometry, material));
    }

    const bounds = new THREE.Box3().setFromObject(root);
    const size = bounds.getSize(new THREE.Vector3());
    const maxSceneSize = Math.max(size.x, size.y, size.z, 1);
    const distance = clampNumber(
      maxSceneSize / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) + maxSceneSize * 0.55,
      720,
      1800
    );
    camera.position.set(0, 0, distance);
    camera.near = Math.max(0.1, distance / 1000);
    camera.far = distance + 2600;
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let width = 1;
    let height = 1;
    let { yaw, pitch } = orbitRef.current;
    let dragStart: { x: number; y: number } | undefined;
    let frame = 0;
    let lastActivePositionKey = "";
    let lastSelectedNodeId = selectedNodeId;
    let appliedVisualSignature = visualSignature;
    let metricWindowStartedAt = performance.now();
    let metricFrameCount = 0;

    const resize = () => {
      const rect = container.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };

    const updatePointer = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1;
      pointer.y = -(((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 - 1);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (dragStart) {
        const deltaX = event.clientX - dragStart.x;
        const deltaY = event.clientY - dragStart.y;
        dragStart = { x: event.clientX, y: event.clientY };
        yaw += deltaX * 0.006;
        pitch = Math.max(-0.9, Math.min(0.9, pitch + deltaY * 0.004));
        orbitRef.current = { yaw, pitch };
        return;
      }
      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(nodeObjects, false)[0];
      handlersRef.current.onHoverObject?.(typeof hit?.object.userData.id === "string" ? hit.object.userData.id : undefined);
    };

    const handlePointerDown = (event: PointerEvent) => {
      dragStart = { x: event.clientX, y: event.clientY };
      renderer.domElement.setPointerCapture(event.pointerId);
    };
    const handlePointerUp = (event: PointerEvent) => {
      if (dragStart) {
        updatePointer(event);
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObjects(nodeObjects, false)[0];
        const nodeId = hit?.object.userData.id;
        if (typeof nodeId === "string") handlersRef.current.onSelectNode?.(nodeId);
      }
      dragStart = undefined;
    };
    const handlePointerLeave = () => handlersRef.current.onHoverObject?.(undefined);
    const handleContextLost = (event: Event) => {
      event.preventDefault();
      setContextLost(true);
      onAvailabilityChange(false);
      handlersRef.current.onRenderMetrics({
        kind: "three-3d",
        visibleNodes: nodeObjects.length,
        visibleEdges: edgeMaterialById.size,
        contextLost: true
      });
    };
    const handleContextRestored = () => {
      setContextLost(false);
      onAvailabilityChange(true);
      handlersRef.current.onRenderMetrics({
        kind: "three-3d",
        visibleNodes: nodeObjects.length,
        visibleEdges: edgeMaterialById.size,
        contextLost: false
      });
      resize();
    };

    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);
    renderer.domElement.addEventListener("pointerleave", handlePointerLeave);
    renderer.domElement.addEventListener("webglcontextlost", handleContextLost);
    renderer.domElement.addEventListener("webglcontextrestored", handleContextRestored);
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    let disposed = false;
    const emitActiveNodePosition = () => {
      const currentActiveNodeId = handlersRef.current.activeNodeId;
      if (!currentActiveNodeId) {
        if (lastActivePositionKey) {
          lastActivePositionKey = "";
          handlersRef.current.onActiveNodePosition?.(undefined);
        }
        return;
      }

      const mesh = nodeObjectById.get(currentActiveNodeId);
      if (!mesh || width <= 1 || height <= 1) {
        const nextKey = `${currentActiveNodeId}:hidden`;
        if (lastActivePositionKey !== nextKey) {
          lastActivePositionKey = nextKey;
          handlersRef.current.onActiveNodePosition?.({ nodeId: currentActiveNodeId, x: 0, y: 0, visible: false });
        }
        return;
      }

      const position = new THREE.Vector3();
      mesh.getWorldPosition(position);
      position.project(camera);
      const x = ((position.x + 1) / 2) * width;
      const y = ((1 - position.y) / 2) * height;
      const visible = position.z >= -1 && position.z <= 1 && x >= 0 && x <= width && y >= 0 && y <= height;
      const viewX = (x / Math.max(1, width)) * 900;
      const viewY = (y / Math.max(1, height)) * 640;
      const nextKey = `${currentActiveNodeId}:${Math.round(viewX)}:${Math.round(viewY)}:${visible ? "v" : "h"}`;
      if (lastActivePositionKey !== nextKey) {
        lastActivePositionKey = nextKey;
        handlersRef.current.onActiveNodePosition?.({ nodeId: currentActiveNodeId, x: viewX, y: viewY, visible });
      }
    };

    const render = () => {
      if (disposed) return;
      frame = requestAnimationFrame(render);
      if (handlersRef.current.visualSignature !== appliedVisualSignature) {
        for (const [nodeId, mesh] of nodeObjectById) {
          const node = handlersRef.current.currentNodes.get(nodeId);
          if (!node || !(mesh.material instanceof THREE.MeshStandardMaterial)) continue;
          const color = colorForNode(node);
          mesh.material.color.setHex(color);
          mesh.material.emissive.copy(new THREE.Color(color).multiplyScalar(statusBoost(node.statuses)));
          mesh.material.opacity = node.statuses.includes("dimmed") ? 0.26 : 0.96;
        }
        for (const [edgeId, material] of edgeMaterialById) {
          const edge = handlersRef.current.currentEdges.get(edgeId);
          if (!edge) continue;
          material.color.setHex(colorForEdge(edge));
          material.opacity = opacityForEdge(edge);
        }
        appliedVisualSignature = handlersRef.current.visualSignature;
      }
      const currentSelectedNodeId = handlersRef.current.selectedNodeId;
      if (currentSelectedNodeId !== lastSelectedNodeId) {
        if (lastSelectedNodeId) {
          const previous = nodeObjectById.get(lastSelectedNodeId);
          if (previous) {
            previous.userData.baseScale = 1;
            previous.scale.setScalar(1);
          }
        }
        if (currentSelectedNodeId) {
          const selected = nodeObjectById.get(currentSelectedNodeId);
          if (selected) {
            selected.userData.baseScale = 1.32;
            selected.scale.setScalar(1.32);
          }
        }
        lastSelectedNodeId = currentSelectedNodeId;
      }
      root.rotation.y = yaw;
      root.rotation.x = pitch;
      if (!reducedMotion && semanticNodeObjects.length > 0) {
        const pulse = 1 + Math.sin(performance.now() / 180) * 0.1;
        for (const mesh of semanticNodeObjects) mesh.scale.setScalar(Number(mesh.userData.baseScale || 1) * pulse);
        const edgeOpacity = 0.58 + Math.sin(performance.now() / 140) * 0.2;
        for (const material of semanticEdgeMaterials) material.opacity = edgeOpacity;
      }
      root.updateMatrixWorld(true);
      emitActiveNodePosition();
      renderer.render(scene, camera);
      metricFrameCount += 1;
      const now = performance.now();
      if (now - metricWindowStartedAt >= 1_000) {
        handlersRef.current.onRenderMetrics({
          kind: "three-3d",
          visibleNodes: nodeObjects.length,
          visibleEdges: edgeMaterialById.size,
          framesPerSecond: metricFrameCount / ((now - metricWindowStartedAt) / 1_000),
          contextLost: false
        });
        metricWindowStartedAt = now;
        metricFrameCount = 0;
      }
    };
    render();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      renderer.domElement.removeEventListener("pointerleave", handlePointerLeave);
      renderer.domElement.removeEventListener("webglcontextlost", handleContextLost);
      renderer.domElement.removeEventListener("webglcontextrestored", handleContextRestored);
      if (renderer.domElement.parentElement === container) container.removeChild(renderer.domElement);
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          object.geometry.dispose();
          const material = object.material;
          if (Array.isArray(material)) material.forEach((item) => item.dispose());
          else material.dispose();
        }
      });
      renderer.dispose();
    };
  }, [fitSequence, graphSignature, onAvailabilityChange, reducedMotion]);

  if (rendererUnavailable) {
    return <div className="three-graph-unavailable" role="status" aria-label="3D graph unavailable" />;
  }

  return (
    <div className="three-graph-scene" data-renderer="three" ref={containerRef}>
      {contextLost && <div className="graph-webgl-unavailable" role="status">WebGL context lost. Restoring graph state…</div>}
    </div>
  );
}

function colorForNode(node: GraphRendererNode) {
  if (node.statuses.includes("blocked") || node.statuses.includes("rejected")) return 0xff8f7b;
  if (node.statuses.includes("candidate") || node.statuses.includes("ready")) return 0xf2cf7b;
  if (node.statuses.includes("incoming") || node.statuses.includes("cited")) return 0x8fe2ce;
  return NODE_COLORS[node.kind] ?? 0xb6d3ff;
}

function colorForEdge(edge: GraphRendererEdge) {
  if (edge.statuses.includes("candidate")) return 0xf2cf7b;
  if (edge.statuses.includes("cited")) return 0x8fe2ce;
  return 0x788493;
}

function opacityForEdge(edge: GraphRendererEdge) {
  if (edge.statuses.includes("dimmed")) return 0.16;
  if (edge.statuses.includes("related")) return 0.78;
  return 0.42;
}

function statusBoost(statuses: GraphVisualStatus[]) {
  if (statuses.some((status) => status === "focus" || status === "hover" || status === "scanning")) return 0.38;
  if (statuses.some((status) => status === "incoming" || status === "cited" || status === "candidate")) return 0.22;
  return 0.08;
}

function sceneSignature(nodes: GraphRendererNode[], edges: GraphRendererEdge[]) {
  const nodeSignature = nodes
    .map((node) =>
      [
        node.id,
        node.kind,
        node.x.toFixed(1),
        node.y.toFixed(1),
        node.z.toFixed(1),
        node.radius.toFixed(2),
        stableStatusKey(node.statuses)
      ].join(":")
    )
    .join("|");
  const edgeSignature = edges
    .map((edge) => [edge.id, edge.sourceNodeId, edge.targetNodeId, stableStatusKey(edge.statuses)].join(":"))
    .join("|");
  return `${nodeSignature}::${edgeSignature}`;
}

function sceneVisualSignature(nodes: GraphRendererNode[], edges: GraphRendererEdge[]) {
  const nodeSignature = nodes.map((node) => `${node.id}:${node.statuses.join(",")}`).join("|");
  const edgeSignature = edges.map((edge) => `${edge.id}:${edge.statuses.join(",")}`).join("|");
  return `${nodeSignature}::${edgeSignature}`;
}

function stableStatusKey(statuses: GraphVisualStatus[]) {
  return statuses
    .filter((status) => !["dimmed", "focus", "hover", "related"].includes(status))
    .sort()
    .join(",");
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
