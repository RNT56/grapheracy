# API Service

Purpose: future FastAPI service for auth, graph data, sources, ingestion runs, proposals, review decisions, and
provenance.

Owner: backend worker.

Entrypoints:

- Contract skeleton: `openapi.yaml`
- App module: `services/api/src/graphview_api`
- Ingestion adapters: `services/api/src/graphview_api/ingestion.py`
- Repository: `services/api/src/graphview_api/repository.py`
- Schemas: `services/api/src/graphview_api/schemas.py`

Commands:

- `pnpm --filter @graphview/api-contract dev`
- `pnpm --filter @graphview/api-contract typecheck`
- `pnpm --filter @graphview/api-contract test`

Environment variables: `POSTGRES_*`, `MINIO_*`, `OIDC_*`, `GRAPHVIEW_API_BASE_URL`, `GRAPHVIEW_ENV`.

Runnable endpoints:

- `GET /graph`
- `GET /sources`
- `POST /sources`
- `PATCH /sources/{source_id}`
- `DELETE /sources/{source_id}`
- `GET /ingestion-runs`
- `POST /ingestion-runs`
- `GET /proposals`
- `POST /proposals`
- `GET /review-decisions`
- `POST /review-decisions`
- `GET /search`
- `GET /export`
- `POST /import`

Test path: `services/api/tests`.

Phase 4 ingestion supports inline text, markdown, backend URL fetch, and PDF text extraction. It writes a source,
ingestion run, reviewable proposals, provenance, and deterministic local embeddings in one repository transaction.

Failure modes: OpenAPI drift, auth adapter mismatch, failed URL/PDF extraction, incomplete provenance persistence, and
migration rollback gaps.
