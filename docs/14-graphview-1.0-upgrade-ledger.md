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
| V1 API and compatibility aliases | active | pending | pending | API |
| Graph viewport, LOD, layouts, and replay | active | pending | pending | Graph |
| Sigma/Graphology 2D and Three.js parity | active | pending | pending | Web |
| PostgreSQL/pgvector persistence and migration | active | pending | pending | Persistence |
| Arq queues, scheduling, retries, and outbox | active | pending | pending | Worker |
| Upload, URL, GitHub, Google, and Notion connectors | active | pending | pending | Connectors |
| Cited AI planning, query, and research | active | pending | pending | AI |
| Attention, actions, outcomes, and feedback | active | pending | pending | Actions |
| Active agent context capture and retention | implemented | implemented | pending | Context |
| OIDC, sessions, RBAC, CSRF, and service tokens | active | pending | pending | Identity |
| Vault-backed secrets and encrypted object storage | active | pending | pending | Security |
| OpenTelemetry metrics and traces | active | pending | pending | Operations |
| Compose and Kubernetes/Helm deployment | active | pending | pending | Operations |
| Backup, restore, rollback, SBOM, and signed release | active | pending | pending | Release |
| 100k-node/500k-edge acceptance | active | pending | pending | Performance |

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
