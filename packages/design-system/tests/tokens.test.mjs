import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("design tokens define compact product shell dimensions", async () => {
  const source = await readFile(new URL("../src/index.ts", import.meta.url), "utf8");
  assert.match(source, /sidebarWidth/);
  assert.match(source, /graphPanelMinHeight/);
});
