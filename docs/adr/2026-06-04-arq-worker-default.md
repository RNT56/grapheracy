# ADR: Arq Worker Default

Date: 2026-06-04

## Status

Accepted for Phase 1 direction.

## Context

Ingestion work needs async stages, retries, traceability, and idempotency. The project does not yet need enterprise queue
features.

## Decision

Use Arq as the default worker direction for Phase 2 unless queue requirements force Celery.

## Consequences

- Redis is included in the local Compose topology.
- Worker stages must remain decoupled enough to migrate queues if needed.
- Long-running enterprise queue needs must be documented before switching to Celery.
