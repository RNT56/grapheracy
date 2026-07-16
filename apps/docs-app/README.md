# Docs App Contract

Owner: documentation worker.

Purpose: lightweight docs navigation contract that consumes the markdown source of truth from `docs/`.

Entrypoints:

- `src/docsIndex.mjs`
- `scripts/check-docs-app.mjs`

Commands:

- `pnpm --filter @graphview/docs-app typecheck`
- `pnpm --filter @graphview/docs-app test`

Environment variables: none.

Test path: `scripts/check-docs-app.mjs`.

Failure modes: stale markdown links, docs app diverging from repo markdown, or generated docs artifacts committed without
review.
