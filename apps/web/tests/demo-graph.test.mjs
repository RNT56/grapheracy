import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("iOS 26 Swift demo graph covers native app development areas", async () => {
  const source = await readFile(new URL("../src/demo/ios26SwiftDemoGraph.ts", import.meta.url), "utf8");

  for (const term of [
    "Native iOS 26 Swift App",
    "Xcode 26 and iOS 26 SDK",
    "SwiftUI App Structure",
    "Liquid Glass",
    "SwiftData Persistence",
    "App Intents",
    "Siri, Spotlight, and Apple Intelligence",
    "Swift Testing and XCTest",
    "App Store Connect"
  ]) {
    assert.match(source, new RegExp(term.replaceAll(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  const nodeKeys = new Set([...source.matchAll(/\s+([a-zA-Z][a-zA-Z0-9]*): "node-/g)].map((match) => match[1]));
  const edgeEndpoints = [...source.matchAll(/edge\("[^"]+", n\.([a-zA-Z0-9]+), n\.([a-zA-Z0-9]+),/g)];
  assert.ok(nodeKeys.size >= 28);
  assert.ok(edgeEndpoints.length >= 45);
  for (const [, sourceKey, targetKey] of edgeEndpoints) {
    assert.ok(nodeKeys.has(sourceKey), `missing source node key ${sourceKey}`);
    assert.ok(nodeKeys.has(targetKey), `missing target node key ${targetKey}`);
  }
});

test("web shell defaults to the live iOS 26 Swift graph and keeps an offline fallback", async () => {
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");

  assert.match(appSource, /project-ios26-swift-demo/);
  assert.match(appSource, /\/graphs/);
  assert.match(appSource, /selectedGraphId/);
  assert.match(appSource, /graphScopedPath/);
  assert.match(appSource, /ios26SwiftDemoGraph/);
  assert.match(appSource, /usingDemoGraph/);
  assert.match(appSource, /demoDefaultSourceText/);
  assert.match(appSource, /demoReviewDashboard/);
});
