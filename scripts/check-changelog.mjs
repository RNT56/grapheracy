import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const changelog = await readFile(path.join(root, "CHANGELOG.md"), "utf8");

const required = ["# Changelog", "## [Unreleased]", "### Added"];
const missing = required.filter((text) => !changelog.includes(text));

const fragmentDir = path.join(root, "docs/changelog/unreleased");
const fragments = (await readdir(fragmentDir)).filter((file) => file.endsWith(".md"));

if (fragments.length === 0) {
  missing.push("at least one unreleased changelog fragment");
}

for (const fragment of fragments) {
  const body = await readFile(path.join(fragmentDir, fragment), "utf8");
  if (!body.startsWith("---\n")) {
    missing.push(`${fragment} frontmatter`);
  }
  if (!/^type: (added|changed|deprecated|removed|fixed|security)$/m.test(body)) {
    missing.push(`${fragment} allowed type`);
  }
  if (!/^owner: .+/m.test(body)) {
    missing.push(`${fragment} owner`);
  }
}

if (missing.length > 0) {
  console.error("Changelog check failed:");
  for (const item of missing) console.error(`- Missing ${item}`);
  process.exit(1);
}

console.log(`Changelog check passed (${fragments.length} fragment(s)).`);
