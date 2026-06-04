# API Service

Purpose: future FastAPI service for auth, graph data, sources, ingestion runs, proposals, review decisions, and
provenance.

Owner: backend worker.

Entrypoints:

- Contract skeleton: `openapi.yaml`
- Planned app module: `services/api/src/graphview_api`

Commands:

- `pnpm --filter @graphview/api-contract dev`
- `pnpm --filter @graphview/api-contract typecheck`
- `pnpm --filter @graphview/api-contract test`

Environment variables: `POSTGRES_*`, `MINIO_*`, `OIDC_*`, `GRAPHVIEW_API_BASE_URL`, `GRAPHVIEW_ENV`.

Test path: `services/api/tests`.

Failure modes: OpenAPI drift, auth adapter mismatch, incomplete provenance persistence, and migration rollback gaps.
