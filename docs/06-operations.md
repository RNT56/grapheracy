# Operations

## Purpose

Define local and production operational direction without implementing production services in Phase 1.

## Deployment Model

Graphview is container-neutral. Docker Compose is provided for local and development orchestration, while production
containers must be deployable into internal infrastructure without SaaS assumptions.

## Services

- Web app container.
- API container.
- Worker container.
- PostgreSQL 18 with pgvector.
- MinIO for local S3-compatible storage.
- Redis for Arq worker queue if Phase 2 confirms Arq.

## Compose

The development Compose file is `../infra/compose/docker-compose.dev.yml`.

```sh
docker compose -f infra/compose/docker-compose.dev.yml up web api worker postgres redis minio
```

The app services run from the local workspace for development. Production image hardening remains a later phase.

## Environment Matrix

| Variable | Owner | Local default | Secret | Purpose |
| --- | --- | --- | --- | --- |
| `GRAPHVIEW_ENV` | all services | `local` | No | Runtime environment label. |
| `GRAPHVIEW_PUBLIC_BASE_URL` | web | `http://localhost:5173` | No | Browser app base URL. |
| `GRAPHVIEW_API_BASE_URL` | web/api | `http://localhost:8000` | No | API URL. |
| `POSTGRES_*` | api/worker | `.env.example` | Password yes | Database connection. |
| `MINIO_*` | api/worker | `.env.example` | Keys yes | Object storage. |
| `OIDC_*` | api | `.env.example` | Secret yes | Internal SSO adapter. |
| `ARQ_REDIS_URL` | worker | `redis://localhost:6379/0` | No locally | Worker queue. |

## Release Process

1. Consolidate fragments from `docs/changelog/unreleased/` into `CHANGELOG.md`.
2. Run full CI gates.
3. Generate SBOMs for release images.
4. Review security exceptions and dependency changes.
5. Tag a SemVer release after V1 release policy is defined.

## Failure Modes

- Compose diverges from production container assumptions.
- Image layers include secrets.
- Non-root container policy is bypassed.
- SBOM generation is skipped before release.
- Operational docs lag behind environment variables.
