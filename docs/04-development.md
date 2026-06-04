# Development

## Purpose

Define the documented setup path, commands, environment variables, and local development expectations.

## Required Tools

- Node 24 Active LTS.
- pnpm 10.27 or newer.
- Python 3.14.
- uv.
- Docker and Docker Compose.

## Setup

```sh
pnpm install --frozen-lockfile
uv python install 3.14.5
pnpm run phase4:check
```

## Root Commands

| Command | Status | Purpose |
| --- | --- | --- |
| `pnpm run setup` | Runnable | Install with the committed lockfile. |
| `pnpm run lint` | Runnable | Check markdown links, docs freshness, and workspace metadata. |
| `pnpm run docs:check` | Runnable | Run documentation hygiene checks. |
| `pnpm run changelog:check` | Runnable | Validate changelog and unreleased fragments. |
| `pnpm run security:local` | Runnable | Check repository security policy configuration. |
| `pnpm run security:licenses` | Runnable | Check license policy metadata. |
| `pnpm run security:audit` | Runnable after install | Run pnpm audit at moderate severity. |
| `pnpm run security:signatures` | CI gate | Verify npm registry signatures where package metadata supports it. |
| `pnpm run security:osv` | CI gate | Run OSV-Scanner against the source tree and lockfiles. |
| `pnpm run security:secrets` | CI gate | Run gitleaks secret scanning. |
| `pnpm run typecheck` | Runnable placeholder | Runs package type checks as implementations appear. |
| `pnpm run test` | Runnable placeholder | Runs package tests as implementations appear. |
| `pnpm run phase1:check` | Runnable | Runs the local Phase 1 acceptance checks. |
| `pnpm run phase2:check` | Runnable | Runs local Phase 2 checks and builds the web app. |
| `pnpm run phase3:check` | Runnable | Runs local Phase 3 checks, API workflow tests, and the web build. |
| `pnpm run phase4:check` | Runnable | Runs local Phase 4 ingestion checks, API/worker tests, and the web build. |
| `pnpm --filter @graphview/web dev` | Runnable | Starts the Vite web app on `127.0.0.1:5173`. |
| `pnpm --filter @graphview/api-contract dev` | Runnable | Starts the FastAPI service on `127.0.0.1:8000`. |
| `pnpm --filter @graphview/worker-contract dev` | Runnable | Runs the worker scaffold and prints the stage plan. |

## Environment Variables

Use `.env.example` as the local template. Production values must come from external secret management.

The API defaults to `GRAPHVIEW_DATABASE_URL=sqlite:///./.graphview/graphview.sqlite` for local development. Use a
Postgres URL for shared development or production-like environments.

## Package Additions

Do not run casual package installs. Use a dedicated dependency PR, update the lockfile, and complete the checklist in
`03-security.md`.

## Direct Dependencies

JavaScript direct dependencies are pinned through `pnpm-workspace.yaml`: React, React DOM, React Router, TanStack Query,
Zustand, Vite, the Vite React plugin, React type packages, and TypeScript. Python direct dependencies are locked through
uv for the API and worker: FastAPI, Pydantic Settings, SQLAlchemy, Alembic, Uvicorn, Arq, HTTPX, PyPDF, and Pytest.

HTTPX is a runtime API dependency for backend URL fetch during ingestion. PyPDF is a runtime API and worker dependency
for PDF extraction. Both are covered by `uv.lock` and service tests.

## Failure Modes

- Local Node or pnpm version below policy.
- Missing lockfile review after dependency changes.
- Root commands added without documentation.
- Feature implementation added before Phase 2 scaffolding.
