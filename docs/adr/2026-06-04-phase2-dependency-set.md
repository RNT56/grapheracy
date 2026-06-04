# ADR: Phase 2 Dependency Set

Date: 2026-06-04

## Status

Accepted for Phase 2 scaffolding.

## Context

Phase 2 turns placeholder packages into runnable scaffolds. That requires direct dependencies for the web app, API,
worker, and tests.

## Decision

Pin JavaScript dependencies through the pnpm catalog and lock Python dependencies through uv. Use React, React DOM,
React Router, TanStack Query, Zustand, Vite, Vite React plugin, React type packages, and TypeScript for the web scaffold.
Use FastAPI, Pydantic Settings, SQLAlchemy, Alembic, and Uvicorn for the API. Use Arq for the worker queue direction.
Use Pytest and HTTPX for service tests.

## Consequences

- The workspace has real lockfile diffs that must be reviewed.
- Lifecycle scripts remain denied by default.
- Phase 3 can build persistence and review workflows on a running baseline instead of replacing placeholders.
