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

Install dependencies and run the current local acceptance gate:

```sh
pnpm install --frozen-lockfile
uv python install 3.14.5
pnpm run phase26:check
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
| `pnpm run phase5:check` | Runnable | Runs local Phase 5 hardening checks, release readiness validation, and the web build. |
| `pnpm run phase6:check` | Runnable | Runs local Phase 6 mode checks, release readiness validation, and the web build. |
| `pnpm run phase7:check` | Runnable | Runs local Phase 7 relationship proposal checks, release readiness validation, and the web build. |
| `pnpm run phase8:check` | Runnable | Runs local Phase 8 lineage trace checks, release readiness validation, and the web build. |
| `pnpm run phase9:check` | Runnable | Runs local Phase 9 graph insight checks, release readiness validation, and the web build. |
| `pnpm run phase10:check` | Runnable | Runs local Phase 10 neighborhood explorer checks, release readiness validation, and the web build. |
| `pnpm run phase11:check` | Runnable | Runs local Phase 11 path finder checks, release readiness validation, and the web build. |
| `pnpm run phase12:check` | Runnable | Runs local Phase 12 review worklist checks, release readiness validation, and the web build. |
| `pnpm run phase13:check` | Runnable | Runs local Phase 13 review dashboard checks, release readiness validation, and the web build. |
| `pnpm run phase14:check` | Runnable | Runs local Phase 14 review activity checks, release readiness validation, and the web build. |
| `pnpm run phase15:check` | Runnable | Runs local Phase 15 source review coverage checks, release readiness validation, and the web build. |
| `pnpm run phase16:check` | Runnable | Runs local Phase 16 full graph workspace UI checks, release readiness validation, and the web build. |
| `pnpm run phase17:check` | Runnable | Runs local Phase 17 connector ingestion checks, release readiness validation, and the web build. |
| `pnpm run phase18:check` | Runnable | Runs AI foundation checks, release readiness validation, and the web build. |
| `pnpm run phase19:check` | Runnable | Runs Planning Mode checks, release readiness validation, and the web build. |
| `pnpm run phase20:check` | Runnable | Runs graph query agent checks, release readiness validation, and the web build. |
| `pnpm run phase21:check` | Runnable | Runs research extension checks, release readiness validation, and the web build. |
| `pnpm run phase22:check` | Runnable | Runs full AI V1 provider/UI/docs checks, release readiness validation, and the web build. |
| `pnpm run phase23:check` | Runnable | Runs AI-native graph workspace checks, release readiness validation, and the web build. |
| `pnpm run phase24:check` | Runnable | Runs living graph source contracts, Playwright browser QA, release readiness validation, and the web build. |
| `pnpm run phase25:check` | Runnable | Runs digital nervous system checks, web build, and browser graph QA. |
| `pnpm run phase26:check` | Runnable | Runs release hardening checks, web build, browser graph QA, and artifact cleanup. |
| `pnpm run release:check` | Runnable | Validates release readiness docs, commands, mode discovery, lineage, insights, neighborhoods, paths, review worklists, review dashboards, review activity, source review coverage, full graph workspace, backup/restore, and observability references. |
| `pnpm --filter @graphview/web dev` | Runnable | Starts the Vite web app on `127.0.0.1:5173`. |
| `pnpm --filter @graphview/api-contract dev` | Runnable | Starts the FastAPI service on `127.0.0.1:8000`. |
| `pnpm --filter @graphview/worker-contract dev` | Runnable | Runs the worker scaffold and prints the stage plan. |
| `pnpm --filter @graphview/web test:browser` | Runnable | Runs browser smoke tests for nonblank 2D/3D graph rendering and tooltip URL behavior. |

## Environment Variables

Use `.env.example` as the local template. Production values must come from external secret management.

The API defaults to `GRAPHVIEW_DATABASE_URL=sqlite:///./.graphview/graphview.sqlite` for local development. Use a
Postgres URL for shared development or production-like environments.

## Package Additions

Do not run casual package installs. Use a dedicated dependency PR, update the lockfile, and complete the checklist in
`03-security.md`.

## Direct Dependencies

JavaScript direct dependencies are pinned through `pnpm-workspace.yaml`: React, React DOM, React Router, TanStack Query,
Zustand, Vite, the Vite React plugin, React type packages, TypeScript, Three.js, Playwright, and PNGJS. Python direct
dependencies are locked through uv for the API and worker: FastAPI, Pydantic Settings, SQLAlchemy, Alembic, Uvicorn,
Arq, HTTPX, PyPDF, and Pytest.

HTTPX is a runtime API dependency for backend URL fetch during ingestion. PyPDF is a runtime API and worker dependency
for PDF extraction. Both are covered by `uv.lock` and service tests. Three.js powers the explicit 3D graph mode, while
`@types/three`, `@playwright/test`, and `pngjs` remain development-only QA dependencies.

## Failure Modes

- Local Node or pnpm version below policy.
- Missing lockfile review after dependency changes.
- Root commands added without documentation.
- Feature implementation added before Phase 2 scaffolding.
- Browser QA or dependency approval notes drifting from the committed lockfile and phase check scripts.
