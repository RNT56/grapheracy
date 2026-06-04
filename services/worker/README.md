# Worker Service

Purpose: future async worker service for source fetching, extraction, analysis, proposal generation, and review-aware
commits.

Owner: worker systems worker.

Entrypoints:

- Worker contract: `worker-contract.md`
- Worker module: `services/worker/src/graphview_worker`
- Ingestion primitives: `services/worker/src/graphview_worker/ingestion.py`

Commands:

- `pnpm --filter @graphview/worker-contract dev`
- `pnpm --filter @graphview/worker-contract typecheck`
- `pnpm --filter @graphview/worker-contract test`

Environment variables: `POSTGRES_*`, `MINIO_*`, `ARQ_REDIS_URL`, `GRAPHVIEW_ENV`.

Test path: `services/worker/tests`.

Phase 4 supports deterministic text/markdown/PDF extraction, local hash embeddings, and heuristic content-node proposal
generation. URL fetch runs through the API boundary in this phase; worker URL jobs are still planned for queued
execution.

Failure modes: non-idempotent retries, untraceable stages, duplicate proposals, failed PDF extraction, and graph commits
without review state.
