import { readFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const failures = [];

const read = async (file) => readFile(path.join(root, file), "utf8");
const packageJson = JSON.parse(await read("package.json"));
const roadmap = await read("docs/08-roadmap.md");
const operations = await read("docs/06-operations.md");
const architecture = await read("docs/02-architecture.md");
const releaseChecklist = await read("docs/rituals/release-checklist.md");
const readme = await read("README.md");

if (!packageJson.scripts?.["phase22:check"]) failures.push("package.json missing phase22:check");
if (!packageJson.scripts?.["phase27:smoke"]) failures.push("package.json missing phase27:smoke");
if (!packageJson.scripts?.["phase27:check"]) failures.push("package.json missing phase27:check");
if (!packageJson.scripts?.["release:check"]) failures.push("package.json missing release:check");
if (!roadmap.includes("## Phase 27: Active Agent Context Connectors\n\nStatus: complete.")) {
  failures.push("roadmap does not mark Phase 27 complete");
}
if (!roadmap.includes("## Phase 22: Provider Completion and Release Hardening\n\nStatus: complete.")) {
  failures.push("roadmap does not mark Phase 22 complete");
}
if (!roadmap.includes("## Phase 18: Durable AI Foundation\n\nStatus: complete.")) {
  failures.push("roadmap does not mark Phase 18 complete");
}
if (!roadmap.includes("## Phase 17: Connector Ingestion and Graph Building\n\nStatus: complete.")) {
  failures.push("roadmap does not mark Phase 17 complete");
}
if (!roadmap.includes("## Phase 16: Full Graph Workspace UI\n\nStatus: complete.")) {
  failures.push("roadmap does not mark Phase 16 complete");
}

for (const text of [
  "pnpm run phase22:check",
  "pnpm run phase27:smoke",
  "pnpm run phase27:check",
  "pnpm run release:check",
  "/observability/ready",
  "/observability/metrics",
  "/providers",
  "/planning-sessions",
  "/agent-runs",
  "/graph/query",
  "/graph/research",
  "/connectors",
  "/connector-targets",
  "/connector-sync-runs",
  "/source-chunks",
  "/review-sources",
  "/review-activity",
  "/review-dashboard",
  "/review-queue",
  "/graph/path",
  "/graph/neighborhood",
  "/insights",
  "/extraction-lenses",
  "/graph-lenses",
  "/backup",
  "/restore",
  "/agent-context/sessions",
  "/agent-context/events/batch"
]) {
  if (!operations.includes(text)) failures.push(`operations doc missing ${text}`);
}

for (const text of [
  "pnpm run phase22:check",
  "pnpm run phase27:smoke",
  "pnpm run phase27:check",
  "pnpm run release:check",
  "backup",
  "restore",
  "observability",
  "/providers",
  "/graph/query",
  "/graph/research",
  "approve-action",
  "/review-sources",
  "/review-activity",
  "/review-dashboard",
  "/review-queue",
  "/graph/path",
  "/graph/neighborhood",
  "/insights",
  "/extraction-lenses",
  "/graph-lenses",
  "/agent-context/sessions",
  "/agent-context/events/batch"
]) {
  if (!releaseChecklist.toLowerCase().includes(text.toLowerCase())) {
    failures.push(`release checklist missing ${text}`);
  }
}

for (const text of [
  "Knowledge Graph Builder",
  "AI-native planning",
  "provider catalog",
  "graph Q&A",
  "scoped research",
  "connector-backed graph building",
  "active agent context",
  "full graph workspace",
  "/providers",
  "/planning-sessions",
  "/graph/query",
  "/graph/research",
  "/connectors",
  "/connector-targets",
  "/connector-sync-runs",
  "/source-chunks",
  "/extraction-lenses",
  "/graph-lenses",
  "/agent-context/sessions",
  "/agent-context/events/batch",
  "/lineage",
  "/insights",
  "/review-sources",
  "/review-activity",
  "/review-dashboard",
  "/review-queue",
  "/graph/path",
  "/graph/neighborhood",
  "Engineering",
  "Ops",
  "semantic_edge"
]) {
  if (!architecture.includes(text)) failures.push(`architecture doc missing ${text}`);
}

if (!readme.includes("Phase 22")) failures.push("README does not describe Phase 22 state");
if (!readme.includes("Planning Mode")) failures.push("README does not describe Planning Mode");

if (failures.length > 0) {
  console.error("Release readiness check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Release readiness check passed.");
