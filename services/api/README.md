# API Service

Purpose: future FastAPI service for auth, graph data, sources, ingestion runs, proposals, review decisions, and
provenance.

Owner: backend worker.

Entrypoints:

- Contract skeleton: `openapi.yaml`
- Planned app module: `services/api/src/graphview_api`
- Repository: `services/api/src/graphview_api/repository.py`
- Schemas: `services/api/src/graphview_api/schemas.py`

Commands:

- `pnpm --filter @graphview/api-contract dev`
- `pnpm --filter @graphview/api-contract typecheck`
- `pnpm --filter @graphview/api-contract test`

Environment variables: `POSTGRES_*`, `MINIO_*`, `OIDC_*`, `GRAPHVIEW_API_BASE_URL`, `GRAPHVIEW_ENV`.

Phase 3 endpoints:

- `GET /graph`
- `GET /sources`
- `POST /sources`
- `PATCH /sources/{source_id}`
- `DELETE /sources/{source_id}`
- `GET /proposals`
- `POST /proposals`
- `GET /review-decisions`
- `POST /review-decisions`
- `GET /search`
- `GET /export`
- `POST /import`

Test path: `services/api/tests`.

Failure modes: OpenAPI drift, auth adapter mismatch, incomplete provenance persistence, and migration rollback gaps.
