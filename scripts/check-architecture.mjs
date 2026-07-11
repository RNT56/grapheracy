import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const failures = [];

async function read(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

async function sourceFiles(relativeDir, suffixes) {
  const entries = await readdir(path.join(root, relativeDir), { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const relativePath = path.join(relativeDir, entry.name);
    if (entry.isDirectory()) files.push(...(await sourceFiles(relativePath, suffixes)));
    else if (suffixes.some((suffix) => entry.name.endsWith(suffix))) files.push(relativePath);
  }
  return files;
}

const boundedLegacyFiles = {
  "apps/web/src/App.tsx": 6000,
  "apps/web/src/GraphCanvas.tsx": 1500,
  "services/api/src/graphview_api/main.py": 220,
  "services/api/src/graphview_api/api_v1/router.py": 60,
  "services/api/src/graphview_api/repository.py": 5250
};

for (const [relativePath, maximumLines] of Object.entries(boundedLegacyFiles)) {
  const lineCount = (await read(relativePath)).split("\n").length;
  if (lineCount > maximumLines) {
    failures.push(`${relativePath} grew to ${lineCount} lines; legacy ceiling is ${maximumLines}`);
  }
}

for (const relativePath of await sourceFiles("services/api/src/graphview_api", [".py"])) {
  const basename = path.basename(relativePath);
  if (basename.startsWith("repository") || basename === "connector_state.py" || basename === "db.py" || basename === "demo_seed.py") continue;
  const source = await read(relativePath);
  if (/\bconn\.execute\(|\bengine\.begin\(/.test(source)) {
    failures.push(`${relativePath} performs SQL outside a repository/persistence module`);
  }
}

for (const relativePath of await sourceFiles("apps/web/src", [".ts", ".tsx"])) {
  if (relativePath.endsWith("App.tsx")) continue;
  const source = await read(relativePath);
  if (/from ["'][^"']*demo\//.test(source)) {
    failures.push(`${relativePath} imports demo fixtures from a production module`);
  }
}

const requiredBoundaries = [
  "packages/shared-types/src/index.ts",
  "packages/graph-core/src/index.ts",
  "services/api/openapi.yaml",
  "services/api/src/graphview_api/api_v1/action_dependencies.py",
  "services/api/src/graphview_api/api_v1/action_router.py",
  "services/api/src/graphview_api/api_v1/action_service.py",
  "services/api/src/graphview_api/api_v1/connector_dependencies.py",
  "services/api/src/graphview_api/api_v1/connector_router.py",
  "services/api/src/graphview_api/api_v1/connector_service.py",
  "services/api/src/graphview_api/api_v1/graph_dependencies.py",
  "services/api/src/graphview_api/api_v1/graph_router.py",
  "services/api/src/graphview_api/api_v1/job_dependencies.py",
  "services/api/src/graphview_api/api_v1/job_router.py",
  "services/api/src/graphview_api/api_v1/job_service.py",
  "services/api/src/graphview_api/api_v1/upload_dependencies.py",
  "services/api/src/graphview_api/api_v1/upload_router.py",
  "services/api/src/graphview_api/api_v1/upload_service.py",
  "services/api/src/graphview_api/actions/repository.py",
  "services/api/src/graphview_api/actions/router.py",
  "services/api/src/graphview_api/actions/service.py",
  "services/api/src/graphview_api/agent_context/repository.py",
  "services/api/src/graphview_api/agent_context/router.py",
  "services/api/src/graphview_api/agent_context/service.py",
  "services/api/src/graphview_api/ai/retrieval_router.py",
  "services/api/src/graphview_api/ai/retrieval_service.py",
  "services/api/src/graphview_api/ai/repository.py",
  "services/api/src/graphview_api/ai/router.py",
  "services/api/src/graphview_api/ai/service.py",
  "services/api/src/graphview_api/ai/tools_router.py",
  "services/api/src/graphview_api/ai/tools_service.py",
  "services/api/src/graphview_api/attention/repository.py",
  "services/api/src/graphview_api/attention/router.py",
  "services/api/src/graphview_api/attention/service.py",
  "services/api/src/graphview_api/connector_repository.py",
  "services/api/src/graphview_api/connector_routes.py",
  "services/api/src/graphview_api/connector_service.py",
  "services/api/src/graphview_api/graph/repository.py",
  "services/api/src/graphview_api/graph/router.py",
  "services/api/src/graphview_api/graph/service.py",
  "services/api/src/graphview_api/operations/data_router.py",
  "services/api/src/graphview_api/operations/repository.py",
  "services/api/src/graphview_api/operations/readiness.py",
  "services/api/src/graphview_api/operations/service.py",
  "services/api/src/graphview_api/review/repository.py",
  "services/api/src/graphview_api/review/router.py",
  "services/api/src/graphview_api/review/service.py",
  "services/api/src/graphview_api/repository_sources.py",
  "services/api/src/graphview_api/repository_graph.py",
  "services/api/src/graphview_api/sources/repository.py",
  "services/api/src/graphview_api/sources/router.py",
  "services/api/src/graphview_api/sources/service.py",
  "docs/14-graphview-1.0-upgrade-ledger.md"
];
for (const relativePath of requiredBoundaries) {
  try {
    await read(relativePath);
  } catch {
    failures.push(`required architecture boundary is missing: ${relativePath}`);
  }
}

const apiAssembly = await read("services/api/src/graphview_api/main.py");
if (apiAssembly.includes('"/agent-context/')) {
  failures.push("agent-context routes must remain inside the bounded agent_context module");
}

const boundedRoutePrefixes = [
  ["actions", ['"/action-', '"/decision-records"', '"/outcomes"', '"/feedback-events"']],
  ["ai", ['"/providers"', '"/planning-sessions"', '"/agent-tool-calls"', '"/graph/query"', '"/graph/research"']],
  ["attention", ['"/signals"', '"/observations"', '"/alerts"', '"/attention"', '"/owners"', '"/routing-policies"']],
  ["connector", ['"/connectors"', '"/connector-accounts"', '"/connector-targets"', '"/connector-sync-runs"']],
  ["graph", ['"/graph"', '"/graphs"', '"/insights"', '"/extraction-lenses"', '"/graph-lenses"']],
  ["operations", ['"/search"', '"/export"', '"/backup"', '"/restore"', '"/import"']],
  ["review", ['"/proposals"', '"/review-']],
  ["sources", ['"/sources"', '"/source-chunks"', '"/lineage/', '"/ingestion-runs"']]
];
for (const [moduleName, routePrefixes] of boundedRoutePrefixes) {
  if (routePrefixes.some((routePrefix) => apiAssembly.includes(routePrefix))) {
    failures.push(`${moduleName} routes must remain inside their bounded router module`);
  }
}

const graphRouter = await read("services/api/src/graphview_api/graph/router.py");
if (graphRouter.includes("GraphRepository") || graphRouter.includes("repository.")) {
  failures.push("graph router must call GraphService rather than the persistence repository");
}

const v1GraphRouter = await read("services/api/src/graphview_api/api_v1/graph_router.py");
if (v1GraphRouter.includes("GraphRepository") || v1GraphRouter.includes("repository.")) {
  failures.push("V1 graph router must call GraphProjectionService rather than the persistence repository");
}

const v1JobRouter = await read("services/api/src/graphview_api/api_v1/job_router.py");
if (v1JobRouter.includes("GraphRepository") || v1JobRouter.includes("JobRepository") || v1JobRouter.includes("repository.")) {
  failures.push("V1 job routers must call JobService rather than persistence repositories");
}

const v1UploadRouter = await read("services/api/src/graphview_api/api_v1/upload_router.py");
if (v1UploadRouter.includes("GraphRepository") || v1UploadRouter.includes("JobRepository") || v1UploadRouter.includes("repository.")) {
  failures.push("V1 upload router must call UploadService rather than persistence repositories");
}

const v1ActionRouter = await read("services/api/src/graphview_api/api_v1/action_router.py");
if (v1ActionRouter.includes("GraphRepository") || v1ActionRouter.includes("JobRepository") || v1ActionRouter.includes("repository.")) {
  failures.push("V1 action router must call V1ActionService rather than persistence repositories");
}

const v1ConnectorRouter = await read("services/api/src/graphview_api/api_v1/connector_router.py");
if (v1ConnectorRouter.includes("GraphRepository") || v1ConnectorRouter.includes("JobRepository") || v1ConnectorRouter.includes("repository.")) {
  failures.push("V1 connector router must call V1ConnectorService rather than persistence repositories");
}

const v1Assembly = await read("services/api/src/graphview_api/api_v1/router.py");
if (v1Assembly.includes("@router.") || v1Assembly.includes("GraphRepository") || v1Assembly.includes("repository.")) {
  failures.push("V1 API assembly must remain dependency wiring and router registration only");
}

const sourcesRouter = await read("services/api/src/graphview_api/sources/router.py");
if (sourcesRouter.includes("GraphRepository") || sourcesRouter.includes("repository.")) {
  failures.push("sources router must call SourcesService rather than the persistence repository");
}

const connectorRouter = await read("services/api/src/graphview_api/connector_routes.py");
if (connectorRouter.includes("GraphRepository") || connectorRouter.includes("repository.")) {
  failures.push("connector router must call ConnectorService rather than the persistence repository");
}

const reviewRouter = await read("services/api/src/graphview_api/review/router.py");
if (reviewRouter.includes("GraphRepository") || reviewRouter.includes("repository.")) {
  failures.push("review router must call ReviewService rather than the persistence repository");
}

const actionsRouter = await read("services/api/src/graphview_api/actions/router.py");
if (actionsRouter.includes("GraphRepository") || actionsRouter.includes("repository.")) {
  failures.push("actions router must call ActionsService rather than the persistence repository");
}

const attentionRouter = await read("services/api/src/graphview_api/attention/router.py");
if (attentionRouter.includes("GraphRepository") || attentionRouter.includes("repository.")) {
  failures.push("attention router must call AttentionService rather than the persistence repository");
}

const dataOperationsRouter = await read("services/api/src/graphview_api/operations/data_router.py");
if (dataOperationsRouter.includes("GraphRepository") || dataOperationsRouter.includes("repository.")) {
  failures.push("data operations router must call DataOperationsService rather than the persistence repository");
}

const agentContextRouter = await read("services/api/src/graphview_api/agent_context/router.py");
if (agentContextRouter.includes("GraphRepository") || agentContextRouter.includes("repository.")) {
  failures.push("agent context router must call AgentContextService rather than the persistence repository");
}

const planningRouter = await read("services/api/src/graphview_api/ai/router.py");
if (planningRouter.includes("GraphRepository") || planningRouter.includes("repository.")) {
  failures.push("planning router must call PlanningService rather than the persistence repository");
}

const agentToolsRouter = await read("services/api/src/graphview_api/ai/tools_router.py");
if (agentToolsRouter.includes("GraphRepository") || agentToolsRouter.includes("repository.")) {
  failures.push("agent tools router must call AgentToolsService rather than the persistence repository");
}

const retrievalRouter = await read("services/api/src/graphview_api/ai/retrieval_router.py");
if (retrievalRouter.includes("GraphRepository") || retrievalRouter.includes("repository.")) {
  failures.push("retrieval router must call RetrievalService rather than the persistence repository");
}

if (failures.length) {
  console.error("Architecture check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Architecture check passed.");
