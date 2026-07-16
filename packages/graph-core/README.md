# Graph Core

Purpose: typed graph model helpers and the Canvas/WebGL rendering abstraction boundary.

Owner: graph rendering worker.

Entrypoints: `packages/graph-core/src`.

Commands: `pnpm --filter @graphview/graph-core typecheck` and `pnpm --filter @graphview/graph-core test`.

Environment variables: none.

Test path: `packages/graph-core/tests`.

Phase 10 adds deterministic focused-neighborhood extraction for reviewed graph exploration.
Phase 11 adds deterministic bounded shortest-path extraction for reviewed graph exploration.

Phase 5 exposes `planGraphRender` and `DEFAULT_GRAPH_RENDER_LIMITS` so renderers can cap large graph payloads,
remove orphan edges, keep layout deterministic, and report omitted nodes and edges.

Failure modes: renderer lock-in before evaluation, large-graph performance regressions, and graph model drift from shared
contracts.
