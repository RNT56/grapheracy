---
type: changed
owner: codex
---

# Production Active Context

## Added

- Move active-context HTTP routes and capture-token authentication into a bounded backend module, lower the enforced
  API assembly ceiling, and prevent the route family from returning to the monolith.
- Add stable context SSE event IDs, `Last-Event-ID` resume, and an explicit stale-cursor conflict response.
- Add an exact-image Compose acceptance gate covering Keycloak service authorization, capture-only tokens, ordered
  offline gateway replay, encrypted MinIO blobs, redaction, object retention purge, metadata preservation, and session
  completion.

## Changed

- Replace phase-numbered active-context operator instructions with stable quality and live-stack commands.
