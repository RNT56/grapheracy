# Development

## Purpose

Define the supported setup path, stable commands, development adapters, and contribution boundaries for Graphview 1.0.

## Required Tools

- Node 24.
- pnpm 10.27 or newer.
- Python 3.14 managed through uv.
- Docker and Docker Compose for production-reference verification.
- Helm for deployment validation; Kind is installed by the staging workflow.

## Setup

```sh
pnpm install --frozen-lockfile
uv python install 3.14.5
pnpm run quality:fast
```

Use `.env.example` only for local development. SQLite and the authenticated local AEAD secret store are limited
developer adapters; production and acceptance use PostgreSQL, Redis, S3, OIDC, and Vault.

## Stable Commands

| Command | Scope |
| --- | --- |
| `pnpm run quality:fast` | Docs, metadata, Python lint, security policy, licenses, changelog, architecture, generated API drift, types, unit/integration suites, release structure, and production web build. |
| `pnpm run quality:full` | Fast quality plus smoke, integration, browser E2E, performance planning, and artifact cleanup. |
| `pnpm run test:integration` | API, worker, agent gateway, and editor extension contract suites. |
| `pnpm run test:e2e` | Desktop/mobile Playwright coverage, renderer pixels, accessibility, interaction persistence, and screenshot safety. |
| `pnpm run test:performance` | 5k/20k and 20k/50k visible budgets plus 100k/500k client overview planning. |
| `pnpm run security:full` | Policy, license, dependency audit, OSV, secret, and npm integrity/signature checks. |
| `pnpm run release:verify` | Full local quality, security, deployment schema/security, and client artifact verification. |
| `pnpm run test:deployment` | Strict Helm lint, Kubernetes 1.35 schema validation, and manifest security scan. |
| `pnpm run test:migrations:postgres` | Real PostgreSQL migration chain and interrupted-migration rollback rehearsal. |
| `pnpm run test:e2e:live` | Unmocked browser flow against an already running production reference stack. |
| `pnpm run test:compatibility:live` | Exact unversioned and `/api/v1` alias parity replay. |
| `pnpm run test:observability:live` | API-to-worker trace continuity, metric coverage, and telemetry redaction. |
| `pnpm run test:agent-context:live` | Service auth, offline replay, encrypted context, SSE resume, retention, and terminal state. |
| `pnpm run test:secrets:live` | Vault rotation, migration, redaction, and permanent deletion. |
| `pnpm run test:failure-injection:live` | Redis/MinIO loss, readiness, SSE reconnect, webhook replay, and lease recovery. |
| `pnpm run test:performance:live` | OIDC-authenticated PostgreSQL 100k/500k projection p95 proof. |
| `pnpm run test:backup-restore:live` | Destructive physical backup/restore with credential and side-effect neutralization. |
| `pnpm run test:staging:live` | Clean Kind/Helm install, authenticated ingestion, no-op upgrade, and redacted receipt. |
| `pnpm run test:external-canaries` | Protected, secret-backed GitHub/Google/Notion/OpenAI/SMTP/webhook canaries. |

The `*:live` commands require their documented reference environment. CI owns the Compose stack, PostgreSQL service,
and Kind cluster used for authoritative release evidence; do not point destructive or external canaries at production
data.

## Development Surfaces

```sh
pnpm --filter @graphview/web dev
pnpm --filter @graphview/api-contract dev
pnpm --filter @graphview/worker-contract dev
```

Focused package tests are available through pnpm filters. The MCP gateway and VS Code/Cursor adapter are validated with:

```sh
pnpm --filter @graphview/agent-gateway test
pnpm --filter @graphview/vscode-extension test
```

## Architecture Boundaries

- FastAPI routers authenticate, validate, and call application services; routers do not issue SQL.
- Backend modules own router, service, repository port, schema, and transitions for their domain.
- PostgreSQL is the system of record; durable jobs enter Redis/Arq through the transactional outbox.
- Pydantic/OpenAPI is the HTTP source of truth. Run `pnpm run api:generate` only for an intentional contract change and
  commit both `services/api/openapi.yaml` and `packages/api-client/src/schema.ts`.
- TanStack Query owns server state. Zustand owns only ephemeral graph selection, camera, filter, layout, and replay state.
- Feature slices do not import across workspace boundaries; domain-only visual contracts live in shared packages.
- Production source code may not import preserved prototype or demo fixtures.

`pnpm run architecture:check` enforces these constraints, module size ceilings, API assembly ceilings, circular domain
dependencies, generated-client drift boundaries, and forbidden fixture imports.

## Dependency Changes

Do not run casual package upgrades. Use an intentional dependency change, update the pnpm/uv lockfiles, verify current
supported runtimes and security advisories, document new production dependencies in `03-security.md`, and run
`security:full` plus the relevant image scan.

Primary browser dependencies are React, React Router, TanStack Query, Zustand, Graphology, Sigma, and lazy Three.js.
Primary service dependencies are FastAPI/Pydantic, SQLAlchemy/Alembic, Arq, HTTPX, extraction libraries, OpenTelemetry,
and the selected storage/identity clients. Versions are pinned by the workspace catalogs and lockfiles.

## Failure Modes

- A documented command no longer exists in `package.json`.
- Generated API artifacts change without an intentional wire-contract change.
- A router reaches persistence directly or a UI feature becomes a replacement monolith.
- SQLite, seeded-header authentication, local AEAD, Vite preview, or demo fixtures enter a production path.
- A live check is reported from mocked fixtures or from images other than the candidate commit.
- Dependency or runtime changes land without lockfile, security, and image verification.
