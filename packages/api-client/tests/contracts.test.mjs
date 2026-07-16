import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("generated API schema exposes the canonical V1 projection routes", async () => {
  const schema = await readFile(new URL("../src/schema.ts", import.meta.url), "utf8");
  for (const route of ["/api/v1/graphs/{graph_id}/viewport", "/api/v1/jobs", "/api/v1/auth/session"]) {
    assert.match(schema, new RegExp(route.replace(/[{}]/g, "\\$&")));
  }
});
