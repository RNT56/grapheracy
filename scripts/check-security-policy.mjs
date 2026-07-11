import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const failures = [];

async function mustExist(file) {
  try {
    await stat(path.join(root, file));
  } catch {
    failures.push(`${file} is missing`);
  }
}

await Promise.all([
  mustExist(".npmrc"),
  mustExist(".env.example"),
  mustExist(".gitleaks.toml"),
  mustExist("SECURITY.md"),
  mustExist("docs/03-security.md"),
  mustExist(".github/workflows/security.yml"),
  mustExist(".github/renovate.json"),
  mustExist("infra/docker/minio-healthcheck.go"),
  mustExist("infra/docker/otelcol-builder.yaml")
]);

const workspace = await readFile(path.join(root, "pnpm-workspace.yaml"), "utf8");
const npmrc = await readFile(path.join(root, ".npmrc"), "utf8");
const security = await readFile(path.join(root, "docs/03-security.md"), "utf8");
const gitignore = await readFile(path.join(root, ".gitignore"), "utf8");
const containerFiles = [
  "api.Dockerfile",
  "clamav.Dockerfile",
  "keycloak.Dockerfile",
  "minio.Dockerfile",
  "ops.Dockerfile",
  "otel-collector.Dockerfile",
  "web.Dockerfile",
  "worker.Dockerfile"
];
const containers = Object.fromEntries(
  await Promise.all(
    containerFiles.map(async (file) => [file, await readFile(path.join(root, "infra/docker", file), "utf8")])
  )
);
const productionCompose = await readFile(path.join(root, "infra/compose/docker-compose.production.yml"), "utf8");

const requiredWorkspace = [
  "minimumReleaseAge: 1440",
  "minimumReleaseAgeStrict: true",
  "minimumReleaseAgeIgnoreMissingTime: false",
  "trustPolicy: no-downgrade",
  "blockExoticSubdeps: true"
];

for (const text of requiredWorkspace) {
  if (!workspace.includes(text)) failures.push(`pnpm-workspace.yaml missing ${text}`);
}

if (!npmrc.includes("ignore-scripts=true")) {
  failures.push(".npmrc must deny lifecycle scripts by default");
}

if (!gitignore.includes(".env") || !gitignore.includes("!.env.example")) {
  failures.push(".gitignore must ignore local env files while keeping .env.example");
}

for (const phrase of ["OSV", "gitleaks", "SBOM", "Triage SLA", "Dependency Approval Checklist"]) {
  if (!security.includes(phrase) && !(phrase === "Triage SLA" && (await readFile(path.join(root, "SECURITY.md"), "utf8")).includes(phrase))) {
    failures.push(`security docs missing ${phrase}`);
  }
}

for (const [file, body] of Object.entries(containers)) {
  if (/^FROM\s+\S+:latest(?:\s|$)/m.test(body)) failures.push(`${file} must not use a mutable latest base`);
  for (const line of body.split("\n")) {
    if (/^ADD\s+/.test(line) && /https:\/\//.test(line) && !line.includes("--checksum=sha256:")) {
      failures.push(`${file} remote ADD must include a SHA-256 checksum`);
    }
  }
}

for (const file of ["api.Dockerfile", "worker.Dockerfile"]) {
  for (const required of ["python:3.14.6-slim-bookworm", "apt-get upgrade --yes", "pip==26.1.2"]) {
    if (!containers[file].includes(required)) failures.push(`${file} missing hardened runtime requirement ${required}`);
  }
}
for (const file of ["web.Dockerfile", "clamav.Dockerfile"]) {
  if (!containers[file].includes("apk upgrade --no-cache")) failures.push(`${file} must upgrade the final Alpine package set`);
}
for (const file of ["minio.Dockerfile", "ops.Dockerfile", "otel-collector.Dockerfile"]) {
  if (!containers[file].includes("golang:1.26.5-bookworm")) failures.push(`${file} must use the patched Go toolchain`);
}
for (const required of ["jackson-databind/2.21.5", "mssql-jdbc/13.4.0.jre11", "keycloak-admin-cli-*.jar"]) {
  if (!containers["keycloak.Dockerfile"].includes(required)) failures.push(`keycloak.Dockerfile missing ${required}`);
}
for (const required of [
  "github.com/apache/thrift@v0.23.0",
  "filippo.io/edwards25519@v1.1.1",
  "github.com/Azure/go-ntlmssp@v0.1.1",
  "github.com/buger/jsonparser@v1.1.2",
  "github.com/eclipse/paho.mqtt.golang@v1.5.1",
  "github.com/go-jose/go-jose/v4@v4.1.4",
  "github.com/prometheus/prometheus@v0.311.3",
  "go.opentelemetry.io/otel/sdk@v1.43.0",
  "golang.org/x/crypto@v0.52.0",
  "golang.org/x/net@v0.55.0",
  "google.golang.org/grpc@v1.79.3"
]) {
  if (!containers["minio.Dockerfile"].includes(required)) failures.push(`minio.Dockerfile missing ${required}`);
}
if (!productionCompose.includes("image: ${GRAPHVIEW_OPS_IMAGE:?required}")) {
  failures.push("production MinIO initialization must reuse the scanned operations image");
}
for (const forbidden of [
  "minio/minio:RELEASE.2025-09-07T16-13-09Z",
  "minio/mc:RELEASE.2025-08-13T08-35-41Z",
  "otel/opentelemetry-collector-contrib:0.153.0",
  "quay.io/keycloak/keycloak:26.6.4",
  "clamav/clamav:1.4.3"
]) {
  if (`${Object.values(containers).join("\n")}\n${productionCompose}`.includes(forbidden)) {
    failures.push(`production container configuration retains vulnerable pin ${forbidden}`);
  }
}

if (failures.length > 0) {
  console.error("Security policy check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Security policy check passed.");
