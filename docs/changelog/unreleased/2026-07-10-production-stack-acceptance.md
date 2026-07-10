---
type: added
owner: codex
---

# Production stack acceptance and continuous connectors

- Add an unmocked browser acceptance workflow for Keycloak PKCE login, Redis-backed sessions, CSRF-protected upload,
  durable worker completion, object-backed ingestion, and live review proposals.
- Add production Compose and Helm reference services with authenticated Redis, PostgreSQL-backed Keycloak, MinIO,
  ClamAV, Vault, migration Jobs, hardened runtime security contexts, deployment probes, and manifest security gates.
- Add race-safe running-job cancellation, multi-project connector scheduling, incremental GitHub compare/deletion
  handling, and verified Google Drive watch renewal and webhook delivery.
