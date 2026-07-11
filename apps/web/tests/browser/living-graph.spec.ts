import { expect, test, type Locator, type Page, type Route } from "@playwright/test";
import { PNG } from "pngjs";

const graphId = "phase24-living-graph";
const now = "2026-06-05T12:00:00.000Z";
const sourceUrl = "https://example.com/phase24-source";

const source = {
  id: "source-phase24-url",
  title: "Phase 24 URL source",
  kind: "url",
  uri: sourceUrl,
  remote_url: sourceUrl,
  metadata: {}
};

const providers = [
  {
    id: "graphview-local",
    label: "Graphview Local",
    enabled: true,
    configured: true,
    default_model: "graphview-local-deterministic-v1",
    capabilities: ["planning", "graph_query", "research", "structured_output"],
    models: [
      {
        id: "graphview-local-deterministic-v1",
        label: "Local deterministic",
        default: true,
        capabilities: ["planning", "graph_query", "research", "structured_output"]
      }
    ]
  },
  {
    id: "openai",
    label: "OpenAI",
    enabled: false,
    configured: false,
    default_model: "gpt-5.5",
    capabilities: ["planning", "graph_query", "research", "structured_output", "tool_calling"],
    models: [
      { id: "gpt-5.5", label: "gpt-5.5", default: true, capabilities: ["reasoning", "tool_calling", "structured_output"] },
      { id: "gpt-5.4-mini", label: "gpt-5.4-mini", default: false, capabilities: ["fast_reasoning", "tool_calling", "structured_output"] }
    ]
  },
  {
    id: "anthropic",
    label: "Anthropic",
    enabled: false,
    configured: false,
    default_model: "claude-opus-4.8",
    capabilities: ["planning", "graph_query", "research", "tool_calling"],
    models: [
      { id: "claude-opus-4.8", label: "claude-opus-4.8", default: true, capabilities: ["reasoning", "tool_calling", "long_context"] },
      { id: "claude-sonnet-4.6", label: "claude-sonnet-4.6", default: false, capabilities: ["fast_reasoning", "tool_calling", "long_context"] }
    ]
  },
  {
    id: "gemini",
    label: "Gemini",
    enabled: false,
    configured: false,
    default_model: "gemini-3.1-pro",
    capabilities: ["planning", "graph_query", "research", "structured_output", "search_grounding", "url_context"],
    models: [
      { id: "gemini-3.1-pro", label: "gemini-3.1-pro", default: true, capabilities: ["reasoning", "function_calling", "search_grounding", "url_context"] },
      { id: "gemini-3.5-flash", label: "gemini-3.5-flash", default: false, capabilities: ["fast_reasoning", "function_calling", "search_grounding", "url_context"] }
    ]
  }
];

const nodes = [
  {
    id: "node-living-graph",
    project_id: graphId,
    topic_ids: [],
    label: "Living Graph Tooltip Node",
    kind: "concept",
    summary: "A graph node with tethered Phase 24 tooltip details and a source URL.",
    metadata: { sourceUrl },
    provenance: [{ sourceId: source.id, locator: "phase24:node" }],
    created_at: now,
    updated_at: now
  },
  {
    id: "node-agent-scan",
    project_id: graphId,
    topic_ids: [],
    label: "Agent Scan Path",
    kind: "workflow",
    summary: "A related node used by graph activity scan fixtures.",
    metadata: {},
    provenance: [{ sourceId: source.id, locator: "phase24:scan" }],
    created_at: now,
    updated_at: now
  },
  {
    id: "node-candidate-review",
    project_id: graphId,
    topic_ids: [],
    label: "Candidate Review Gate",
    kind: "decision",
    summary: "A review-gated graph object used by Phase 24 candidate visuals.",
    metadata: {},
    provenance: [{ sourceId: source.id, locator: "phase24:review" }],
    created_at: now,
    updated_at: now
  }
];

const edges = [
  {
    id: "edge-living-graph-scan",
    project_id: graphId,
    source_node_id: nodes[0].id,
    target_node_id: nodes[1].id,
    relation: "references",
    weight: 0.88,
    metadata: {},
    provenance: [{ sourceId: source.id, locator: "phase24:edge" }],
    created_at: now,
    updated_at: now
  },
  {
    id: "edge-scan-review",
    project_id: graphId,
    source_node_id: nodes[1].id,
    target_node_id: nodes[2].id,
    relation: "has_review_cycle",
    weight: 0.8,
    metadata: {},
    provenance: [{ sourceId: source.id, locator: "phase24:edge-review" }],
    created_at: now,
    updated_at: now
  }
];

const proposal = {
  id: "proposal-phase24-candidate",
  kind: "content_node",
  status: "pending_review",
  proposed_value: {
    label: "Candidate Tooltip Action",
    kind: "concept",
    summary: "Candidate object shown in the Phase 24 proposal layer."
  }
};

const citation = {
  id: "citation-phase24-url",
  source_id: source.id,
  source_title: source.title,
  source_chunk_id: "chunk-phase24-url",
  node_id: nodes[0].id,
  edge_id: null,
  locator: "phase24:tooltip-url",
  excerpt: "Phase 24 source excerpt for tooltip URL behavior."
};

test.beforeEach(async ({ page }) => {
  await installApiFixtures(page);
});

test("renders nonblank 2D and 3D living graph surfaces", async ({ page }) => {
  await page.goto("/");

  const root = page.locator('[data-testid="graph-canvas-root"], .graph-canvas-wrap').first();
  const surface = page.locator('[data-testid="graph-canvas-surface"], .graph-canvas').first();

  await expect(root).toBeVisible();
  await expect(page.getByRole("img", { name: /rendered graph nodes/i })).toBeVisible();
  await expectNonBlank(surface, "2D graph");

  await page.getByRole("button", { name: "3D graph" }).click();
  await expect(root).toHaveClass(/graph-view-3d/);
  const threeCanvas = page.locator(".three-graph-canvas").first();
  await expect(threeCanvas).toBeVisible();
  await expectBrightPixels(threeCanvas, "3D graph canvas");
  await expectNonBlank(surface, "3D graph");
});

test("keeps semantic graph state static when reduced motion is requested", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");

  const root = page.getByTestId("graph-canvas-root");
  await expect(root).toHaveAttribute("data-motion-tier", "reduced_motion");
  await expectStablePixels(page.getByTestId("sigma-graph-scene"), "reduced-motion Sigma scene");

  await page.getByRole("button", { name: "3D graph" }).click();
  await expect(root).toHaveClass(/graph-view-3d/);
  await expectStablePixels(page.locator(".three-graph-canvas"), "reduced-motion Three.js scene");
});

test("provides a complete non-WebGL graph fallback", async ({ page }) => {
  await page.addInitScript(() => {
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: function (contextId: string, ...arguments_: unknown[]) {
        if (contextId === "webgl" || contextId === "webgl2" || contextId === "experimental-webgl") return null;
        return Reflect.apply(originalGetContext, this, [contextId, ...arguments_]);
      } as typeof HTMLCanvasElement.prototype.getContext
    });
  });
  await page.goto("/");
  expect(await page.evaluate(() => Boolean(document.createElement("canvas").getContext("webgl")))).toBe(false);

  const root = page.getByTestId("graph-canvas-root");
  await expect(root).toHaveClass(/graph-webgl-fallback/);
  await expect(page.getByRole("img", { name: /3 rendered graph nodes and 2 rendered graph edges/i })).toBeVisible();
  await expectNonBlank(page.getByTestId("graph-canvas-surface"), "non-WebGL 2D fallback");

  await page.getByRole("button", { name: "3D graph" }).click();
  await expect(page.getByRole("status", { name: "3D graph unavailable" })).toBeVisible();
  await expect(root).toHaveClass(/graph-webgl-fallback/);
  await expectNonBlank(page.getByTestId("graph-canvas-surface"), "non-WebGL 3D fallback");
});

test("requests bounded viewport projections and preserves state across WebGL recovery", async ({ page }) => {
  const viewportRequests: URL[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (/^\/api\/v1\/graphs\/[^/]+\/viewport$/.test(url.pathname)) viewportRequests.push(url);
  });

  await page.goto("/");
  await expect(page.getByTestId("sigma-graph-scene")).toBeVisible();
  await expect.poll(() => viewportRequests.length).toBeGreaterThan(0);
  const root = page.getByTestId("graph-canvas-root");
  await expect(root).toHaveAttribute("data-renderer-kind", "sigma-2d");
  await expect(root).toHaveAttribute("data-renderer-visible-nodes", "3");
  await expect(root).toHaveAttribute("data-renderer-visible-edges", "2");

  const initialRequest = viewportRequests[0];
  expect(initialRequest.searchParams.get("max_nodes")).toBe("20000");
  expect(initialRequest.searchParams.get("max_edges")).toBe("50000");
  for (const parameter of ["zoom", "min_x", "min_y", "max_x", "max_y"]) {
    expect(initialRequest.searchParams.has(parameter), `${parameter} should scope the viewport projection`).toBe(true);
  }

  const isMobile = (page.viewportSize()?.width ?? 1440) <= 820;
  await selectAccessibleGraphNode(page, "Living Graph Tooltip Node");
  if (isMobile) {
    const app = page.getByLabel("Knowledge Graph Builder");
    await expect(app).toHaveClass(/mobile-section-focus/);
    await expect(page.getByText("A graph node with tethered Phase 24 tooltip details and a source URL.")).toBeVisible();
    await page.getByRole("button", { name: "Open graph" }).click();
    await expect(app).toHaveClass(/mobile-section-graph/);
  } else {
    await expect(page.getByTestId("graph-tooltip")).toContainText("Living Graph Tooltip Node");
  }

  const canLoseContext = await page.evaluate(() => {
    const canvases = [...document.querySelectorAll<HTMLCanvasElement>('[data-testid="sigma-graph-scene"] canvas')];
    for (const canvas of canvases) {
      const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
      const extension = context?.getExtension("WEBGL_lose_context");
      if (!extension) continue;
      (window as typeof window & { __graphviewWebglExtension?: WEBGL_lose_context }).__graphviewWebglExtension = extension;
      extension.loseContext();
      return true;
    }
    return false;
  });
  test.skip(!canLoseContext, "Chromium did not expose WEBGL_lose_context");

  await expect(root).toHaveClass(/graph-webgl-fallback/);
  await expect(root).toHaveAttribute("data-renderer-context", "lost");
  await expect(page.getByRole("img", { name: /3 rendered graph nodes/i })).toBeVisible();

  await page.evaluate(() => {
    (window as typeof window & { __graphviewWebglExtension?: WEBGL_lose_context }).__graphviewWebglExtension?.restoreContext();
  });
  await expect(root).not.toHaveClass(/graph-webgl-fallback/);
  await expect(root).toHaveAttribute("data-renderer-context", "ready");
  if (isMobile) {
    await expect(page.getByLabel("Knowledge Graph Builder")).toHaveClass(/graph-view-focus/);
  } else {
    await expect(page.getByTestId("graph-tooltip")).toContainText("Living Graph Tooltip Node");
  }

  await page.getByRole("button", { name: "3D graph" }).click();
  await expect(page.locator(".three-graph-canvas")).toBeVisible();
  const canLoseThreeContext = await page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(".three-graph-canvas");
    const context = canvas?.getContext("webgl2") ?? canvas?.getContext("webgl");
    const extension = context?.getExtension("WEBGL_lose_context");
    if (!extension) return false;
    (window as typeof window & { __graphviewThreeWebglExtension?: WEBGL_lose_context }).__graphviewThreeWebglExtension = extension;
    extension.loseContext();
    return true;
  });
  expect(canLoseThreeContext, "Chromium should expose Three.js context-loss injection").toBe(true);
  await expect(root).toHaveClass(/graph-webgl-fallback/);
  await expect(root).toHaveAttribute("data-renderer-kind", "three-3d");
  await expect(root).toHaveAttribute("data-renderer-context", "lost");
  await page.evaluate(() => {
    (window as typeof window & { __graphviewThreeWebglExtension?: WEBGL_lose_context }).__graphviewThreeWebglExtension?.restoreContext();
  });
  await expect(root).not.toHaveClass(/graph-webgl-fallback/);
  await expect(root).toHaveAttribute("data-renderer-context", "ready");
  await expectBrightPixels(page.locator(".three-graph-canvas"), "restored 3D graph canvas");
  if (isMobile) {
    await expect(page.getByLabel("Knowledge Graph Builder")).toHaveClass(/graph-view-focus/);
  } else {
    await expect(page.getByTestId("graph-tooltip")).toContainText("Living Graph Tooltip Node");
  }
});

test("opens a 100k node and 500k edge project through clustered overview within 2.5 seconds", async ({ page }) => {
  const clusterCount = 400;
  const overviewEdgeCount = 1_000;
  const clusters = Array.from({ length: clusterCount }, (_, index) => ({
    id: `cluster:${index}`,
    label: `Knowledge cluster ${index + 1}`,
    x: -0.96 + (index % 25) * 0.08,
    y: -0.9 + Math.floor(index / 25) * 0.12,
    node_count: 250,
    edge_count: 1_250,
    dominant_kind: "concept",
    node_ids: []
  }));
  const overviewEdges = Array.from({ length: overviewEdgeCount }, (_, index) => ({
    id: `cluster-edge:${index}`,
    source_id: clusters[index % clusterCount].id,
    target_id: clusters[(index * 11 + 1) % clusterCount].id,
    relation: "relates_to",
    weight: 1,
    count: 500,
    edge: null
  }));
  let projectionReceivedAt = 0;
  page.on("requestfinished", (request) => {
    const url = new URL(request.url());
    if (/^\/api\/v1\/graphs\/[^/]+\/viewport$/.test(url.pathname)) projectionReceivedAt = Date.now();
  });
  await page.route("http://127.0.0.1:8000/api/v1/graphs/*/viewport**", async (route) => {
    const url = new URL(route.request().url());
    const requestedGraphId = url.pathname.split("/").at(-2) ?? graphId;
    await fulfillJson(route, {
      graph_id: requestedGraphId,
      project_id: requestedGraphId,
      graph_version: 100_000,
      etag: '"production-cluster-overview"',
      zoom: Number(url.searchParams.get("zoom") ?? 0.25),
      level: "clusters",
      bounds: { min_x: -1, min_y: -1, max_x: 1, max_y: 1 },
      nodes: [],
      edges: overviewEdges,
      clusters,
      omitted_node_count: 0,
      omitted_edge_count: 0,
      page: { next_cursor: null, has_more: false }
    });
  });

  await page.goto("/");
  const data = page.locator(".graph-accessible-data");
  await expect(data.getByText(`Accessible graph data (${clusterCount} nodes, ${overviewEdgeCount} relations)`)).toBeVisible();
  expect(projectionReceivedAt).toBeGreaterThan(0);
  expect(Date.now() - projectionReceivedAt, "clustered overview should become interactive after the API response").toBeLessThanOrEqual(2_500);
  await expectBrightPixels(page.getByTestId("sigma-graph-scene"), "Sigma clustered overview");
});

test("renders an interactive production-sized viewport with bounded accessible data", async ({ page }) => {
  test.setTimeout(45_000);
  const isMobile = (page.viewportSize()?.width ?? 1440) <= 820;
  const nodeCount = isMobile ? 600 : 5_000;
  const edgeCount = isMobile ? 599 : 20_000;
  const rowCount = Math.ceil(nodeCount / 100);
  const largeNodes = Array.from({ length: nodeCount }, (_, index) => ({
    ...nodes[index % nodes.length],
    id: `node-scale-${index.toString().padStart(4, "0")}`,
    label: `Scale node ${index.toString().padStart(4, "0")}`,
    summary: `Accessible scale fixture ${index}`,
    metadata: {}
  }));
  const largeEdges = Array.from({ length: edgeCount }, (_, index) => ({
    ...edges[index % edges.length],
    id: `edge-scale-${index.toString().padStart(4, "0")}`,
    source_node_id: largeNodes[index % largeNodes.length].id,
    target_node_id: largeNodes[(index * 17 + 1) % largeNodes.length].id
  }));
  let projectionReceivedAt = 0;
  page.on("requestfinished", (request) => {
    const url = new URL(request.url());
    if (/^\/api\/v1\/graphs\/[^/]+\/viewport$/.test(url.pathname)) projectionReceivedAt = Date.now();
  });
  await page.route("http://127.0.0.1:8000/api/v1/graphs/*/viewport**", async (route) => {
    const url = new URL(route.request().url());
    await fulfillJson(route, {
      graph_id: graphId,
      project_id: graphId,
      graph_version: 2,
      etag: '"scale-viewport-v2"',
      zoom: Number(url.searchParams.get("zoom") ?? 0.25),
      level: "nodes",
      bounds: { min_x: -1, min_y: -1, max_x: 1, max_y: 1 },
      nodes: largeNodes.map((node, index) => ({
        node,
        x: -0.96 + (index % 100) * (1.92 / 99),
        y: -0.92 + Math.floor(index / 100) * (1.84 / Math.max(1, rowCount - 1)),
        z: 0
      })),
      edges: largeEdges.map((edge) => ({
        id: edge.id,
        source_id: edge.source_node_id,
        target_id: edge.target_node_id,
        relation: edge.relation,
        weight: edge.weight,
        count: 1,
        edge: null
      })),
      clusters: [],
      omitted_node_count: 0,
      omitted_edge_count: 0,
      page: { next_cursor: null, has_more: false }
    });
  });

  await page.goto("/");
  const data = page.locator(".graph-accessible-data");
  await expect(data.getByText(`Accessible graph data (${nodeCount} nodes, ${edgeCount} relations)`)).toBeVisible();
  expect(projectionReceivedAt, "the viewport response should complete before interactivity is measured").toBeGreaterThan(0);
  await expect(page.getByTestId("graph-canvas-root")).toHaveAttribute("data-renderer-visible-nodes", String(nodeCount));
  await expect(page.getByTestId("graph-canvas-root")).toHaveAttribute("data-renderer-visible-edges", String(edgeCount));
  await expectBrightPixels(page.getByTestId("sigma-graph-scene"), "Sigma production viewport");

  const renderedFps = await measureZoomFps(page);
  expect(renderedFps, "viewport should preserve an interactive frame cadence while zooming").toBeGreaterThanOrEqual(isMobile ? 30 : 45);

  await data.locator("summary").click();
  await expect(data.getByRole("row")).toHaveCount(502);

  const finalNodeLabel = `Scale node ${(nodeCount - 1).toString().padStart(4, "0")}`;
  await data.getByRole("searchbox", { name: "Filter visible graph data" }).fill(finalNodeLabel);
  await expect(data.getByRole("button", { name: finalNodeLabel })).toBeVisible();
  await expect(data.getByText("Visible graph nodes (1 matches)")).toBeVisible();
});

test("keeps a 20k node and 50k edge raw viewport above 30 FPS", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name.includes("mobile"), "The 20k raw viewport acceptance target is for the desktop reference machine");
  test.setTimeout(90_000);
  const nodeCount = 20_000;
  const edgeCount = 50_000;
  const stressNodes = Array.from({ length: nodeCount }, (_, index) => ({
    ...nodes[index % nodes.length],
    id: `node-stress-${index.toString().padStart(5, "0")}`,
    label: `Stress node ${index.toString().padStart(5, "0")}`,
    summary: undefined,
    metadata: {}
  }));
  const stressEdges = Array.from({ length: edgeCount }, (_, index) => ({
    id: `edge-stress-${index.toString().padStart(5, "0")}`,
    source_id: stressNodes[index % nodeCount].id,
    target_id: stressNodes[(index * 19 + 1) % nodeCount].id,
    relation: "relates_to",
    weight: 1,
    count: 1,
    edge: null
  }));
  await page.route("http://127.0.0.1:8000/api/v1/graphs/*/viewport**", async (route) => {
    const url = new URL(route.request().url());
    const requestedGraphId = url.pathname.split("/").at(-2) ?? graphId;
    await fulfillJson(route, {
      graph_id: requestedGraphId,
      project_id: requestedGraphId,
      graph_version: 3,
      etag: '"stress-viewport-v3"',
      zoom: Number(url.searchParams.get("zoom") ?? 8),
      level: "nodes",
      bounds: { min_x: -1, min_y: -1, max_x: 1, max_y: 1 },
      nodes: stressNodes.map((node, index) => ({
        node,
        x: -0.97 + (index % 200) * (1.94 / 199),
        y: -0.94 + Math.floor(index / 200) * (1.88 / 99),
        z: 0
      })),
      edges: stressEdges,
      clusters: [],
      omitted_node_count: 0,
      omitted_edge_count: 0,
      page: { next_cursor: null, has_more: false }
    });
  });

  await page.goto("/");
  await expect(page.locator(".graph-accessible-data").getByText(`Accessible graph data (${nodeCount} nodes, ${edgeCount} relations)`)).toBeVisible({ timeout: 30_000 });
  await expectBrightPixels(page.getByTestId("sigma-graph-scene"), "Sigma stress viewport");
  expect(await measureZoomFps(page), "20k/50k viewport should remain operational while zooming").toBeGreaterThanOrEqual(30);
});

test("settings use left navigation and focused pages", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.locator(".settings-sidebar")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Credentials/ })).toBeVisible();

  await page.getByRole("tab", { name: /Credentials/ }).click();
  await expect(page.getByRole("heading", { name: "Credentials" })).toBeVisible();
  await expect(page.getByRole("button", { name: /OpenAI/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Anthropic/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Gemini/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Graphview Local/ })).toBeVisible();

  await page.getByRole("button", { name: /OpenAI/ }).click();
  await expect(page.getByLabel("OpenAI API key")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save key" })).toBeDisabled();
  await page.getByLabel("OpenAI API key").fill("test-openai-key");
  await expect(page.getByRole("button", { name: "Save key" })).toBeEnabled();
  await expect(page.getByText("Saving sets OpenAI as the default LLM provider.")).toBeVisible();
  await expect(page.getByRole("button", { name: /GitHub Issues/ })).toBeVisible();
  await page.getByRole("button", { name: /Signed webhook/ }).click();
  await expect(page.getByLabel("Signing secret")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save credential" })).toBeDisabled();
  await page.getByLabel("Signing secret").fill("test-webhook-secret");
  await expect(page.getByRole("button", { name: "Save credential" })).toBeEnabled();

  await page.getByRole("tab", { name: /Automation/ }).click();
  await expect(page.getByRole("heading", { name: "Automation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save automation" })).toBeVisible();

  await page.getByRole("tab", { name: /Capabilities/ }).click();
  await expect(page.getByRole("heading", { name: "Capabilities" })).toBeVisible();
  await expect(page.locator(".settings-provider-matrix")).toBeVisible();
});

test("opens active context workspace with mocked live context data", async ({ page }) => {
  const agentContextRequests: string[] = [];
  await installMockEventSource(page);
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/v1/agent-context/")) {
      agentContextRequests.push(`${url.pathname}${url.search}`);
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Active context" }).click();

  const workspace = page.getByLabel("Active agent context");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByRole("heading", { name: "Codex active context" })).toBeVisible();
  await expect(workspace).toContainText("codex / running / gateway");

  const sessions = page.getByLabel("Captured sessions");
  await expect(sessions.getByRole("button", { name: /Codex active context/ })).toHaveAttribute("aria-pressed", "true");

  const metrics = page.getByLabel("Active context metrics");
  await expect(metrics).toContainText("4 events");
  await expect(metrics).toContainText("2 artifacts");
  await expect(metrics).toContainText("2 gateway");
  await expect(metrics).toContainText("2 reconciled");

  const graphProjection = page.getByLabel("Context graph projection");
  await expect(graphProjection).toContainText("file read");
  await expect(graphProjection).toContainText("read");
  await expect(graphProjection).toContainText("App.tsx");

  const promptAndEdits = page.getByLabel("Prompt and edit activity");
  await expect(promptAndEdits).toContainText("prompt built");
  await expect(promptAndEdits).toContainText("model response");
  await expect(promptAndEdits).toContainText("edit applied");
  await expect(promptAndEdits.locator(".authority-gateway")).toContainText("prompt built");
  await expect(promptAndEdits.locator(".authority-adapter_reported")).toContainText("model response");
  await expect(promptAndEdits.locator(".authority-passive_reconciled")).toContainText("edit applied");

  const timeline = page.getByLabel("Active context timeline");
  await expect(timeline).toContainText("Read App.tsx.");
  await expect(timeline).toContainText("gateway / apps/web/src/App.tsx");
  await expect(timeline).toContainText("Adapter returned a grounded model response.");
  await expect(timeline).toContainText("adapter reported");
  await expect(timeline).toContainText("Observed a passive edit touching App.tsx.");
  await expect(timeline).toContainText("passive reconciled");

  await expect
    .poll(() => page.evaluate(() => window.__agentContextEventSourceUrls?.at(-1) ?? ""))
    .toBe("http://127.0.0.1:8000/api/v1/agent-context/sessions/ctxsession-phase27/stream?limit=25");

  const inspectAppArtifact = timeline
    .locator(".agent-context-event")
    .filter({ hasText: "Read App.tsx." })
    .getByRole("button", { name: "Inspect artifact" });
  await expect(inspectAppArtifact).toBeVisible();
  const contentResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/v1/agent-context/artifacts/ctxartifact-file/content" && response.ok();
  });
  await inspectAppArtifact.evaluate((button: HTMLButtonElement) => button.click());
  await contentResponse;

  const inspector = page.getByLabel("Content inspector");
  await expect(inspector).toContainText("App.tsx");
  await expect(inspector).toContainText("redacted");
  await expect(inspector).toContainText("encrypted");
  await expect(inspector).toContainText('const apiToken = "[REDACTED]";');
  await expect(inspector).not.toContainText("super-secret-token");

  const graphRequestCount = agentContextRequests.filter((path) => path === "/api/v1/agent-context/sessions/ctxsession-phase27/graph").length;
  const contentRequestCount = agentContextRequests.filter((path) => path === "/api/v1/agent-context/artifacts/ctxartifact-file/content").length;

  await page.evaluate(() => window.__dispatchAgentContextEvent?.());

  await expect
    .poll(() => agentContextRequests.filter((path) => path === "/api/v1/agent-context/sessions/ctxsession-phase27/graph").length)
    .toBeGreaterThan(graphRequestCount);
  await expect
    .poll(() => agentContextRequests.filter((path) => path === "/api/v1/agent-context/artifacts/ctxartifact-file/content").length)
    .toBeGreaterThan(contentRequestCount);
});

test("shows tethered node tooltip with safe source URL behavior", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.goto("/");

  await selectAccessibleGraphNode(page, "Living Graph Tooltip Node");
  if ((page.viewportSize()?.width ?? 1440) <= 820) {
    await page.getByRole("button", { name: "Open graph" }).click();
  }

  const tooltip = page.getByTestId("graph-tooltip");
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toContainText("Living Graph Tooltip Node");
  await expect(page.getByTestId("graph-tooltip-tether")).toBeVisible();
  await expect(tooltip).toHaveCSS("pointer-events", "none");
  await expect(tooltip).toHaveAttribute("data-placement", /right|left|top|bottom/);

  const tooltipInterceptsPointer = await tooltip.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const target = document.elementFromPoint(rect.left + 12, rect.top + 12);
    return Boolean(target?.closest('[data-testid="graph-tooltip"]'));
  });
  expect(tooltipInterceptsPointer).toBe(false);

  const url = page.getByTestId("graph-tooltip-source-url");
  await expect(url).toHaveCSS("pointer-events", "auto");
  await expect(url).toHaveAttribute("href", sourceUrl);
  await expect(url).toHaveAttribute("target", "_blank");
  await expect(url).toHaveAttribute("rel", /noopener|noreferrer/);

  const currentUrl = page.url();
  await url.hover();
  await expect(page).toHaveURL(currentUrl);

  const popupPromise = page.waitForEvent("popup");
  await url.click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(sourceUrl);
  await popup.close();
  expect(consoleErrors.filter((message) => message.includes("Maximum update depth"))).toEqual([]);
});

async function selectAccessibleGraphNode(page: Page, label: string) {
  const data = page.locator(".graph-accessible-data");
  if (!(await data.getAttribute("open"))) await data.locator("summary").click();
  const node = data.getByRole("button", { name: label });
  await expect(node).toBeVisible();
  await node.focus();
  await node.press("Enter");
}

async function installMockEventSource(page: Page) {
  await page.addInitScript({
    content: `
      (() => {
        window.__agentContextEventSourceUrls = [];
        window.__dispatchAgentContextEvent = () => {};

        class MockEventSource extends EventTarget {
          constructor(url) {
            super();
            this.url = String(url);
            this.readyState = 0;
            window.__agentContextEventSourceUrls.push(this.url);
            window.__lastAgentContextEventSource = this;
            window.__dispatchAgentContextEvent = () => {
              this.dispatchEvent(new MessageEvent("agent-context.event", { data: "{}" }));
            };
          }

          close() {
            this.readyState = 2;
          }
        }

        MockEventSource.CONNECTING = 0;
        MockEventSource.OPEN = 1;
        MockEventSource.CLOSED = 2;
        window.EventSource = MockEventSource;
      })();
    `
  });
}

async function expectNonBlank(locator: Locator, label: string) {
  const image = PNG.sync.read(await locator.screenshot({ animations: "disabled" }));
  let coloredPixels = 0;
  const totalPixels = image.width * image.height;

  for (let index = 0; index < image.data.length; index += 4) {
    const red = image.data[index];
    const green = image.data[index + 1];
    const blue = image.data[index + 2];
    const alpha = image.data[index + 3];
    const nearWhite = red > 245 && green > 245 && blue > 245;
    const nearTransparent = alpha < 8;
    if (!nearTransparent && !nearWhite) coloredPixels += 1;
  }

  expect(coloredPixels, `${label} should contain visible graph pixels`).toBeGreaterThan(Math.floor(totalPixels * 0.01));
}

async function expectBrightPixels(locator: Locator, label: string) {
  const image = PNG.sync.read(await locator.screenshot({ animations: "disabled" }));
  let brightPixels = 0;

  for (let index = 0; index < image.data.length; index += 4) {
    const red = image.data[index];
    const green = image.data[index + 1];
    const blue = image.data[index + 2];
    const alpha = image.data[index + 3];
    if (alpha > 8 && red + green + blue > 120) brightPixels += 1;
  }

  expect(brightPixels, `${label} should contain rendered node or edge pixels`).toBeGreaterThan(30);
}

async function expectStablePixels(locator: Locator, label: string) {
  await expect(locator).toBeVisible();
  await new Promise((resolve) => setTimeout(resolve, 500));
  const before = PNG.sync.read(await captureRendererPixels(locator));
  await new Promise((resolve) => setTimeout(resolve, 280));
  const after = PNG.sync.read(await captureRendererPixels(locator));
  expect(after.width).toBe(before.width);
  expect(after.height).toBe(before.height);
  let changedPixels = 0;
  for (let index = 0; index < before.data.length; index += 4) {
    const difference =
      Math.abs(before.data[index] - after.data[index]) +
      Math.abs(before.data[index + 1] - after.data[index + 1]) +
      Math.abs(before.data[index + 2] - after.data[index + 2]);
    if (difference > 8) changedPixels += 1;
  }
  expect(changedPixels, `${label} should not use continuous semantic motion`).toBeLessThanOrEqual(12);
}

async function captureRendererPixels(locator: Locator) {
  const canvasDataUrl = await locator.evaluate((element) =>
    element instanceof HTMLCanvasElement ? element.toDataURL("image/png") : undefined
  );
  if (canvasDataUrl) return Buffer.from(canvasDataUrl.slice(canvasDataUrl.indexOf(",") + 1), "base64");
  return locator.screenshot({ animations: "disabled" });
}

async function measureZoomFps(page: Page) {
  return page.evaluate(async () => {
    const target = document.querySelector<HTMLCanvasElement>('[data-testid="sigma-graph-scene"] canvas');
    if (!target) return 0;
    let frames = 0;
    const startedAt = performance.now();
    const wheel = window.setInterval(() => {
      const rect = target.getBoundingClientRect();
      target.dispatchEvent(new WheelEvent("wheel", {
        bubbles: true,
        cancelable: true,
        clientX: rect.left + rect.width / 2,
        clientY: rect.top + rect.height / 2,
        deltaY: frames % 2 === 0 ? -24 : 24
      }));
    }, 80);
    await new Promise<void>((resolve) => {
      const sample = (timestamp: number) => {
        frames += 1;
        if (timestamp - startedAt >= 1_000) resolve();
        else requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
    });
    window.clearInterval(wheel);
    return frames / ((performance.now() - startedAt) / 1_000);
  });
}

async function installApiFixtures(page: Page) {
  await page.route("https://example.com/**", async (route) => {
    await route.fulfill({
      contentType: "text/html",
      body: "<!doctype html><title>Phase 24 source</title><main>Phase 24 source fixture</main>"
    });
  });

  await page.route("http://127.0.0.1:8000/**", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await fulfillJson(route, undefined, 204);
      return;
    }

    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/v1(?=\/)/, "");

    if (path === "/health") {
      await fulfillJson(route, { status: "ok", service: "graphview-api" });
      return;
    }
    if (path === "/graphs") {
      await fulfillJson(route, [
        {
          id: graphId,
          project_id: graphId,
          label: "Phase 24 Living Graph",
          description: "Browser QA fixture for living graph rendering.",
          kind: "project",
          source_ids: [source.id],
          node_count: nodes.length,
          edge_count: edges.length,
          source_count: 1,
          pending_proposal_count: 1
        }
      ]);
      return;
    }
    if (path === "/graph") {
      await fulfillJson(route, {
        project: {
          id: graphId,
          name: "Phase 24 Living Graph",
          description: "Browser QA fixture for living graph rendering.",
          created_at: now,
          updated_at: now
        },
        nodes,
        edges
      });
      return;
    }
    if (/^\/graphs\/[^/]+\/viewport$/.test(path)) {
      const requestedGraphId = path.split("/")[2] || graphId;
      await fulfillJson(route, {
        graph_id: requestedGraphId,
        project_id: requestedGraphId,
        graph_version: 1,
        etag: '"phase24-viewport-v1"',
        zoom: Number(url.searchParams.get("zoom") ?? 0.25),
        level: "nodes",
        bounds: {
          min_x: Number(url.searchParams.get("min_x") ?? -1),
          min_y: Number(url.searchParams.get("min_y") ?? -1),
          max_x: Number(url.searchParams.get("max_x") ?? 1),
          max_y: Number(url.searchParams.get("max_y") ?? 1)
        },
        nodes: nodes.map((node, index) => ({
          node,
          x: -0.62 + index * 0.62,
          y: index % 2 === 0 ? -0.32 : 0.32,
          z: index * 12
        })),
        edges: edges.map((edge) => ({
          id: edge.id,
          source_id: edge.source_node_id,
          target_id: edge.target_node_id,
          relation: edge.relation,
          weight: edge.weight,
          count: 1,
          edge
        })),
        clusters: [],
        omitted_node_count: 0,
        omitted_edge_count: 0,
        page: { next_cursor: null, has_more: false }
      });
      return;
    }
    if (path === "/sources") {
      await fulfillJson(route, { sources: [source] });
      return;
    }
    if (path === "/source-chunks") {
      await fulfillJson(route, {
        source_chunks: [
          {
            id: "chunk-phase24-url",
            source_id: source.id,
            parent_chunk_id: null,
            block_type: "paragraph",
            ordinal: 0,
            text: "Phase 24 source excerpt for tooltip URL behavior.",
            checksum: "phase24-tooltip-url",
            locator: "paragraph:1",
            heading_path: ["Phase 24"],
            links: [sourceUrl],
            mentions: ["Living Graph Tooltip Node"],
            metadata: {}
          }
        ]
      });
      return;
    }
    if (path === "/proposals") {
      await fulfillJson(route, { proposals: [proposal] });
      return;
    }
    if (path === "/review-queue") {
      await fulfillJson(route, {
        pending_count: 1,
        ready_count: 1,
        blocked_count: 0,
        items: [
          {
            proposal,
            source,
            priority_score: 0.91,
            action: "review_node",
            work_item_kind: "research_result",
            change_summary: "Review a candidate living graph tooltip action.",
            evidence_summary: "Candidate is backed by the Phase 24 URL source.",
            affected_graph_ids: [nodes[0].id],
            citations: [citation],
            blocked: false,
            ready_to_commit: true,
            reason: "Ready for review.",
            endpoint_node_ids: [],
            missing_endpoint_node_ids: []
          }
        ]
      });
      return;
    }
    if (path === "/review-dashboard") {
      await fulfillJson(route, {
        proposal_count: 1,
        pending_count: 1,
        ready_count: 1,
        blocked_count: 0,
        review_decision_count: 0,
        accepted_count: 0,
        rejected_count: 0,
        edited_count: 0,
        deferred_count: 0,
        acceptance_rate: 0,
        commit_rate: 0,
        oldest_pending_proposal_id: proposal.id,
        oldest_pending_created_at: now
      });
      return;
    }
    if (path === "/review-activity") {
      await fulfillJson(route, { review_decision_count: 0, returned_count: 0, items: [] });
      return;
    }
    if (path === "/review-sources") {
      await fulfillJson(route, {
        sources: [
          {
            source,
            status: "pending_review",
            proposal_count: 1,
            pending_count: 1,
            reviewed_count: 0,
            decision_count: 0,
            accepted_count: 0,
            rejected_count: 0,
            edited_count: 0,
            deferred_count: 0,
            last_reviewed_at: null
          }
        ]
      });
      return;
    }
    if (path === "/review-decisions") {
      await fulfillJson(route, { review_decisions: [] });
      return;
    }
    if (path === "/insights") {
      await fulfillJson(route, {
        node_count: nodes.length,
        edge_count: edges.length,
        source_count: 1,
        proposal_count: 1,
        pending_proposal_count: 1,
        connected_edge_count: edges.length,
        orphan_edge_count: 0,
        provenance_coverage: {
          reviewed_item_count: nodes.length + edges.length,
          traced_item_count: nodes.length + edges.length,
          missing_item_count: 0,
          coverage_percent: 100
        },
        top_nodes: nodes.map((node) => ({ id: node.id, label: node.label, kind: node.kind, degree: 2 }))
      });
      return;
    }
    if (path === "/lineage/edge/edge-living-graph-scan" || path.startsWith("/lineage/")) {
      await fulfillJson(route, {
        entity_kind: "edge",
        entity_id: edges[0].id,
        source,
        proposals: [proposal],
        review_decisions: [],
        nodes,
        edges,
        provenance: []
      });
      return;
    }
    if (path.startsWith("/graph/neighborhood/")) {
      await fulfillJson(route, {
        center_node: nodes[0],
        depth: 1,
        limit: 12,
        nodes,
        edges,
        omitted_node_count: 0,
        omitted_edge_count: 0
      });
      return;
    }
    if (path === "/graph/path") {
      await fulfillJson(route, {
        source_node: nodes[0],
        target_node: nodes[1],
        max_depth: 4,
        path_found: true,
        distance: 1,
        nodes: [nodes[0], nodes[1]],
        edges: [edges[0]]
      });
      return;
    }
    if (path === "/graph/activity" || path.match(/^\/agent-runs\/[^/]+\/activity$/)) {
      await fulfillJson(route, {
        activity_events: [
          {
            id: "activity-phase24-scan",
            project_id: graphId,
            graph_id: graphId,
            kind: "agent_scan",
            status: "running",
            subject: { kind: "node", id: nodes[0].id, label: nodes[0].label },
            actor_id: "agent-phase24",
            agent_run_id: "agent-run-phase24",
            source_ids: [source.id],
            source_chunk_ids: ["chunk-phase24-url"],
            node_ids: nodes.map((node) => node.id),
            edge_ids: edges.map((edge) => edge.id),
            proposal_ids: [proposal.id],
            review_decision_ids: [],
            citations: [citation],
            summary: "Agent scan is traversing the living graph.",
            metadata: {},
            occurred_at: now
          }
        ]
      });
      return;
    }
    if (path === "/agent-context/sessions") {
      await fulfillJson(route, {
        sessions: [
          {
            id: "ctxsession-phase27",
            project_id: graphId,
            client_id: "ctxclient-phase27",
            runtime_kind: "codex",
            authority: "gateway",
            status: "running",
            title: "Codex active context",
            workspace_root: "/workspace/graphview",
            repository_uri: "git@example.invalid:graphview.git",
            branch: "codex/phase27",
            commit_sha: "abc123",
            metadata: {},
            started_at: now,
            ended_at: null,
            updated_at: now
          }
        ]
      });
      return;
    }
    if (path === "/agent-context/sessions/ctxsession-phase27/graph") {
      await fulfillJson(route, {
        session: {
          id: "ctxsession-phase27",
          project_id: graphId,
          client_id: "ctxclient-phase27",
          runtime_kind: "codex",
          authority: "gateway",
          status: "running",
          title: "Codex active context",
          workspace_root: "/workspace/graphview",
          repository_uri: "git@example.invalid:graphview.git",
          branch: "codex/phase27",
          commit_sha: "abc123",
          metadata: {},
          started_at: now,
          ended_at: null,
          updated_at: now
        },
        nodes: [
          { id: "ctxsession-phase27", kind: "session", label: "Codex active context", authority: "gateway", metadata: {} },
          { id: "ctxartifact-file", kind: "file", label: "App.tsx", authority: null, metadata: { path: "apps/web/src/App.tsx" } },
          { id: "ctxartifact-prompt", kind: "prompt", label: "Prompt context", authority: null, metadata: { title: "Prompt context" } },
          { id: "ctxevent-read", kind: "event", label: "file read", authority: "gateway", metadata: {} },
          { id: "ctxevent-prompt", kind: "event", label: "prompt built", authority: "gateway", metadata: {} },
          { id: "ctxevent-model", kind: "event", label: "model response", authority: "adapter_reported", metadata: {} },
          { id: "ctxevent-edit", kind: "event", label: "edit applied", authority: "passive_reconciled", metadata: {} }
        ],
        edges: [
          {
            id: "ctxedge-read",
            source_id: "ctxevent-read",
            target_id: "ctxartifact-file",
            relation: "read",
            observed: true,
            metadata: { authority: "gateway" }
          },
          {
            id: "ctxedge-prompt",
            source_id: "ctxevent-prompt",
            target_id: "ctxartifact-prompt",
            relation: "built_prompt",
            observed: true,
            metadata: { authority: "gateway" }
          },
          {
            id: "ctxedge-edit",
            source_id: "ctxevent-edit",
            target_id: "ctxartifact-file",
            relation: "edited",
            observed: false,
            metadata: { authority: "passive_reconciled" }
          }
        ],
        artifacts: [
          {
            id: "ctxartifact-file",
            project_id: graphId,
            session_id: "ctxsession-phase27",
            kind: "file",
            path: "apps/web/src/App.tsx",
            uri: null,
            title: "App.tsx",
            content_type: "text/typescript",
            checksum: "abc",
            metadata: {},
            created_at: now,
            updated_at: now
          },
          {
            id: "ctxartifact-prompt",
            project_id: graphId,
            session_id: "ctxsession-phase27",
            kind: "prompt",
            path: null,
            uri: null,
            title: "Prompt context",
            content_type: "text/markdown",
            checksum: "prompt123",
            metadata: {},
            created_at: now,
            updated_at: now
          }
        ],
        events: [
          {
            id: "ctxevent-read",
            project_id: graphId,
            session_id: "ctxsession-phase27",
            client_event_id: "evt-read",
            sequence: 1,
            event_kind: "file_read",
            authority: "gateway",
            status: "accepted",
            summary: "Read App.tsx.",
            checksum: "ctxevent-read",
            artifact_id: "ctxartifact-file",
            blob_id: "ctxblob-file",
            payload: {},
            object_refs: [],
            occurred_at: now,
            received_at: now
          },
          {
            id: "ctxevent-prompt",
            project_id: graphId,
            session_id: "ctxsession-phase27",
            client_event_id: "evt-prompt",
            sequence: 2,
            event_kind: "prompt_built",
            authority: "gateway",
            status: "accepted",
            summary: "Built prompt from graph context.",
            checksum: "ctxevent-prompt",
            artifact_id: "ctxartifact-prompt",
            blob_id: "ctxblob-prompt",
            payload: { token_count: 128 },
            object_refs: [{ kind: "artifact", id: "ctxartifact-prompt", label: "Prompt context" }],
            occurred_at: now,
            received_at: now
          },
          {
            id: "ctxevent-model",
            project_id: graphId,
            session_id: "ctxsession-phase27",
            client_event_id: "evt-model",
            sequence: 3,
            event_kind: "model_response",
            authority: "adapter_reported",
            status: "accepted",
            summary: "Adapter returned a grounded model response.",
            checksum: "ctxevent-model",
            artifact_id: "ctxartifact-prompt",
            blob_id: "ctxblob-prompt",
            payload: { model: "graphview-local-deterministic-v1" },
            object_refs: [],
            occurred_at: now,
            received_at: now
          },
          {
            id: "ctxevent-edit",
            project_id: graphId,
            session_id: "ctxsession-phase27",
            client_event_id: "evt-edit",
            sequence: 4,
            event_kind: "edit_applied",
            authority: "passive_reconciled",
            status: "accepted",
            summary: "Observed a passive edit touching App.tsx.",
            checksum: "ctxevent-edit",
            artifact_id: "ctxartifact-file",
            blob_id: "ctxblob-file",
            payload: { source: "filesystem_reconcile" },
            object_refs: [{ kind: "file", id: "ctxartifact-file", label: "App.tsx" }],
            occurred_at: now,
            received_at: now
          }
        ]
      });
      return;
    }
    if (path === "/agent-context/artifacts/ctxartifact-file/content") {
      await fulfillJson(route, {
        blob: {
          id: "ctxblob-file",
          project_id: graphId,
          session_id: "ctxsession-phase27",
          artifact_id: "ctxartifact-file",
          content_kind: "text",
          media_type: "text/typescript",
          redaction_status: "redacted",
          encryption_status: "encrypted",
          checksum: "ctxblob-file",
          byte_count: 74,
          token_count: 16,
          metadata: { redacted_fields: ["apiToken"] },
          created_at: now,
          expires_at: null
        },
        text: 'const apiToken = "[REDACTED]";\\nexport const activeContext = true;'
      });
      return;
    }
    if (path === "/extraction-lenses") {
      await fulfillJson(route, {
        extraction_lenses: [
          {
            id: "research",
            label: "Research",
            summary: "Research extraction lens.",
            default_proposal_limit: 8,
            source_kinds: ["text", "markdown", "url"],
            primary_node_kinds: ["concept", "topic", "source"],
            provenance_fields: ["source_id", "locator"]
          }
        ]
      });
      return;
    }
    if (path === "/graph-lenses") {
      await fulfillJson(route, {
        graph_lenses: [
          { id: "all", label: "All", summary: "All reviewed graph items.", active_by_default: true },
          { id: "research", label: "Research", summary: "Research graph items.", active_by_default: false }
        ]
      });
      return;
    }
    if (path === "/connectors") {
      await fulfillJson(route, { connectors: [] });
      return;
    }
    if (path === "/connector-accounts") {
      await fulfillJson(route, { connector_accounts: [] });
      return;
    }
    if (path === "/connector-targets") {
      await fulfillJson(route, { connector_targets: [] });
      return;
    }
    if (path === "/connector-sync-runs") {
      await fulfillJson(route, { connector_sync_runs: [] });
      return;
    }
    if (path === "/graph/settings") {
      await fulfillJson(route, {
        project_id: graphId,
        llm_enabled: false,
        llm_provider: null,
        llm_model: null,
        auto_commit_threshold: 0.92,
        settings: {},
        created_at: now,
        updated_at: now
      });
      return;
    }
    if (path === "/providers") {
      await fulfillJson(route, { providers });
      return;
    }
    if (path === "/planning-sessions") {
      await fulfillJson(route, { planning_sessions: [] });
      return;
    }

    await fulfillJson(route, {});
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  const requestOrigin = await route.request().headerValue("origin");
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: {
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
      "Access-Control-Allow-Origin": requestOrigin ?? "http://127.0.0.1:5173",
      "Access-Control-Allow-Credentials": "true",
      Vary: "Origin"
    },
    body: body === undefined ? "" : JSON.stringify(body)
  });
}
