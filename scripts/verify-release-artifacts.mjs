import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const root = process.cwd();
const directory = path.resolve(process.argv[2] || "dist/release");
const manifest = JSON.parse(await readFile(path.join(directory, "release-manifest.json"), "utf8"));
const manifestBytes = await readFile(path.join(directory, "release-manifest.json"));
const rootPackage = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
const sums = new Map(
  (await readFile(path.join(directory, "SHA256SUMS"), "utf8"))
    .trim()
    .split("\n")
    .map((line) => {
      const [digest, name] = line.split(/\s{2}/, 2);
      return [name, digest];
    }),
);

if (manifest.schema_version !== 1 || manifest.product !== "Graphview") throw new Error("Invalid release manifest identity");
if (manifest.version !== rootPackage.version) throw new Error("Release manifest version does not match the workspace");
const commit = (await execFileAsync("git", ["rev-parse", "HEAD"], { cwd: root })).stdout.trim();
if (manifest.git_commit !== commit) throw new Error("Release manifest commit does not match HEAD");
if (!Array.isArray(manifest.artifacts) || manifest.artifacts.length !== 3) throw new Error("Release manifest must cover three client artifacts");
const manifestDigest = createHash("sha256").update(manifestBytes).digest("hex");
if (sums.get("release-manifest.json") !== manifestDigest) throw new Error("Release manifest checksum does not match");

for (const artifact of manifest.artifacts) {
  if (!/^[A-Za-z0-9@._+-]+$/.test(artifact.name)) throw new Error(`Unsafe artifact name: ${artifact.name}`);
  const filePath = path.join(directory, artifact.name);
  const digest = createHash("sha256").update(await readFile(filePath)).digest("hex");
  const size = (await stat(filePath)).size;
  if (digest !== artifact.sha256 || digest !== sums.get(artifact.name)) throw new Error(`Checksum mismatch: ${artifact.name}`);
  if (size !== artifact.bytes) throw new Error(`Size mismatch: ${artifact.name}`);
}

const extension = manifest.artifacts.find((artifact) => artifact.name.endsWith(".vsix"));
const gateway = manifest.artifacts.find((artifact) => artifact.name.endsWith(".tgz"));
const sbom = manifest.artifacts.find((artifact) => artifact.name.endsWith(".spdx.json"));
if (!extension || !gateway || !sbom) throw new Error("Release artifacts are missing VSIX, gateway package, or SPDX SBOM");

await execFileAsync("unzip", ["-tqq", path.join(directory, extension.name)]);
const extensionFiles = (await execFileAsync("unzip", ["-Z1", path.join(directory, extension.name)])).stdout.split("\n");
for (const required of ["[Content_Types].xml", "extension.vsixmanifest", "extension/package.json", "extension/src/extension.mjs"]) {
  if (!extensionFiles.includes(required)) throw new Error(`VSIX is missing ${required}`);
}
const gatewayFiles = (await execFileAsync("tar", ["-tzf", path.join(directory, gateway.name)])).stdout.split("\n");
for (const required of ["package/package.json", "package/README.md", "package/src/index.mjs"]) {
  if (!gatewayFiles.includes(required)) throw new Error(`Gateway package is missing ${required}`);
}
const sbomDocument = JSON.parse(await readFile(path.join(directory, sbom.name), "utf8"));
const lockfile = await readFile(path.join(root, "pnpm-lock.yaml"), "utf8");
const lockedPackageCount = [
  ...(lockfile.match(/^packages:\n([\s\S]*?)^snapshots:/m)?.[1] || "").matchAll(
    /^  (?:'([^']+)'|([^' \n][^:\n]*)):\s*$/gm,
  ),
].length;
if (sbomDocument.spdxVersion !== "SPDX-2.3" || sbomDocument.packages.length !== lockedPackageCount + 2) {
  throw new Error("Client artifact SBOM does not contain the complete pnpm lockfile inventory");
}
const lockDigest = createHash("sha256").update(lockfile).digest("hex");
if (!sbomDocument.annotations?.some((annotation) => annotation.comment?.includes(`sha256=${lockDigest}`))) {
  throw new Error("Client artifact SBOM is not bound to the current pnpm lockfile");
}

console.log("Release artifact verification passed: package structure, SBOM, manifest, commit, sizes, and SHA-256 checksums match.");
