# Product Goals

## Purpose

Graphview helps users ingest mixed knowledge sources, extract candidate concepts and relationships, review proposals,
preserve provenance, and explore the resulting graph.

## V1 Audience

- Internal research teams mapping literature, notes, interviews, and documents.
- Personal knowledge workflows that need provenance and review instead of opaque summarization.

## V1 Scope

- Single internal organization.
- Role-based access within that organization.
- Source records with provenance.
- Ingestion runs with traceable worker stages.
- Extraction proposals reviewed before graph commits.
- Interactive graph exploration.
- Postgres-backed full-text search.
- S3-compatible object storage for source artifacts.

## Non-V1 Scope

- Multi-tenant SaaS.
- Public anonymous access.
- Marketplace ingestion plugins.
- Real-time collaborative editing.
- OpenSearch or Meilisearch unless Postgres search becomes measured bottleneck.
- Heavy graph rendering commitment before Sigma.js and Cosmograph are evaluated in Phase 2.

## Upgrade Paths

Engineering mode will add repository ingestion, code-symbol aware extraction, dependency graph overlays, and pull-request
or issue provenance.

General ops mode will add policy, process, vendor, incident, and project document maps with ownership and review
metadata.

## Success Criteria

- Users can trace every graph node and edge back to source material and review decisions.
- Ingestion is idempotent, replayable, and observable.
- Reviewers can accept, reject, or edit proposals before graph updates.
- The product stays container-neutral and deployable into internal infrastructure.
