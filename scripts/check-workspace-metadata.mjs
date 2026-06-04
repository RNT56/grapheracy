import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const failures = [];

async function exists(file) {
  try {
    await stat(path.join(root, file));
    return true;
  } catch {
    return false;
  }
}

const requiredDirs = [
  "apps/web",
  "apps/docs-app",
  "services/api",
  "services/worker",
  "packages/shared-types",
  "packages/graph-core",
  "packages/design-system",
  "docs/adr",
  "docs/changelog/unreleased",
  "docs/rituals",
  "prototypes",
  "infra/docker",
  "infra/compose",
  ".github/workflows"
];

for (const dir of requiredDirs) {
  if (!(await exists(dir))) failures.push(`${dir} is missing`);
}

const prototype = "prototypes/knowledge-graph-explorer.html";
if (!(await exists(prototype))) failures.push(`${prototype} is missing`);

const rootPackage = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
if (rootPackage.packageManager !== "pnpm@10.27.0") {
  failures.push("packageManager must be pnpm@10.27.0");
}

const workspacePackages = [
  "apps/web/package.json",
  "apps/docs-app/package.json",
  "services/api/package.json",
  "services/worker/package.json",
  "packages/shared-types/package.json",
  "packages/graph-core/package.json",
  "packages/design-system/package.json"
];

for (const file of workspacePackages) {
  const pkg = JSON.parse(await readFile(path.join(root, file), "utf8"));
  if (!pkg.private) failures.push(`${file} must be private`);
  if (!pkg.scripts?.typecheck) failures.push(`${file} missing typecheck script`);
  if (!pkg.scripts?.test) failures.push(`${file} missing test script`);
}

const adrFiles = (await readdir(path.join(root, "docs/adr"))).filter((file) => /^2026-06-04-.+\.md$/.test(file));
if (adrFiles.length < 5) failures.push("expected at least five Phase 1 ADRs");

if (failures.length > 0) {
  console.error("Workspace metadata check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Workspace metadata check passed.");
