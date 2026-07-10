---
type: changed
owner: codex
---

# Inert production disaster recovery

- Back up the full PostgreSQL database and isolated S3 object payload with checksummed database and object-set
  manifests; reject unsafe, corrupt, incomplete, or active-client restores.
- Require an explicit maintenance acknowledgement and stop API, worker, and Keycloak before destructive restore.
- Remove connector/provider/action secret references, revoke context clients and sessions, flush Redis, clear leases,
  and convert unfinished jobs, outbox events, connector/AI runs, actions, and linked Attention to inert terminal state.
- Add a live-stack gate that deletes database records and a referenced object, restores them, verifies credentials and
  side effects remain suppressed, restarts services, and proves no worker replay occurs.
- Preserve redacted connector metadata, graph versions, and saved layout coordinates through logical project export;
  revoke imported context clients and audit every logical restore while suppressing pending project jobs and outbox work.
