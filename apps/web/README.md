# Web App

Purpose: future React 19.2, TypeScript, and Vite 8 product UI for graph exploration, source review, and proposal review.

Owner: frontend worker.

Entrypoints:

- `src/main.tsx`
- `src/App.tsx`
- `src/GraphCanvas.tsx`

Commands:

- `pnpm --filter @graphview/web dev`
- `pnpm --filter @graphview/web build`
- `pnpm --filter @graphview/web typecheck`
- `pnpm --filter @graphview/web test`

Environment variables:

- `GRAPHVIEW_PUBLIC_BASE_URL`
- `GRAPHVIEW_API_BASE_URL`

Test path: `apps/web/tests`.

Failure modes: graph rendering performance regressions, stale API contracts, auth adapter mismatch, and provenance UI
omissions.
