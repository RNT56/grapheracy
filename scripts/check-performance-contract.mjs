import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";

import { planGraphRender } from "../packages/graph-core/src/index.ts";

const ISO_TIMESTAMP = "2026-07-10T00:00:00.000Z";
const projectId = "perf-project";
const maximumOverviewDurationMs = Number(process.env.GRAPHVIEW_PERF_PLAN_MS ?? 2_500);

const nodes = Array.from({ length: 100_000 }, (_, index) => ({
  id: `perf-node-${index}`,
  projectId,
  topicIds: [],
  label: `Performance node ${index}`,
  kind: "concept",
  provenance: [],
  createdAt: ISO_TIMESTAMP,
  updatedAt: ISO_TIMESTAMP
}));
const edges = Array.from({ length: 500_000 }, (_, index) => ({
  id: `perf-edge-${index}`,
  projectId,
  sourceNodeId: nodes[index % nodes.length].id,
  targetNodeId: nodes[(index * 17 + 1) % nodes.length].id,
  relation: "relates_to",
  provenance: [],
  createdAt: ISO_TIMESTAMP,
  updatedAt: ISO_TIMESTAMP
}));

function visibleEdges(visibleNodes, edgeCount, prefix) {
  return Array.from({ length: edgeCount }, (_, index) => ({
    id: `${prefix}-edge-${index}`,
    projectId,
    sourceNodeId: visibleNodes[index % visibleNodes.length].id,
    targetNodeId: visibleNodes[(index * 17 + 1) % visibleNodes.length].id,
    relation: "relates_to",
    provenance: [],
    createdAt: ISO_TIMESTAMP,
    updatedAt: ISO_TIMESTAMP
  }));
}

const interactiveNodes = nodes.slice(0, 5_000);
const denseNodes = nodes.slice(0, 20_000);

const scenarios = [
  {
    name: "interactive viewport",
    data: { nodes: interactiveNodes, edges: visibleEdges(interactiveNodes, 20_000, "interactive") },
    limits: { maxNodes: 5_000, maxEdges: 20_000, labelMaxLength: 64 },
    maximumDurationMs: 1_000,
    expectedNodes: 5_000,
    expectedEdges: 20_000
  },
  {
    name: "dense viewport",
    data: { nodes: denseNodes, edges: visibleEdges(denseNodes, 50_000, "dense") },
    limits: { maxNodes: 20_000, maxEdges: 50_000, labelMaxLength: 48 },
    maximumDurationMs: 1_800,
    expectedNodes: 20_000,
    expectedEdges: 50_000
  },
  {
    name: "production project overview",
    data: { nodes, edges },
    limits: { maxNodes: 1_000, maxEdges: 4_000, labelMaxLength: 40 },
    maximumDurationMs: maximumOverviewDurationMs,
    expectedNodes: 1_000,
    expectedEdges: undefined
  }
];

for (const scenario of scenarios) {
  const startedAt = performance.now();
  const plan = planGraphRender(scenario.data, scenario.limits);
  const durationMs = performance.now() - startedAt;

  assert.equal(plan.nodes.length, scenario.expectedNodes, `${scenario.name} should honor its node budget`);
  assert.ok(plan.edges.length <= scenario.limits.maxEdges, `${scenario.name} should honor its edge budget`);
  if (scenario.expectedEdges !== undefined) {
    assert.equal(plan.edges.length, scenario.expectedEdges, `${scenario.name} should retain all visible edges`);
  }
  assert.ok(durationMs <= scenario.maximumDurationMs, `${scenario.name} planning took ${durationMs.toFixed(1)}ms`);
  console.log(
    `${scenario.name}: ${scenario.data.nodes.length} nodes / ${scenario.data.edges.length} edges -> ` +
      `${plan.nodes.length} nodes / ${plan.edges.length} edges in ${durationMs.toFixed(1)}ms`
  );
}

console.log("Performance contract passed for clustered overview and both raw viewport budgets.");
