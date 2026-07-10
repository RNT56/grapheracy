---
type: changed
owner: codex
---

# Live dependency and worker recovery

- Make API readiness verify PostgreSQL, Redis-backed sessions, and S3 independently while keeping liveness isolated
  from dependency outages; unexpected failures now return redacted RFC 7807 responses.
- Add exact-stack MinIO/Redis outage, inert upload failure, graph SSE resume, signed webhook replay, invalid signature,
  and expired worker-lease recovery proof.
- Inject real provider timeouts and 429 `Retry-After` behavior in worker tests, including error redaction and visible
  retry state.
- Force an Alembic lock-timeout interruption under an exclusive PostgreSQL table lock, prove transactional rollback,
  and then complete the same migration normally.
