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
  "services/api/src/graphview_api/main.py": 1650,
  "services/api/src/graphview_api/repository.py": 6200
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
  "docs/14-graphview-1.0-upgrade-ledger.md"
];
for (const relativePath of requiredBoundaries) {
  try {
    await read(relativePath);
  } catch {
    failures.push(`required architecture boundary is missing: ${relativePath}`);
  }
}

if (failures.length) {
  console.error("Architecture check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Architecture check passed.");
