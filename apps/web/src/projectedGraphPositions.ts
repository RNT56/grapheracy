import type { ContentNode } from "@graphview/shared-types";

export function projectedGraphPositions(nodes: ContentNode[], width: number, height: number) {
  const projected = nodes.map((node) => node.metadata?.graphviewPosition).filter(
    (position): position is { x: number; y: number; z?: number } => {
      const candidate = position as { x?: unknown; y?: unknown } | undefined;
      return typeof candidate?.x === "number" && typeof candidate.y === "number";
    }
  );
  if (projected.length !== nodes.length) return undefined;
  return new Map(nodes.map((node, index) => [node.id, {
    x: ((projected[index].x + 1) / 2) * width,
    y: ((projected[index].y + 1) / 2) * height,
    z: projected[index].z ?? 0
  }]));
}
