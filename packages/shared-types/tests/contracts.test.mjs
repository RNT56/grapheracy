import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("shared contracts expose required public interfaces", async () => {
  const source = await readFile(new URL("../src/index.ts", import.meta.url), "utf8");
  for (const name of [
    "GraphProject",
    "Topic",
    "Source",
    "ContentNode",
    "SemanticEdge",
    "IngestionRun",
    "ExtractionProposal",
    "ReviewDecision",
    "Provenance"
  ]) {
    assert.match(source, new RegExp(`interface ${name}`));
  }
});
