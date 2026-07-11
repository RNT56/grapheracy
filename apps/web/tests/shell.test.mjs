import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

function assertSourceIncludes(source, pattern, label) {
  assert.ok(pattern.test(source), `${label} missing ${pattern}`);
}

test("web shell is product-first and wired to API health", async () => {
  const source = `${await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")}\n${await readFile(new URL("../src/apiClient.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useWorkspaceQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useGraphQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useAttentionQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useConnectorQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/usePlanningQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useAgentContextQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/workspaceTypes.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/workspaceModel.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/sourceContentModel.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/contentExpansionModel.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/connectorWorkspaceModel.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/WorkspaceChrome.tsx", import.meta.url), "utf8")}\n${await readFile(new URL("../src/SettingsWorkspace.tsx", import.meta.url), "utf8")}\n${await readFile(new URL("../src/PlanningWorkspace.tsx", import.meta.url), "utf8")}\n${await readFile(new URL("../src/AgentContextWorkspace.tsx", import.meta.url), "utf8")}`;
  assert.match(source, /fetchHealth/);
  assert.match(source, /createSource/);
  assert.match(source, /ingestText/);
  assert.match(source, /\/ingestion-runs/);
  assert.match(source, /\/extraction-lenses/);
  assert.match(source, /\/graph-lenses/);
  assert.match(source, /\/graphs/);
  assert.match(source, /GraphPicker/);
  assert.match(source, /graph-picker/);
  assert.match(source, /General Knowledge Graph/);
  assert.match(source, /\/graph\/settings/);
  assert.match(source, /\/connectors/);
  assert.match(source, /\/connector-accounts/);
  assert.match(source, /\/connector-targets/);
  assert.match(source, /\/connector-sync-runs/);
  assert.match(source, /\/source-chunks/);
  assert.match(source, /\/review-queue/);
  assert.match(source, /\/review-dashboard/);
  assert.match(source, /\/review-activity/);
  assert.match(source, /\/review-sources/);
  assert.match(source, /\/source-chunks/);
  assert.match(source, /\/providers/);
  assert.match(source, /fallbackProviders/);
  assert.match(source, /withFallbackProviders/);
  assert.match(source, /OpenAI API key/);
  assert.match(source, /Anthropic API key/);
  assert.match(source, /Gemini API key/);
  assert.match(source, /\/planning-sessions/);
  assert.match(source, /\/agent-context\/sessions/);
  assert.match(source, /AgentContextWorkspace/);
  assert.match(source, /Active context/);
  assert.match(source, /\/ai\/query/);
  assert.match(source, /\/ai\/research/);
  assert.match(source, /approve-action/);
  assert.match(source, /PlanningWorkspace/);
  assert.match(source, /Planning Mode/);
  assert.match(source, /Artifact Preview/);
  assert.match(source, /Graph AI/);
  assert.match(source, /AgentToolCallCard/);
  assert.match(source, /graphAgentToolCalls/);
  assert.match(source, /agent-tool-card/);
  assert.match(source, /AI citations/);
  assert.match(source, /askGraphAgent/);
  assert.match(source, /runGraphResearch/);
  assert.match(source, /approveAgentAction/);
  assert.match(source, /citationDrawerOpen/);
  assert.match(source, /workspaceMode/);
  assert.match(source, /Evidence/);
  assert.match(source, /source-content-reader/);
  assert.match(source, /Context pane/);
  assert.match(source, /Focus context/);
  assert.match(source, /Related/);
  assert.match(source, /Source reader/);
  assert.match(source, /sourceModalOpen/);
  assert.match(source, /ingestComposerOpen/);
  assert.match(source, /ingestMode/);
  assert.match(source, /Connect sources/);
  assert.match(source, /copySourceContent/);
  assert.match(source, /exportSourceContent/);
  assert.match(source, /shareSourceContent/);
  assert.match(source, /buildContextSourceBlocks/);
  assert.match(source, /handleSelectGraphNode/);
  assert.match(source, /reviewProposal/);
  assert.match(source, /normalizeGraph/);
  assert.match(source, /NODE_KIND_DEFINITIONS/);
  assert.match(source, /normalizeContentNodeKind/);
  assert.match(source, /LENS_SUPPORT_NODE_KINDS/);
  assert.match(source, /extractionLensIdForSourceKind/);
  assert.match(source, /extractionLensIdForGraphLens/);
  assert.match(source, /nodeKindDefinitionsForLens/);
  assert.match(source, /kindLibrarySourceKind/);
  assert.match(source, /Active node kind lens/);
  assert.match(source, /Node kind legend/);
  assert.match(source, /nodeKindExpanded/);
  assert.match(source, /kindLibraryDefinitions/);
  assert.match(source, /displayedNodeKindDefinitions/);
  assert.match(source, /Show more/);
  assert.match(source, /node-kind-label/);
  assert.doesNotMatch(source, /Source type legend/);
  assert.match(source, /selectedGraphLensId/);
  assert.match(source, /GraphLensIcon/);
  assert.match(source, /sourceKind/);
  assert.doesNotMatch(source, /selectedMode\.sourceKind/);
  assert.doesNotMatch(source, /engineering-repository/);
  assert.doesNotMatch(source, /ops-document-map/);
  assert.match(source, /semantic_edge/);
  assert.match(source, /Needs attention/);
  assert.match(source, /Review work items/);
  assert.match(source, /review-worklist/);
  assert.match(source, /reviewWorkItemLabel/);
  assert.match(source, /buildContentExpansionGraph/);
  assert.match(source, /contentExpansionChunks/);
  assert.match(source, /Show source graph/);
  assert.match(source, /\/lineage\//);
  assert.match(source, /Lineage/);
  assert.match(source, /\/insights/);
  assert.match(source, /Insights/);
  assert.match(source, /\/graph\/neighborhood\//);
  assert.match(source, /Neighborhood/);
  assert.match(source, /\/graph\/path/);
  assert.match(source, /Path/);
  assert.match(source, /attention-list/);
  assert.match(source, /Knowledge Graph Builder/);
  assert.match(source, /Outline/);
  assert.match(source, /Context/);
  assert.match(source, /Graph controls/);
  assert.match(source, /graphViewMode/);
  assert.match(source, /activateGraphViewMode/);
  assert.match(source, /overview-mode-panel/);
  assert.match(source, /focus-mode-panel/);
  assert.match(source, /evidence-mode-panel/);
  assert.match(source, /Graph overview metrics/);
  assert.match(source, /Top connected/);
  assert.match(source, /Citation-backed claims/);
  assert.match(source, /api-status-chip/);
  assert.match(source, /graphLayout/);
  assert.match(source, /setGraphLayout/);
  assert.match(source, /graphDimension/);
  assert.match(source, /3D graph/);
  assert.match(source, /showContents/);
  assert.match(source, /Search graph/);
  assert.match(source, /Ingest document/);
  assert.match(source, /Connector setup/);
  assert.match(source, /Sync connector/);
  assert.match(source, /Resync/);
  assert.match(source, /LLM extraction/);
  assert.match(source, /auto_commit_threshold/);
  assert.match(source, /Auto-commit/);
  assert.match(source, /proposalToGraphEdge/);
  assert.match(source, /GraphCanvasEdge/);
  assert.match(source, /graph-builder/);
  assert.match(source, /Digital nervous system/);
  assert.match(source, /Graph-centered Attention/);
  assert.doesNotMatch(source, /Full source content/);
  assert.doesNotMatch(source, /Accept next/);
  assert.doesNotMatch(source, /Fan out subcontents/);
  assert.doesNotMatch(source, /hero/i);
});

test("graph canvas uses bounded render plans for large graphs", async () => {
  const source = await readFile(new URL("../src/GraphCanvas.tsx", import.meta.url), "utf8");
  assert.match(source, /planGraphRender/);
  assert.match(source, /GraphLayoutMode/);
  assert.match(source, /forcePositions/);
  assert.match(source, /radialPositions/);
  assert.match(source, /arcPositions/);
  assert.match(source, /project3d/);
  assert.match(source, /graph-edge-flow/);
  assert.match(source, /is-proposed/);
  assert.match(source, /is-content-node/);
  assert.match(source, /is-content-edge/);
  assert.match(source, /edgeEndpoints/);
  assert.match(source, /effectiveDimension/);
  assert.match(source, /graph-render-budget/);
  assert.match(source, /orphanEdgeCount/);
  assert.match(source, /NODE_KIND_DEFINITIONS/);
  assert.match(source, /kindIndexFor/);
  assert.match(source, /isPrimaryNodeKind/);
  assert.match(source, /sensedIds/);
  assert.match(source, /actionRunningIds/);
  assert.match(source, /feedbackAppliedIds/);
  assert.match(source, /tooltipPlacementScore/);
  assert.match(source, /onActiveNodePosition/);
  assert.match(source, /activeNodeId/);
});

test("phase 25 digital nervous system routes through Attention mode", async () => {
  const appSource = `${await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useAttentionQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useActionCredentialMutations.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/workspaceTypes.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/AgentContextWorkspace.tsx", import.meta.url), "utf8")}`;
  const canvasSource = await readFile(new URL("../src/GraphCanvas.tsx", import.meta.url), "utf8");
  const sharedTypes = await readFile(new URL("../../../packages/shared-types/src/index.ts", import.meta.url), "utf8");
  const graphCore = await readFile(new URL("../../../packages/graph-core/src/index.ts", import.meta.url), "utf8");

  for (const route of [
    "/signals",
    "/observations",
    "/alerts",
    "/attention",
    "/owners",
    "/routing-policies",
    "/decision-records",
    "/action-credentials/",
    "/action-proposals",
    "/action-runs",
    "/outcomes",
    "/feedback-events"
  ]) {
    assertSourceIncludes(appSource, new RegExp(route.replaceAll("/", "\\/")), `phase 25 route ${route}`);
  }

  assertSourceIncludes(appSource, /GraphViewMode = "overview" \| "focus" \| "evidence" \| "review" \| "attention"/, "attention graph mode");
  assertSourceIncludes(appSource, /createOperationalSignal/, "sense mutation");
  assertSourceIncludes(appSource, /createOperationalDecision/, "decision mutation");
  assertSourceIncludes(appSource, /approveOperationalAction/, "action approval mutation");
  assertSourceIncludes(appSource, /credential_id: "smtp"/, "safe SMTP credential selection");
  assertSourceIncludes(appSource, /waitForJob<ApiOperationalActionRun>/, "durable external action execution");
  assertSourceIncludes(appSource, /recordOperationalOutcome/, "outcome mutation");
  assertSourceIncludes(appSource, /operating-loop-strip/, "operating loop strip");
  assertSourceIncludes(appSource, /Sense", "Interpret", "Remember", "Prioritize", "Decide", "Act", "Observe", "Learn"/, "loop labels");

  assertSourceIncludes(sharedTypes, /"signal_sensed"/, "shared signal event kind");
  assertSourceIncludes(sharedTypes, /"outcome_succeeded"/, "shared outcome status event kind");
  assertSourceIncludes(sharedTypes, /export interface ActionProposal/, "shared action proposal contract");
  assertSourceIncludes(graphCore, /slaAtRiskIds/, "graph-core SLA risk visual ids");
  assertSourceIncludes(graphCore, /feedbackAppliedIds/, "graph-core feedback visual ids");
  assertSourceIncludes(canvasSource, /event.kind === "feedback_applied"/, "canvas feedback hint");
  assertSourceIncludes(canvasSource, /event.kind === "attention_reopened"/, "canvas reopened hint");
});

test("phase 27 active context workspace and shared contracts are exposed", async () => {
  const appSource = `${await readFile(new URL("../src/App.tsx", import.meta.url), "utf8")}\n${await readFile(new URL("../src/useAgentContextQueries.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/workspaceTypes.ts", import.meta.url), "utf8")}\n${await readFile(new URL("../src/AgentContextWorkspace.tsx", import.meta.url), "utf8")}`;
  const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  const sharedTypes = await readFile(new URL("../../../packages/shared-types/src/index.ts", import.meta.url), "utf8");

  assertSourceIncludes(sharedTypes, /export interface AgentContextSession/, "shared context session contract");
  assertSourceIncludes(sharedTypes, /export interface AgentContextEvent/, "shared context event contract");
  assertSourceIncludes(sharedTypes, /export interface AgentContextGraph/, "shared context graph contract");
  assertSourceIncludes(sharedTypes, /CaptureAuthority/, "shared capture authority contract");
  assertSourceIncludes(sharedTypes, /ContextEventKind/, "shared context event kind contract");
  assertSourceIncludes(sharedTypes, /"passive_reconciled"/, "shared passive authority");

  assertSourceIncludes(appSource, /type WorkspaceMode = "graph" \| "planning" \| "settings" \| "context"/, "context workspace mode");
  assertSourceIncludes(appSource, /AgentContextWorkspace/, "active context component");
  assertSourceIncludes(appSource, /\/agent-context\/sessions\?limit=25/, "active context sessions route");
  assertSourceIncludes(appSource, /\/agent-context\/sessions\/.*\/graph/, "active context graph route");
  assertSourceIncludes(appSource, /\/agent-context\/sessions\/.*\/stream/, "active context stream route");
  assertSourceIncludes(appSource, /new EventSource/, "active context event stream client");
  assertSourceIncludes(appSource, /addEventListener\("agent-context\.event"/, "active context stream listener");
  assertSourceIncludes(appSource, /\/agent-context\/artifacts\/.*\/content/, "active context artifact content route");
  assertSourceIncludes(appSource, /Content inspector/, "active context content inspector");
  assertSourceIncludes(appSource, /redaction_status\.replaceAll/, "active context redaction display");
  assertSourceIncludes(appSource, /authority-/, "active context authority badges");
  assertSourceIncludes(styles, /agent-context-workspace/, "active context workspace styles");
  assertSourceIncludes(styles, /agent-context-inspector/, "active context inspector styles");
  assertSourceIncludes(styles, /authority-gateway/, "active context authority style");
});

test("living graph contracts are exposed for web integration", async () => {
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const querySource = await readFile(new URL("../src/useGraphQueries.ts", import.meta.url), "utf8");
  const apiSource = await readFile(new URL("../src/apiClient.ts", import.meta.url), "utf8");
  const canvasSource = await readFile(new URL("../src/GraphCanvas.tsx", import.meta.url), "utf8");
  const tooltipSource = await readFile(new URL("../src/GraphTooltipLayer.tsx", import.meta.url), "utf8");
  const rendererContract = await readFile(new URL("../src/graphRendererContract.ts", import.meta.url), "utf8");
  const sharedTypes = await readFile(new URL("../../../packages/shared-types/src/index.ts", import.meta.url), "utf8");
  const webSource = `${appSource}\n${querySource}\n${canvasSource}\n${tooltipSource}\n${rendererContract}`;

  assertSourceIncludes(sharedTypes, /export interface GraphVisualState/, "shared visual state contract");
  assertSourceIncludes(sharedTypes, /export interface GraphTooltipModel/, "shared tooltip contract");
  assertSourceIncludes(sharedTypes, /export interface GraphActivityEvent/, "shared activity contract");
  assertSourceIncludes(sharedTypes, /GraphVisualStatus/, "shared visual status union");
  assertSourceIncludes(sharedTypes, /"scanning"/, "shared scanning status");
  assertSourceIncludes(sharedTypes, /"candidate"/, "shared candidate status");
  assertSourceIncludes(sharedTypes, /"blocked"/, "shared blocked status");
  assertSourceIncludes(sharedTypes, /"stale"/, "shared stale status");

  assertSourceIncludes(appSource, /GraphActivityEvent/, "app activity event usage");
  assertSourceIncludes(appSource, /graphActivityEvents/, "app activity event query state");
  assertSourceIncludes(querySource, /\/graph\/activity/, "app graph activity route");
  assertSourceIncludes(apiSource, /\/agent-runs\/.*\/activity/, "app agent activity route");
  assertSourceIncludes(appSource, /Graph AI agent/, "app graph AI panel");
  assertSourceIncludes(appSource, /Graph agent activity/, "app graph agent activity panel");

  assertSourceIncludes(webSource, /GraphVisualState/, "web visual state usage");
  assertSourceIncludes(rendererContract, /GraphRendererSceneProps/, "shared renderer scene contract");
  assertSourceIncludes(webSource, /GraphTooltipModel/, "web tooltip model usage");
  assertSourceIncludes(webSource, /GraphTooltipLayer/, "web tooltip layer");
  assertSourceIncludes(webSource, /graph-tooltip/, "web tooltip class");
  assertSourceIncludes(webSource, /graph-tooltip-tether/, "web tooltip tether class");
  assertSourceIncludes(webSource, /graph-tooltip-source-url/, "web tooltip source URL class");
  assertSourceIncludes(webSource, /graph-activity-layer/, "web activity layer class");
  assertSourceIncludes(webSource, /graph-candidate-layer/, "web candidate layer class");
  assertSourceIncludes(webSource, /prefers-reduced-motion/, "web reduced-motion handling");
  assertSourceIncludes(webSource, /data-testid="graph-canvas-root"/, "browser graph root test id");
  assertSourceIncludes(webSource, /data-testid="graph-canvas-surface"/, "browser graph surface test id");
  assertSourceIncludes(webSource, /data-testid="graph-tooltip"/, "browser tooltip test id");
  assertSourceIncludes(webSource, /data-testid="graph-tooltip-tether"/, "browser tooltip tether test id");
  assertSourceIncludes(webSource, /data-testid="graph-tooltip-source-url"/, "browser tooltip source URL test id");
});
