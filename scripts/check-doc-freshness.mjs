import { readFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const requiredDocs = [
  "README.md",
  "CLAUDE.md",
  "CHANGELOG.md",
  "SECURITY.md",
  "docs/00-start-here.md",
  "docs/01-product-goals.md",
  "docs/02-architecture.md",
  "docs/03-security.md",
  "docs/04-development.md",
  "docs/05-testing.md",
  "docs/06-operations.md",
  "docs/07-agent-workflows.md",
  "docs/08-roadmap.md"
];

const requiredSubsystemWords = [
  "Purpose",
  "Owner",
  "Entrypoints",
  "Commands",
  "Environment variables",
  "Test path",
  "Failure modes"
];

const failures = [];

const read = async (file) => readFile(path.join(root, file), "utf8");
const readme = await read("README.md");
const claude = await read("CLAUDE.md");

for (const file of requiredDocs) {
  if (!readme.includes(file) && file !== "README.md") {
    failures.push(`README.md does not link ${file}`);
  }
  if (!claude.includes(file) && !["README.md", "CLAUDE.md", "CHANGELOG.md", "SECURITY.md"].includes(file)) {
    failures.push(`CLAUDE.md does not reference ${file}`);
  }
}

const subsystemDocs = [
  "apps/web/README.md",
  "apps/docs-app/README.md",
  "services/api/README.md",
  "services/worker/README.md",
  "packages/graph-core/README.md",
  "packages/design-system/README.md"
];

for (const file of subsystemDocs) {
  const body = await read(file);
  for (const word of requiredSubsystemWords) {
    if (!body.toLowerCase().includes(word.toLowerCase())) {
      failures.push(`${file} missing ${word}`);
    }
  }
}

const roadmap = await read("docs/08-roadmap.md");
for (const phase of ["Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6"]) {
  if (!roadmap.includes(phase)) failures.push(`roadmap missing ${phase}`);
}

if (failures.length > 0) {
  console.error("Docs freshness check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Docs freshness check passed.");
