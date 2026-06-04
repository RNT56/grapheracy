# Architecture

## Purpose

Define Phase 1 service boundaries, contracts, data model, event model, worker lifecycle, and deployment direction.

## Stack

- Frontend: React 19.2, TypeScript, Vite 8, React Router, TanStack Query, Zustand.
- Graph rendering: typed Canvas/WebGL abstraction first; evaluate Sigma.js and Cosmograph in Phase 2.
- Backend: FastAPI, Pydantic, SQLAlchemy 2, Alembic, Uvicorn/Gunicorn.
- Workers: Python async workers; Arq is the default Phase 1 queue direction unless enterprise queue needs force Celery.
- Storage: PostgreSQL 18 with pgvector and S3-compatible object storage; MinIO for local development.
- Search: Postgres full-text search in V1.
- Auth: internal OIDC/SSO-ready interface with a local dev adapter and seeded users.
- Runtime defaults: Node 24 Active LTS, Python 3.14, pnpm 10.27+, uv.

## Service Boundaries

- `apps/web`: browser UI and graph interaction.
- `apps/docs-app`: later markdown-backed docs app.
- `services/api`: HTTP API, auth boundary, persistence boundary, and review workflows.
- `services/worker`: source fetch, extraction, analysis, proposal generation, and commit jobs.
- `packages/shared-types`: public cross-boundary contracts.
- `packages/graph-core`: graph model helpers and rendering abstraction.
- `packages/design-system`: design tokens and shared UI primitives.

## Domain Model

The public interfaces are defined in `../packages/shared-types/src/index.ts`.

- `GraphProject`: workspace-level graph container.
- `Topic`: scoped area of inquiry within a project.
- `Source`: user-provided or fetched knowledge source.
- `ContentNode`: reviewed graph node with provenance.
- `SemanticEdge`: reviewed relationship between content nodes.
- `IngestionRun`: traceable execution of source processing.
- `ExtractionProposal`: worker-generated candidate node or edge.
- `ReviewDecision`: reviewer action that accepts, rejects, edits, or defers a proposal.
- `Provenance`: source location, actor, timestamps, and extraction metadata.

## API Skeleton

The OpenAPI contract skeleton lives in `../services/api/openapi.yaml`.

- `GET /health`
- `GET /version`
- `GET /graph`
- `GET /sources`
- `GET /ingestion-runs`
- `GET /proposals`
- `GET /review-decisions`

Phase 2 will add request and response schemas backed by shared contracts.

## Worker Lifecycle

Worker stages are documented in `../services/worker/worker-contract.md`.

1. Source fetch.
2. Source extract.
3. Content analyze.
4. Proposal generate.
5. Review-aware commit.

Every stage must be idempotent, traceable, retryable, and linked to `IngestionRun` provenance.

## Event Model

- `source.created`
- `ingestion.started`
- `proposal.ready`
- `review.committed`
- `graph.updated`

Events are internal integration contracts. They must include stable IDs, actor context when available, timestamps,
schema version, and trace ID.

## Data Persistence

Postgres is the system of record for graph projects, topics, sources, nodes, edges, proposals, review decisions, and
job state. pgvector is reserved for embeddings once extraction workflows require semantic retrieval. Object storage
holds raw source artifacts and derived text where database storage would be inefficient.

## Failure Modes

- Worker stage retries without idempotency can duplicate proposals or graph edges.
- Missing provenance breaks trust in graph updates.
- Premature renderer choice can force rewrites before graph size is understood.
- Auth adapter drift can create differences between local and internal SSO behavior.
- Search technology added too early can create avoidable operational overhead.
