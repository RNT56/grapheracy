# Roadmap

## Phase 1: Project Preparation

Status: complete.

Goals:

- Preserve the single-file prototype unchanged under `prototypes/`.
- Create monorepo structure for apps, services, packages, docs, and infra.
- Establish `CLAUDE.md` as canonical maintainer and agent entrypoint.
- Add repo-markdown documentation source of truth.
- Add changelog fragments and release consolidation process.
- Install security and dependency governance before broad package adoption.
- Define public domain interfaces, API skeleton, worker contract, and event model.
- Add CI skeletons for lint, typecheck, test, audits, secret scan, docs hygiene, and changelog validation.

## Phase 2: Runnable Service Scaffolds

Status: complete.

- Scaffold React/Vite web app.
- Scaffold FastAPI API service.
- Scaffold async worker service.
- Add typed shared contracts to API and web.
- Add health checks, auth stub, DB migrations, and UI shell informed by the prototype.

## Phase 3: Core Graph Product

Status: complete.

- Implement graph persistence.
- Add source CRUD.
- Add import/export.
- Add proposal review flow.
- Preserve provenance through graph commits.
- Add Postgres full-text search.

## Phase 4: Ingestion Workers

- Add text and markdown ingestion.
- Add URL fetch through backend.
- Add PDF extraction.
- Add embeddings.
- Add LLM proposal generation.

## Phase 5: Hardening

- Harden graph rendering and large-graph performance.
- Enforce access control.
- Add observability.
- Add backup and restore.
- Finalize release process.

## Phase 6: Mode Extensions

- Add engineering repository mode.
- Add general ops document map mode.

## Coordinator Notes

- `CHANGELOG.md` and this roadmap are coordinator-owned.
- Every worker should add an unreleased fragment for meaningful changes.
- No production feature implementation belongs in Phase 1.
