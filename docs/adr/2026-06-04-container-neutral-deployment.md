# ADR: Container-Neutral Deployment

Date: 2026-06-04

## Status

Accepted for Phase 1 direction.

## Context

Graphview is an internal product and should deploy into existing infrastructure without assuming a SaaS platform.

## Decision

Provide Docker Compose for local and development use while keeping service images container-neutral for production.

## Consequences

- Images must run as non-root users.
- Runtime configuration comes from environment variables and external secrets.
- SBOM generation is required before releases.
