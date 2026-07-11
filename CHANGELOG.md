# Changelog

All notable changes to Graphview are documented here. Graphview follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

No changes yet.

## [1.0.0] - 2026-07-11

### Added

- A graph-centered workspace with Sigma 3/Graphology 2D, lazy Three.js 3D, deterministic layouts, progressive
  server-assisted clustering, saved views, graph search, path/neighborhood exploration, evidence fan-out, replay,
  comparison, export, keyboard navigation, and a non-WebGL accessible equivalent.
- PostgreSQL/pgvector graph persistence, hybrid retrieval, stable graph versions, layout snapshots, indexed adjacency,
  cursor pagination, resumable SSE, RFC 7807 errors, ETags, idempotency, audit events, and canonical `/api/v1` routes
  with one-release compatibility aliases.
- Durable Arq queues and transactional outbox dispatch for ingestion, connectors, embeddings, agents, actions,
  outcomes, retention, and maintenance, including retries, leases, dead-letter state, cancellation, and scheduling.
- Streamed upload, SSRF-safe URL, GitHub/repository, Google Workspace, and Notion connectors with incremental cursors,
  pagination, refresh, webhook validation, deletion/tombstones, retry, and connector-health surfaces.
- Planning sessions, cited graph Q&A, scoped research, provider-neutral AI adapters, retrieval audits, budgets,
  cancellation, and review-gated AI proposals.
- The complete signals → observations → Attention → decisions → approved actions → outcomes → feedback loop, with
  production GitHub Issue, SMTP, and HMAC-signed webhook adapters.
- MCP gateway and VS Code/Cursor active-context capture with ordered offline outboxes, scoped authority, redaction,
  encrypted S3 retention, SSE resume, purge metadata, and reviewed derivation.
- Generic OIDC Authorization Code + PKCE, Redis sessions, service JWTs, project RBAC/BOLA, CSRF protection, Keycloak
  reference roles, Vault-backed secret references, CSP/CORS, rate limits, outbound allowlists, and structured audit.
- Vendor-neutral OpenTelemetry traces and metrics across API, workers, queues, connectors, agents, actions, SQL, HTTP,
  and SSE with sensitive attribute sanitization.
- Hardened Compose and Helm deployments for web, API, workers, PostgreSQL/pgvector, Redis, MinIO, ClamAV, Keycloak,
  Vault, migrations, backup, ingress, network policy, autoscaling, disruption budgets, and the Collector.
- Deterministic gateway TGZ and VS Code/Cursor VSIX packaging, SPDX SBOMs, image vulnerability scans, provenance,
  Cosign signatures, signed checksum manifests, and verified release publication.

### Changed

- Replaced the prototype-era monolith with bounded identity, graph, source/ingestion, connector, review, AI, Attention,
  actions, agent-context, operations, and V1 modules backed by application services, repository ports, and enforced
  architecture ceilings.
- Replaced phase-number release commands with `quality:fast`, `quality:full`, `test:integration`, `test:e2e`,
  `test:performance`, `security:full`, and `release:verify`.
- Made TanStack Query the owner of server state and limited Zustand to ephemeral graph interaction state; source,
  review, settings, planning, Attention, connector, and active-context operations now live in bounded feature hooks.
- Promoted FastAPI/Pydantic OpenAPI to the wire-contract source of truth and committed a drift-checked generated
  TypeScript client.
- Reworked the large-graph projection path to avoid full graph materialization and use bounded PostgreSQL clustering,
  adjacency traversal, lexical/vector candidates, and visible-budget edge sampling.
- Preserved the standalone prototype as non-production UX evidence and removed every production import of demo data.

### Fixed

- WebGL context recovery, reduced-motion Three.js framebuffer stability, zero-width mobile lifecycle, and renderer-pixel
  acceptance so blank or decorative-only output cannot pass.
- Physical and logical restore neutralization for connector, AI provider, action-adapter, and active-context
  credentials, Redis sessions, queued jobs, outbox events, connector/AI runs, actions, leases, and linked Attention.
- Shared-runner clustered-overview variance by replacing ordered-set kind calculation with bounded per-kind aggregation
  and limiting edge sampling to the requested visible budget.
- Retry, cancellation, lease-reclamation, duplicate webhook, provider timeout/429, object-store outage, Redis outage,
  migration interruption, and SSE reconnect races.
- Kind/Helm staging selection and readiness for labeled migration Jobs plus both RollingUpdate and OnDelete
  StatefulSets, branch-head candidate SHA binding rather than synthetic pull-request merge refs, and authenticated
  smoke through the generated-contract graph catalog.
- Active-context smoke verification now compares retained content with the exact runtime-selected file range instead of
  obsolete front-door wording.

### Security

- Removed seeded-header authentication, reversible secret obfuscation, inline external actions, mutable image inputs,
  Vite preview serving, root containers, and production demo fixtures from normal production paths.
- Added streamed upload validation and malware scanning, SSRF/redirect protections, safe paths, HMAC replay windows,
  redacted provider errors, secret-reference validation, strict outbound policies, and no side-effect replay on restore.
- Added frozen lockfile trust/integrity, OSV, Gitleaks, license, all-image SBOM/vulnerability, Kubernetes schema, and
  manifest security gates.

[Unreleased]: https://github.com/RNT56/grapheracy/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/RNT56/grapheracy/releases/tag/v1.0.0
