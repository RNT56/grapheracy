import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("graph-core keeps renderer data typed through RenderableGraph", async () => {
  const source = await readFile(new URL("../src/index.ts", import.meta.url), "utf8");
  assert.match(source, /RenderableGraph/);
  assert.match(source, /setData\(data: RenderableGraph\)/);
});
