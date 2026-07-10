# Graphview 1.0 Upgrade Ledger

## Purpose

Track Graphview 1.0 claims against implementation, integration proof, production-reference proof, and ownership. A
capability is complete only when all four columns are satisfied. Unit tests or UI wiring alone do not qualify as
production proof.

The locked reference architecture exposes canonical `/api/v1` contracts over PostgreSQL/pgvector, Redis/Arq, and
S3-compatible object storage; it authenticates browser and service clients with OIDC and externalizes production
secrets. The operational graph surface uses Sigma with Graphology for 2D and a lazy Three.js renderer for 3D.

## Status Vocabulary

- `implemented`: production code exists and no stub is used on the normal path.
- `integration-tested`: real dependent services run in an automated test.
- `production-proven`: the reference self-hosted stack passes the documented acceptance scenario.
- `blocked`: an external credential or environment is required and the local contract proof is complete.

## Completion Ledger

| Capability | Implementation | Integration proof | Production proof | Owner |
| --- | --- | --- | --- | --- |
| Bounded backend architecture | active | Identity, operations/readiness, connector, sources/ingestion, review, Attention, actions/outcomes, agent-context, and V1 graph routers pass the 102-test API suite with exact OpenAPI/client parity | Assembly reduced from 1,486 to 869 lines with a 900-line regression ceiling; AI/planning extraction still pending | Architecture |
| V1 API and compatibility aliases | implemented | 102 API tests, OpenAPI/client drift gate, and alias parity tests | Canonical session, upload, job, review, connector, readiness, and graph replay routes proven through the live stack; full alias-stack replay pending | API |
| Graph viewport, LOD, layouts, and replay | implemented | V1 projection tests plus browser bounds, zoom, visible-budget, accessible-equivalent, and compatibility coverage | OIDC-authenticated 100k/500k PostgreSQL overview, concrete zoom expansion, indexed subgraph, and hybrid-search p95 production-proven | Graph |
| Sigma/Graphology 2D and Three.js parity | active | Nonblank 2D/3D, lazy-load, semantic-state, mobile, reduced-motion, injected WebGL-loss recovery in both renderers, and selection-persistence browser coverage | Reference GPU parity sign-off pending | Web |
| PostgreSQL/pgvector persistence and migration | implemented | Alembic rehearsal and real PostgreSQL repository tests | Compose and Kubernetes schema `20260710_0017`, persisted source/object, transactional lock-timeout interruption rollback, and no-op Helm upgrade proven | Persistence |
| Arq queues, scheduling, retries, and outbox | implemented | 8 worker tests plus API cancellation, provider timeout/429, and terminal-race coverage | Authenticated upload plus expired-lease recovery after a stopped worker and Redis outage/recovery production-proven | Worker |
| Upload, URL, GitHub, Google, and Notion connectors | active | Upload extraction/security plus GitHub compare, Google changes/watch, and Notion 2026 data-source/OAuth/webhook cursor, deletion, signature, replay, and retry tests | Upload/ClamAV/MinIO production-proven; secret-backed GitHub, Google, and Notion canaries pending | Connectors |
| Cited AI planning, query, and research | active | Durable query/research tests and retrieval audit coverage | Live PostgreSQL/S3/worker query and research proven; external-provider failure/cancellation canary pending | AI |
| Attention, actions, outcomes, and feedback | active | Internal nervous-system loop plus GitHub App, templated SMTP, signed webhook, durable retry/cancel/lease, receipt, suppression, and redaction tests | Secret-backed GitHub/SMTP/webhook action and callback canaries pending | Actions |
| Active agent context capture and retention | implemented | API lifecycle/replay/retention tests plus gateway and extension offline-outbox tests | OIDC service auth, ordered offline replay, MinIO-encrypted capture, resumable SSE, redaction, purge, and metadata preservation production-proven | Context |
| OIDC, sessions, RBAC, CSRF, and service tokens | implemented | Identity/RBAC/CSRF tests and live service-token exchange | Browser Authorization Code + PKCE, Redis session, CSRF upload, and Keycloak group mapping production-proven | Identity |
| Vault-backed secrets and encrypted object storage | implemented | Local atomic AEAD and Vault KV v2 create/read/replace/delete tests plus legacy-envelope migration and S3 retained-blob coverage | Stable-reference Vault rotation, legacy database migration, permanent purge, and MinIO-encrypted context production-proven | Security |
| OpenTelemetry metrics and traces | implemented | API request/SSE and worker queue/job/outbox unit coverage, pinned Collector config validation, and Helm schema/security gates | Authenticated Compose upload proves W3C API-to-worker trace continuity, API/worker/SSE metrics, query-free URLs, and acceptance-secret redaction in Collector output | Operations |
| Compose and Kubernetes/Helm deployment | implemented | 39-resource Helm render passes lint, Kubernetes 1.35 schema validation, and HIGH/CRITICAL Trivy gate | Compose and Kind stacks healthy with non-root/read-only services; live Helm install and no-op upgrade proven | Operations |
| Backup, restore, rollback, SBOM, and signed release | active | Destructive recovery proof plus verified gateway TGZ, installable VSIX, SPDX SBOM, checksums, eight-image SBOM/signing matrix, and provenance workflows | Exact-stack inert restore production-proven; final GitHub-verified signed tag and published Sigstore bundle pending | Release |
| 100k-node/500k-edge acceptance | implemented | 100k/500k clustered overview under 2.5 seconds, 5k/20k at or above 45 FPS, 20k/50k at or above 30 FPS, and bounded 100k/500k planning contract | Apple M2 Pro reference run: 178.5 ms overview, 24.8 ms detail, 20.7 ms subgraph, and 6.6 ms search p95 | Performance |

## Recorded Evidence

The following evidence was rerun on 2026-07-10 and 2026-07-11 from `codex/graphview-1-0`:

- `pnpm run quality:fast`: architecture, security policy, license, changelog, generated-client drift, type, test, release
  structure, and production web-build gates passed; the API suite reported 102 tests and the worker suite reported 8.
- The bounded-router extraction retained the committed OpenAPI and generated TypeScript client byte-for-byte while
  moving connector, source/ingestion, review, Attention, and actions/outcomes endpoints out of application assembly.
  Architecture checks now require those module boundaries, reject route migration back into `main.py`, and cap
  assembly at 900 lines.
- `pnpm run test:deployment`: Helm rendered 39 valid Kubernetes 1.35 resources and Trivy reported zero HIGH or
  CRITICAL manifest findings.
- `GRAPHVIEW_LIVE_STACK=1 pnpm run test:e2e:live`: a browser completed Keycloak PKCE login, loaded the real graph
  workspace, fetched its Redis-backed session and CSRF token, uploaded unique evidence, waited for an Arq job to
  succeed on attempt 1, read the terminal SSE job event, received the distributed trace ID, and found the resulting
  proposals in the live review queue without request interception.
- `GRAPHVIEW_COMPOSE_PROJECT=graphview-acceptance pnpm run test:observability:live`: the Collector received a shared
  API/upload and durable-worker trace, route-bounded API metrics, worker queue/job metrics, and SSE metrics. The proof
  also parsed every emitted URL attribute and rejected queries/fragments or any injected database, Redis, object-store,
  Keycloak, Vault, session-signing, service-client, or browser-test secret.
- `GRAPHVIEW_COMPOSE_PROJECT=graphview-acceptance pnpm run test:agent-context:live`: a Keycloak service client created
  a capture-only adapter, replayed two ordered gateway events queued while the API endpoint was unavailable, persisted
  redacted encrypted content in MinIO, resumed SSE after a stable event ID, purged the expired object, retained the
  metadata audit record, and completed the session.
- `GRAPHVIEW_COMPOSE_PROJECT=graphview-acceptance pnpm run test:secrets:live`: connector and provider credentials
  rotated as new Vault KV versions without changing their opaque database references, a legacy database AES-GCM
  credential migrated to Vault on restart, API responses remained redacted, and deletion removed Vault metadata and
  all versions.
- `GRAPHVIEW_COMPOSE_PROJECT=graphview-acceptance pnpm run test:backup-restore:live`: the ops image verified database and
  object manifests, survived destructive record/object deletion, restored the complete PostgreSQL/S3 canary set,
  removed usable connector/provider/context credentials, suppressed unfinished jobs/outbox/actions, flushed Redis,
  restarted Keycloak/API/worker, and proved the worker did not replay the external action.
- `GRAPHVIEW_COMPOSE_PROJECT=graphview-acceptance pnpm run test:performance:live`: the exact production Compose API
  used Keycloak service authentication and a seeded PostgreSQL/pgvector project containing 100,000 nodes and 500,000
  edges. Across 40 measured requests per route, p95 was 178.5 ms for clustered overview, 24.8 ms for concrete viewport
  expansion, 20.7 ms for depth-two subgraph, and 6.6 ms for hybrid search. The run used an Apple M2 Pro MacBook Pro
  with 12 CPU cores and 16 GB host memory; Docker had 12 CPUs and 8 GB memory.
- `GRAPHVIEW_COMPOSE_PROJECT=graphview-acceptance pnpm run test:failure-injection:live`: stopping MinIO made readiness
  fail while liveness remained healthy, a real upload returned redacted RFC 7807 output without creating a job, and
  recovery required no API restart. Stopping Redis produced the same readiness/liveness separation and recovered;
  graph SSE resumed strictly after `Last-Event-ID`; duplicate signed GitHub deliveries reused the original durable job;
  an invalid signature was rejected; and a stopped worker reclaimed an expired lease on attempt 2. The PostgreSQL
  migration rehearsal also forced a lock-timeout, proved revision/schema rollback, then completed normally.
- The same release images were installed in a local Kind reference cluster; all stateful and application workloads
  became ready, the migration Job completed, an authenticated service token succeeded, an upload traversed ClamAV,
  MinIO, Redis, and the worker, and a subsequent no-op Helm upgrade remained healthy.
- `pnpm run test:performance` retained complete 5k/20k and 20k/50k visible projections and bounded a 100k/500k
  project overview well under its 2.5-second budget on the development machine. Chromium browser acceptance separately proved clustered
  overview latency, nonblank WebGL output, the 5k/20k and 20k/50k frame gates, viewport bounds, context recovery,
  mobile rendering, and a 250-row accessible projection window. The production dataset result above completes the
  matching server-side projection sign-off.

## Acceptance Rule

The final integration branch may merge to `main` only when every row is `implemented`, `integration-tested`, and
`production-proven`, or explicitly `blocked` solely on a secret-backed external canary whose deterministic contract and
failure tests pass. No production path may use seeded authentication, an empty worker function list, reversible XOR
credential storage, simulated external IDs, or mocked-only critical flows.

## Failure Modes

- Roadmap prose is updated before executable proof exists.
- Mocked browser fixtures are treated as live-stack evidence.
- A connector supports initial import but not pagination, refresh, deletion, retry, and health.
- An approved action reports success without an external receipt or durable internal mutation.
- A migration requires destructive rollback instead of expand-compatible application rollback.
