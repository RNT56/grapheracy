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
| V1 API and compatibility aliases | implemented | 87 API tests, OpenAPI/client drift gate, and alias parity tests | Canonical session, upload, job, and review routes proven through the live browser stack; full alias-stack replay pending | API |
| Graph viewport, LOD, layouts, and replay | active | pending | pending | Graph |
| Sigma/Graphology 2D and Three.js parity | active | pending | pending | Web |
| PostgreSQL/pgvector persistence and migration | implemented | Alembic rehearsal and real PostgreSQL repository tests | Compose and Kubernetes schema `20260710_0017`, persisted source/object, and no-op Helm upgrade proven | Persistence |
| Arq queues, scheduling, retries, and outbox | implemented | 6 worker tests plus API cancellation and terminal-race coverage | Upload attempt 1 proven through authenticated Redis and a real worker; failure-injection matrix pending | Worker |
| Upload, URL, GitHub, Google, and Notion connectors | active | Upload extraction/security plus connector pagination, incremental cursor, deletion, webhook, and retry tests | Upload/ClamAV/MinIO production-proven; secret-backed GitHub, Google, and Notion canaries pending | Connectors |
| Cited AI planning, query, and research | active | Durable query/research tests and retrieval audit coverage | Live PostgreSQL/S3/worker query and research proven; external-provider failure/cancellation canary pending | AI |
| Attention, actions, outcomes, and feedback | active | pending | pending | Actions |
| Active agent context capture and retention | implemented | implemented | pending | Context |
| OIDC, sessions, RBAC, CSRF, and service tokens | implemented | Identity/RBAC/CSRF tests and live service-token exchange | Browser Authorization Code + PKCE, Redis session, CSRF upload, and Keycloak group mapping production-proven | Identity |
| Vault-backed secrets and encrypted object storage | active | pending | pending | Security |
| OpenTelemetry metrics and traces | active | pending | pending | Operations |
| Compose and Kubernetes/Helm deployment | implemented | 38-resource Helm render passes lint, Kubernetes 1.35 schema validation, and HIGH/CRITICAL Trivy gate | Compose and Kind stacks healthy with non-root/read-only services; live Helm install and no-op upgrade proven | Operations |
| Backup, restore, rollback, SBOM, and signed release | active | pending | pending | Release |
| 100k-node/500k-edge acceptance | active | pending | pending | Performance |

## Recorded Evidence

The following evidence was rerun on 2026-07-10 from `codex/graphview-1-0`:

- `pnpm run quality:fast`: architecture, security policy, license, changelog, generated-client drift, type, test, release
  structure, and production web-build gates passed; the API suite reported 87 tests and the worker suite reported 6.
- `pnpm run test:deployment`: Helm rendered 38 valid Kubernetes 1.35 resources and Trivy reported zero HIGH or
  CRITICAL manifest findings.
- `GRAPHVIEW_LIVE_STACK=1 pnpm run test:e2e:live`: a browser completed Keycloak PKCE login, loaded the real graph
  workspace, fetched its Redis-backed session and CSRF token, uploaded unique evidence, waited for an Arq job to
  succeed on attempt 1, and found the resulting proposals in the live review queue without request interception.
- The same release images were installed in a local Kind reference cluster; all stateful and application workloads
  became ready, the migration Job completed, an authenticated service token succeeded, an upload traversed ClamAV,
  MinIO, Redis, and the worker, and a subsequent no-op Helm upgrade remained healthy.

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
