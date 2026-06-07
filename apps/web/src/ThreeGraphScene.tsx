import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import type { GraphVisualStatus } from "@graphview/shared-types";

export interface ThreeGraphNode {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
  z: number;
  radius: number;
  statuses: GraphVisualStatus[];
}

export interface ThreeGraphEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  relation: string;
  statuses: GraphVisualStatus[];
}

interface Props {
  nodes: ThreeGraphNode[];
  edges: ThreeGraphEdge[];
  selectedNodeId?: string;
  reducedMotion: boolean;
  onHoverObject?: (objectId?: string) => void;
  onSelectNode?: (nodeId: string) => void;
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

export function ThreeGraphScene({ nodes, edges, selectedNodeId, reducedMotion, onHoverObject, onSelectNode }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [rendererUnavailable, setRendererUnavailable] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setRendererUnavailable(false);

    if (!supportsWebGL()) {
      setRendererUnavailable(true);
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x080a0e);
    const camera = new THREE.PerspectiveCamera(48, 1, 1, 2400);
    camera.position.set(0, 0, 720);
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    } catch {
      setRendererUnavailable(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
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
      if (node.id === selectedNodeId || node.statuses.includes("focus")) mesh.scale.setScalar(1.32);
      root.add(mesh);
      nodeObjects.push(mesh);
    }

    for (const edge of edges) {
      const source = nodePositions.get(edge.sourceNodeId);
      const target = nodePositions.get(edge.targetNodeId);
      if (!source || !target) continue;
      const geometry = new THREE.BufferGeometry().setFromPoints([source, target]);
      const material = new THREE.LineBasicMaterial({
        color: edge.statuses.includes("candidate") ? 0xf2cf7b : edge.statuses.includes("cited") ? 0x8fe2ce : 0x788493,
        transparent: true,
        opacity: edge.statuses.includes("dimmed") ? 0.16 : edge.statuses.includes("related") ? 0.78 : 0.42
      });
      root.add(new THREE.Line(geometry, material));
    }

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let width = 1;
    let height = 1;
    let yaw = -0.36;
    let pitch = 0.36;
    let dragStart: { x: number; y: number } | undefined;
    let frame = 0;

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
        return;
      }
      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(nodeObjects, false)[0];
      onHoverObject?.(typeof hit?.object.userData.id === "string" ? hit.object.userData.id : undefined);
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
        if (typeof nodeId === "string") onSelectNode?.(nodeId);
      }
      dragStart = undefined;
    };

    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);
    renderer.domElement.addEventListener("pointerleave", () => onHoverObject?.(undefined));
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    let disposed = false;
    const render = () => {
      if (disposed) return;
      frame = requestAnimationFrame(render);
      root.rotation.y = yaw;
      root.rotation.x = pitch;
      if (!reducedMotion) root.rotation.z = Math.sin(performance.now() / 4200) * 0.035;
      renderer.render(scene, camera);
    };
    render();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      container.removeChild(renderer.domElement);
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
  }, [edges, nodes, onHoverObject, onSelectNode, reducedMotion, selectedNodeId]);

  if (rendererUnavailable) {
    return <div className="three-graph-unavailable" role="status" aria-label="3D graph unavailable" />;
  }

  return <div className="three-graph-scene" data-renderer="three" ref={containerRef} />;
}

function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(window.WebGLRenderingContext && (canvas.getContext("webgl2") || canvas.getContext("webgl")));
  } catch {
    return false;
  }
}

function colorForNode(node: ThreeGraphNode) {
  if (node.statuses.includes("blocked") || node.statuses.includes("rejected")) return 0xff8f7b;
  if (node.statuses.includes("candidate") || node.statuses.includes("ready")) return 0xf2cf7b;
  if (node.statuses.includes("incoming") || node.statuses.includes("cited")) return 0x8fe2ce;
  return NODE_COLORS[node.kind] ?? 0xb6d3ff;
}

function statusBoost(statuses: GraphVisualStatus[]) {
  if (statuses.some((status) => status === "focus" || status === "hover" || status === "scanning")) return 0.38;
  if (statuses.some((status) => status === "incoming" || status === "cited" || status === "candidate")) return 0.22;
  return 0.08;
}
