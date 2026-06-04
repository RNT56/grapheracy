import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("web shell is product-first and wired to API health", async () => {
  const source = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.match(source, /fetchHealth/);
  assert.match(source, /Reviewed knowledge graph/);
  assert.doesNotMatch(source, /hero/i);
});
