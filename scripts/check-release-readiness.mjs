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
  "test:performance:live",
  "test:failure-injection:live",
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
  "scripts/build-release-artifacts.mjs",
  "scripts/verify-release-artifacts.mjs",
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

for (const command of ["release:artifacts", "release:artifacts:verify"]) {
  if (!packageJson.scripts?.[command]) failures.push(`package.json missing ${command}`);
}

const versionFiles = [
  "apps/docs-app/package.json",
  "apps/vscode-extension/package.json",
  "apps/web/package.json",
  "packages/api-client/package.json",
  "packages/design-system/package.json",
  "packages/graph-core/package.json",
  "packages/shared-types/package.json",
  "services/agent-gateway/package.json",
  "services/api/package.json",
  "services/worker/package.json"
];
for (const file of versionFiles) {
  const document = JSON.parse(await read(file));
  if (document.version !== packageJson.version) failures.push(`${file} version differs from root package.json`);
}
for (const file of ["pyproject.toml", "services/api/pyproject.toml", "services/worker/pyproject.toml"]) {
  const match = (await read(file)).match(/^version = "([^"]+)"/m);
  if (match?.[1] !== packageJson.version) failures.push(`${file} version differs from root package.json`);
}

const architecture = await read("docs/02-architecture.md");
const operations = await read("docs/06-operations.md");
const ledger = await read("docs/14-graphview-1.0-upgrade-ledger.md");
const ciWorkflow = await read(".github/workflows/ci.yml");
const releaseWorkflow = await read(".github/workflows/release.yml");
const composeRealm = JSON.parse(await read("infra/compose/keycloak/graphview-realm.json"));
for (const required of ["/api/v1", "PostgreSQL", "Redis", "S3", "OIDC", "Sigma", "Graphology"]) {
  if (!`${architecture}\n${operations}\n${ledger}`.includes(required)) failures.push(`1.0 documentation missing ${required}`);
}
for (const required of [
  "client-artifacts:",
  "release:artifacts:verify",
  "cosign sign-blob",
  ".verification.verified",
  "subject-path: dist/release/*",
  "image-manifest.json"
]) {
  if (!releaseWorkflow.includes(required)) failures.push(`release workflow missing ${required}`);
}
for (const required of [
  "pnpm run test:failure-injection:live",
  "pnpm run test:performance:live",
  "pnpm run test:backup-restore:live"
]) {
  if (!ciWorkflow.includes(required)) failures.push(`live-stack CI workflow missing ${required}`);
}
const webClient = composeRealm.clients?.find((client) => client.clientId === "graphview-web");
const ciCallback = "http://127.0.0.1:8080/api/v1/auth/callback";
if (!webClient?.redirectUris?.includes(ciCallback)) failures.push(`reference Keycloak realm missing ${ciCallback}`);
if (!webClient?.webOrigins?.includes("http://127.0.0.1:8080")) {
  failures.push("reference Keycloak realm missing the live-stack browser origin");
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
