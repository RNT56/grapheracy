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
  await expectNonBlank(surface, "3D graph");
});

test("shows tethered node tooltip with safe source URL behavior", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Living Graph Tooltip Node" }).hover();

  const tooltip = page.getByTestId("graph-tooltip");
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toContainText("Living Graph Tooltip Node");
  await expect(page.getByTestId("graph-tooltip-tether")).toBeVisible();

  const url = page.getByTestId("graph-tooltip-source-url");
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
});

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
    const path = url.pathname;

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
      await fulfillJson(route, {
        providers: [
          {
            id: "graphview-local",
            label: "Graphview Local",
            enabled: true,
            configured: true,
            default_model: "graphview-local-deterministic-v1",
            capabilities: ["planning", "graph_query", "research"]
          }
        ]
      });
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
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: {
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
      "Access-Control-Allow-Origin": "*"
    },
    body: body === undefined ? "" : JSON.stringify(body)
  });
}
