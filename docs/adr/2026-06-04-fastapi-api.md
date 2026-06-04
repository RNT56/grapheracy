# ADR: FastAPI API Service

Date: 2026-06-04

## Status

Accepted for Phase 1 direction.

## Context

Graphview needs a typed internal API for graph data, sources, ingestion runs, proposals, review decisions, auth, and
provenance.

## Decision

Use FastAPI with Pydantic, SQLAlchemy 2, Alembic, and Uvicorn/Gunicorn for the API service.

## Consequences

- Python contracts can align with worker code.
- OpenAPI remains first-class.
- Phase 2 must define schema generation and drift checks against shared TypeScript contracts.
