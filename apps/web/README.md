# Web App

Purpose: future React 19.2, TypeScript, and Vite 8 product UI for graph exploration, source review, and proposal review.

Owner: frontend worker.

Entrypoints: not implemented in Phase 1.

Commands: planned `pnpm --filter @graphview/web dev`, `build`, `typecheck`, and `test` after Phase 2 scaffolding.

Environment variables:

- `GRAPHVIEW_PUBLIC_BASE_URL`
- `GRAPHVIEW_API_BASE_URL`

Test path: planned `apps/web/src`.

Failure modes: graph rendering performance regressions, stale API contracts, auth adapter mismatch, and provenance UI
omissions.
