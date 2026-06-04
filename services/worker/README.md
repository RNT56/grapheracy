# Worker Service

Purpose: future async worker service for source fetching, extraction, analysis, proposal generation, and review-aware
commits.

Owner: worker systems worker.

Entrypoints:

- Worker contract: `worker-contract.md`
- Planned worker module: `services/worker/src/graphview_worker`

Commands:

- `pnpm --filter @graphview/worker-contract dev`
- `pnpm --filter @graphview/worker-contract typecheck`
- `pnpm --filter @graphview/worker-contract test`

Environment variables: `POSTGRES_*`, `MINIO_*`, `ARQ_REDIS_URL`, `GRAPHVIEW_ENV`.

Test path: `services/worker/tests`.

Failure modes: non-idempotent retries, untraceable stages, duplicate proposals, and graph commits without review state.
