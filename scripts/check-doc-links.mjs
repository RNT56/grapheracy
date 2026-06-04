import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const ignoredDirs = new Set([".git", "node_modules", ".venv"]);
const failures = [];

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (ignoredDirs.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(full)));
    if (entry.isFile() && entry.name.endsWith(".md")) files.push(full);
  }
  return files;
}

const linkPattern = /(?<!!)\[[^\]]+\]\(([^)]+)\)/g;
const files = await walk(root);

for (const file of files) {
  const body = await readFile(file, "utf8");
  for (const match of body.matchAll(linkPattern)) {
    const target = match[1].trim();
    if (/^(https?:|mailto:|#)/.test(target)) continue;
    const cleanTarget = target.split("#")[0];
    if (cleanTarget.length === 0) continue;
    const resolved = path.resolve(path.dirname(file), cleanTarget);
    try {
      await stat(resolved);
    } catch {
      failures.push(`${path.relative(root, file)} -> ${target}`);
    }
  }
}

if (failures.length > 0) {
  console.error("Broken markdown links:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Markdown link check passed (${files.length} files).`);
