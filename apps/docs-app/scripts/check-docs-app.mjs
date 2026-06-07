import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { docsAppNavItems, docsAppRoutes } from "../src/docsIndex.mjs";

const appRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const repoRoot = path.resolve(appRoot, "../..");
const routes = docsAppRoutes();

assert.ok(docsAppNavItems.length >= 12, "docs app navigation should cover the core documentation set");
assert.equal(routes.length, docsAppNavItems.length, "docs app routes should mirror nav items");
assert.equal(new Set(routes.map((route) => route.route)).size, routes.length, "docs app routes should be unique");

for (const item of docsAppNavItems) {
  const filePath = path.resolve(appRoot, item.href);
  assert.ok(filePath.startsWith(repoRoot), `docs app item escapes repo root: ${item.href}`);
  const markdown = await readFile(filePath, "utf8");
  assert.match(markdown, /^# /m, `${item.href} should expose a top-level heading`);
}

console.log(`Docs app contract passed (${docsAppNavItems.length} document route(s)).`);
