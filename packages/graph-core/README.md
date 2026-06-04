# Graph Core

Purpose: typed graph model helpers and the Canvas/WebGL rendering abstraction boundary.

Owner: graph rendering worker.

Entrypoints: `packages/graph-core/src`.

Commands: `pnpm --filter @graphview/graph-core typecheck` and `pnpm --filter @graphview/graph-core test`.

Environment variables: none.

Test path: `packages/graph-core/tests`.

Failure modes: renderer lock-in before evaluation, large-graph performance regressions, and graph model drift from shared
contracts.
