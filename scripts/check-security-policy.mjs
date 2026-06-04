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
  mustExist(".github/renovate.json")
]);

const workspace = await readFile(path.join(root, "pnpm-workspace.yaml"), "utf8");
const npmrc = await readFile(path.join(root, ".npmrc"), "utf8");
const security = await readFile(path.join(root, "docs/03-security.md"), "utf8");
const gitignore = await readFile(path.join(root, ".gitignore"), "utf8");

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

if (failures.length > 0) {
  console.error("Security policy check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Security policy check passed.");
