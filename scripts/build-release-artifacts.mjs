import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { cp, mkdir, readFile, readdir, rm, stat, utimes, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const root = process.cwd();
const outputDirectory = path.resolve(process.argv[2] || "dist/release");
const rootPackage = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
const gatewayPackagePath = path.join(root, "services/agent-gateway/package.json");
const extensionPackagePath = path.join(root, "apps/vscode-extension/package.json");
const gatewayPackage = JSON.parse(await readFile(gatewayPackagePath, "utf8"));
const extensionPackage = JSON.parse(await readFile(extensionPackagePath, "utf8"));
const lockfile = await readFile(path.join(root, "pnpm-lock.yaml"), "utf8");
const version = rootPackage.version;

if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error(`Release version is not stable SemVer: ${version}`);
for (const [name, document] of [["gateway", gatewayPackage], ["extension", extensionPackage]]) {
  if (document.version !== version) throw new Error(`${name} version ${document.version} does not match root ${version}`);
}

await rm(outputDirectory, { recursive: true, force: true });
await mkdir(outputDirectory, { recursive: true });

await execFileAsync(
  "pnpm",
  ["pack", "--pack-destination", outputDirectory],
  { cwd: path.dirname(gatewayPackagePath) },
);
const gatewayArchiveName = (await readdir(outputDirectory)).find((name) => name.endsWith(".tgz"));
if (!gatewayArchiveName) throw new Error("Gateway package archive was not created");

const extensionStage = path.join(outputDirectory, ".extension-stage");
const extensionRoot = path.join(extensionStage, "extension");
await mkdir(path.join(extensionRoot, "src"), { recursive: true });
await cp(path.join(root, "apps/vscode-extension/src/extension.mjs"), path.join(extensionRoot, "src/extension.mjs"));
await cp(path.join(root, "apps/vscode-extension/README.md"), path.join(extensionRoot, "README.md"));
const installableExtensionPackage = {
  ...extensionPackage,
  name: "graphview-active-context",
  version,
};
delete installableExtensionPackage.private;
delete installableExtensionPackage.devDependencies;
delete installableExtensionPackage.scripts;
delete installableExtensionPackage.files;
await writeFile(
  path.join(extensionRoot, "package.json"),
  `${JSON.stringify(installableExtensionPackage, null, 2)}\n`,
);
await writeFile(
  path.join(extensionStage, "[Content_Types].xml"),
  `<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="mjs" ContentType="application/javascript" />
  <Default Extension="md" ContentType="text/markdown" />
  <Default Extension="vsixmanifest" ContentType="text/xml" />
</Types>
`,
);
await writeFile(
  path.join(extensionStage, "extension.vsixmanifest"),
  `<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="graphview-active-context" Version="${xml(version)}" Publisher="${xml(extensionPackage.publisher)}" />
    <DisplayName>${xml(extensionPackage.displayName)}</DisplayName>
    <Description xml:space="preserve">${xml(extensionPackage.description)}</Description>
    <Categories>Other</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="${xml(extensionPackage.engines.vscode)}" />
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code" /></Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
  </Assets>
</PackageManifest>
`,
);
await normalizeTimestamps(extensionStage);
const extensionArchiveName = `graphview-active-context-${version}.vsix`;
await execFileAsync(
  "zip",
  ["-X", "-q", "-r", path.join(outputDirectory, extensionArchiveName), "[Content_Types].xml", "extension.vsixmanifest", "extension"],
  { cwd: extensionStage },
);
await rm(extensionStage, { recursive: true, force: true });

const generatedAt = new Date(Number(process.env.SOURCE_DATE_EPOCH || 0) * 1000 || Date.now()).toISOString();
const commit = (await execFileAsync("git", ["rev-parse", "HEAD"], { cwd: root })).stdout.trim();
const dependencyPackages = lockfilePackages(lockfile).map(({ name, version: dependencyVersion }, index) => ({
  name,
  SPDXID: `SPDXRef-Dependency-${index + 1}`,
  versionInfo: dependencyVersion,
  downloadLocation: "NOASSERTION",
  filesAnalyzed: false,
  licenseConcluded: "NOASSERTION",
  licenseDeclared: "NOASSERTION",
  copyrightText: "NOASSERTION",
  externalRefs: [{ referenceCategory: "PACKAGE-MANAGER", referenceType: "purl", referenceLocator: npmPurl(name, dependencyVersion) }],
}));
const sbomName = `graphview-client-artifacts-${version}.spdx.json`;
const sbom = {
  spdxVersion: "SPDX-2.3",
  dataLicense: "CC0-1.0",
  SPDXID: "SPDXRef-DOCUMENT",
  name: `Graphview client artifacts ${version}`,
  documentNamespace: `https://graphview.local/spdx/${commit}/${version}`,
  creationInfo: { created: generatedAt, creators: ["Tool: graphview-release-builder"] },
  packages: [
    spdxPackage("Graphview agent gateway", "SPDXRef-Gateway", gatewayPackage.name, version),
    spdxPackage("Graphview Active Context extension", "SPDXRef-Extension", "graphview-active-context", version),
    ...dependencyPackages,
  ],
  relationships: [
    { spdxElementId: "SPDXRef-DOCUMENT", relationshipType: "DESCRIBES", relatedSpdxElement: "SPDXRef-Gateway" },
    { spdxElementId: "SPDXRef-DOCUMENT", relationshipType: "DESCRIBES", relatedSpdxElement: "SPDXRef-Extension" },
    ...dependencyPackages.map((item) => ({ spdxElementId: "SPDXRef-DOCUMENT", relationshipType: "DESCRIBES", relatedSpdxElement: item.SPDXID })),
  ],
  annotations: [{
    annotationDate: generatedAt,
    annotationType: "OTHER",
    annotator: "Tool: graphview-release-builder",
    comment: `Complete pnpm lockfile inventory; sha256=${createHash("sha256").update(lockfile).digest("hex")}`,
  }],
};
await writeFile(path.join(outputDirectory, sbomName), `${JSON.stringify(sbom, null, 2)}\n`);

const artifactNames = [gatewayArchiveName, extensionArchiveName, sbomName].sort();
const artifacts = [];
for (const name of artifactNames) {
  const filePath = path.join(outputDirectory, name);
  const fileStat = await stat(filePath);
  artifacts.push({ name, bytes: fileStat.size, sha256: await sha256(filePath) });
}
const manifest = {
  schema_version: 1,
  product: "Graphview",
  version,
  git_commit: commit,
  generated_at: generatedAt,
  artifacts,
};
const manifestPath = path.join(outputDirectory, "release-manifest.json");
await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
const checksumEntries = [
  ...artifacts,
  { name: "release-manifest.json", sha256: await sha256(manifestPath) },
];
await writeFile(
  path.join(outputDirectory, "SHA256SUMS"),
  `${checksumEntries.map((artifact) => `${artifact.sha256}  ${artifact.name}`).join("\n")}\n`,
);
console.log(`Built ${artifacts.length} verified release artifacts in ${path.relative(root, outputDirectory)}.`);

function spdxPackage(displayName, spdxId, npmName, packageVersion) {
  return {
    name: displayName,
    SPDXID: spdxId,
    versionInfo: packageVersion,
    downloadLocation: "NOASSERTION",
    filesAnalyzed: false,
    licenseConcluded: "NOASSERTION",
    licenseDeclared: "NOASSERTION",
    copyrightText: "NOASSERTION",
    externalRefs: [{ referenceCategory: "PACKAGE-MANAGER", referenceType: "purl", referenceLocator: npmPurl(npmName, packageVersion) }],
  };
}

function lockfilePackages(document) {
  const packagesSection = document.match(/^packages:\n([\s\S]*?)^snapshots:/m)?.[1];
  if (!packagesSection) throw new Error("pnpm-lock.yaml packages section is missing");
  const packageKeys = [...packagesSection.matchAll(/^  (?:'([^']+)'|([^' \n][^:\n]*)):\s*$/gm)].map(
    (match) => match[1] || match[2],
  );
  if (packageKeys.length === 0) throw new Error("pnpm-lock.yaml package inventory is empty");
  return packageKeys.map((key) => {
    const separator = key.lastIndexOf("@");
    if (separator <= 0 || separator === key.length - 1) throw new Error(`Invalid pnpm package key: ${key}`);
    return { name: key.slice(0, separator), version: key.slice(separator + 1) };
  });
}

function npmPurl(name, packageVersion) {
  const encodedName = name.startsWith("@")
    ? `%40${encodeURIComponent(name.slice(1).split("/")[0])}/${encodeURIComponent(name.split("/").slice(1).join("/"))}`
    : encodeURIComponent(name);
  return `pkg:npm/${encodedName}@${encodeURIComponent(packageVersion)}`;
}

async function sha256(filePath) {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

async function normalizeTimestamps(directory) {
  const fixed = new Date("2000-01-01T00:00:00.000Z");
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) await normalizeTimestamps(entryPath);
    await utimes(entryPath, fixed, fixed);
  }
}

function xml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}
