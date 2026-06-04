# Worker Service

Purpose: future async worker service for source fetching, extraction, analysis, proposal generation, and review-aware
commits.

Owner: worker systems worker.

Entrypoints:

- Worker contract: `worker-contract.md`
- Planned worker module: `services/worker/src/graphview_worker`

Commands: planned `uv run graphview-worker`, `uv run pytest` after Phase 2 scaffolding.

Environment variables: `POSTGRES_*`, `MINIO_*`, `ARQ_REDIS_URL`, `GRAPHVIEW_ENV`.

Test path: planned `services/worker/tests`.

Failure modes: non-idempotent retries, untraceable stages, duplicate proposals, and graph commits without review state.
