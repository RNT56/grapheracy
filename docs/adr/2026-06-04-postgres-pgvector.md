# ADR: PostgreSQL And pgvector

Date: 2026-06-04

## Status

Accepted for Phase 1 direction.

## Context

Graphview needs durable graph, review, provenance, search, and future embedding storage.

## Decision

Use PostgreSQL 18 as the system of record, with pgvector available for embedding workflows.

## Consequences

- Postgres full-text search is the V1 default.
- Search services such as OpenSearch or Meilisearch require measured need.
- Migrations must be managed through Alembic starting in Phase 2.
