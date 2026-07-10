import { access, readFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const failures = [];
const read = async (file) => readFile(path.join(root, file), "utf8");
const packageJson = JSON.parse(await read("package.json"));

for (const command of [
  "quality:fast",
  "quality:full",
  "test:integration",
  "test:e2e",
  "test:performance",
  "security:full",
  "release:verify"
]) {
  if (!packageJson.scripts?.[command]) failures.push(`package.json missing ${command}`);
}
if (Object.keys(packageJson.scripts ?? {}).some((command) => /^phase\d+/.test(command))) {
  failures.push("phase-numbered quality gates remain in package.json");
}

for (const file of [
  "docs/14-graphview-1.0-upgrade-ledger.md",
  "services/api/openapi.yaml",
  "packages/api-client/src/schema.ts",
  "infra/compose/docker-compose.production.yml",
  "infra/helm/graphview/Chart.yaml",
  "infra/scripts/graphview-ops.sh",
  ".github/workflows/ci.yml",
  ".github/workflows/security.yml",
  ".github/workflows/release.yml"
]) {
  try {
    await access(path.join(root, file));
  } catch {
    failures.push(`missing release artifact ${file}`);
  }
}

const architecture = await read("docs/02-architecture.md");
const operations = await read("docs/06-operations.md");
const ledger = await read("docs/14-graphview-1.0-upgrade-ledger.md");
for (const required of ["/api/v1", "PostgreSQL", "Redis", "S3", "OIDC", "Sigma", "Graphology"]) {
  if (!`${architecture}\n${operations}\n${ledger}`.includes(required)) failures.push(`1.0 documentation missing ${required}`);
}
for (const forbidden of ["production stub", "mocked-only critical flow", "seeded authentication fallback in production"]) {
  if (ledger.toLowerCase().includes(`${forbidden}: complete`)) failures.push(`upgrade ledger overclaims ${forbidden}`);
}

if (failures.length) {
  console.error("Release readiness check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}
console.log("Graphview 1.0 release-readiness structure passed.");
