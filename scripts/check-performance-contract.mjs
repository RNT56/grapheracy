import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";

import { planGraphRender } from "../packages/graph-core/src/index.ts";

const nodeCount = Number(process.env.GRAPHVIEW_PERF_NODE_COUNT ?? 5_000);
const edgeCount = Number(process.env.GRAPHVIEW_PERF_EDGE_COUNT ?? 20_000);
const maximumDurationMs = Number(process.env.GRAPHVIEW_PERF_PLAN_MS ?? 1_000);

const nodes = Array.from({ length: nodeCount }, (_, index) => ({
  id: `perf-node-${index}`,
  projectId: "perf-project",
  topicIds: [],
  label: `Performance node ${index}`,
  kind: "concept",
  provenance: [],
  createdAt: "2026-07-10T00:00:00.000Z",
  updatedAt: "2026-07-10T00:00:00.000Z"
}));
const edges = Array.from({ length: edgeCount }, (_, index) => ({
  id: `perf-edge-${index}`,
  projectId: "perf-project",
  sourceNodeId: nodes[index % nodeCount].id,
  targetNodeId: nodes[(index * 17 + 1) % nodeCount].id,
  relation: "relates_to",
  provenance: [],
  createdAt: "2026-07-10T00:00:00.000Z",
  updatedAt: "2026-07-10T00:00:00.000Z"
}));

const startedAt = performance.now();
const plan = planGraphRender({ nodes, edges });
const durationMs = performance.now() - startedAt;

assert.ok(plan.nodes.length <= 120, "render plan must stay within the current visible-node budget");
assert.ok(plan.edges.length <= 240, "render plan must stay within the current visible-edge budget");
assert.ok(durationMs <= maximumDurationMs, `render planning took ${durationMs.toFixed(1)}ms`);

console.log(`Performance contract passed (${nodeCount} nodes, ${edgeCount} edges, ${durationMs.toFixed(1)}ms).`);
