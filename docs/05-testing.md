# Testing

## Purpose

Define the Graphview 1.0 verification layers and the evidence required before a capability or release is described as
complete. Historical phase checks have been replaced by stable commands.

## Verification Tiers

### Fast local gate

`pnpm run quality:fast` runs:

- documentation links/freshness and workspace metadata;
- Python lint, repository security policy, licenses, and changelog validation;
- architecture boundaries and size ceilings;
- FastAPI OpenAPI plus generated TypeScript client drift checks;
- TypeScript/Python type and compile checks;
- API, worker, web, gateway, extension, shared-contract, graph-core, and design-system tests;
- release-structure checks and the production web build.

This gate is suitable for every implementation slice. It is not production-stack evidence.

### Full local gate

`pnpm run quality:full` adds active-context smoke, focused integration suites, desktop/mobile Playwright E2E, client
performance planning, and browser artifact cleanup. `pnpm run release:verify` further adds the full security gate,
deployment validation, and deterministic client artifact packaging/verification.

### Real service integration

- `pnpm run test:migrations:postgres` runs the complete Alembic chain on PostgreSQL and forces a lock-timeout
  interruption to prove transactional rollback before completing normally.
- CI's production-stack job builds eight exact candidate images, starts PostgreSQL/pgvector, authenticated Redis,
  MinIO, ClamAV, PostgreSQL-backed Keycloak, Vault, OpenTelemetry Collector, API, worker, web, migration, and ops
  services, and then runs every Compose proof below.
- The protected `Staging acceptance` workflow loads the same commit's eight images into a clean Kubernetes 1.35 Kind
  cluster, installs the production Helm chart, waits for migrations/workloads, runs authenticated ingestion, performs
  a no-op upgrade, and retains a redacted receipt.

## API And Domain Coverage

The API suite covers:

- identity, OIDC JWT/session mapping, RBAC/BOLA, project scoping, CSRF, rate limits, and RFC 7807 errors;
- source CRUD, streamed uploads, URL/repository/Google/Notion connector contracts, extraction, provenance, lineage,
  tombstones, cursor health, retries, and idempotency;
- proposal validation, endpoint readiness, review authority, review dashboards/worklists/activity, and immutable audit;
- graph viewport/subgraph/search/layout/activity/SSE contracts, pagination, ETags, continuation counts, and V1 aliases;
- planning, provider redaction, cited graph query, research, retrieval audit, cancellation, budgets, and review-gated AI
  proposals;
- signals, observations, routing policies, Attention, decisions, action approval, internal/external execution state,
  outcomes, feedback, redaction, and side-effect suppression;
- active-context token/session/event/blob/replay/retention/derivation authority and backup behavior;
- logical export/restore, complete record reconstruction, job/outbox suppression, and credential neutralization.

Worker tests cover Arq stage selection, durable leases, retry/timeout/429 behavior, cancellation, terminal races,
external action run reuse, redacted failures, connector scheduling, and active-context maintenance.

## Browser And Renderer Coverage

`pnpm run test:e2e` exercises the product shell on desktop and mobile, including:

- Graphology/Sigma 2D and lazy Three.js 3D nonblank pixel output;
- semantic hover, selection, focus, proposal, evidence, Attention, and agent activity parity;
- clustered overview and progressive viewport loading;
- camera, filter, lens, saved-view, path, neighborhood, evidence, replay, comparison, and review interactions;
- context-loss recovery without losing selection, filter, layout, or review state;
- reduced motion, mobile lifecycle, high-contrast/focus behavior, keyboard graph navigation, and the accessible
  list/table projection;
- a forced no-WebGL fallback and screenshot-safe output.

The ten-case headed hardware run is recorded separately in the proof ledger because software/SwiftShader rendering is
not accepted as integrated-GPU evidence.

## Performance Acceptance

`pnpm run test:performance` retains complete 5,000-node/20,000-edge and 20,000-node/50,000-edge visible projections and
bounds client planning for a 100,000-node/500,000-edge stored project.

`pnpm run test:performance:live` idempotently seeds 100,000 nodes and 500,000 edges in the reference PostgreSQL stack,
authenticates through Keycloak, performs warmups, then measures 40 requests each for:

- clustered overview;
- concrete viewport expansion;
- depth-two focused subgraph;
- hybrid text/vector search.

Every server route must remain at or below 250 ms p95. The command writes a machine-readable receipt and fails on
dataset, response-shape, route-order, or threshold drift. Browser acceptance separately requires overview
interactivity within 2.5 seconds after the response, at least 45 FPS for 5k/20k, and at least 30 FPS for 20k/50k on the
documented integrated-GPU reference machine.

## Production Compose Proofs

All commands below run against an already started exact-image reference stack:

- `test:e2e:live`: browser Authorization Code + PKCE, Secure Redis-backed session, CSRF upload, S3/ClamAV acceptance,
  Arq completion, SSE terminal event, and review proposal visibility without request interception.
- `test:compatibility:live`: every unversioned route and operation compared with `/api/v1`, including status,
  content-type, deprecation/sunset/link headers, RFC 7807 normalization, and safe-read response parity.
- `test:observability:live`: shared API-to-worker trace, API/worker/SSE metric set, query-free URL attributes, and
  injected-secret rejection in Collector output.
- `test:agent-context:live`: OIDC service auth, capture-only adapter, ordered offline replay, encrypted MinIO content,
  stable `Last-Event-ID` resume, purge with metadata retention, and terminal session state.
- `test:secrets:live`: Vault KV stable-reference rotation, legacy local-envelope migration, API redaction, and permanent
  metadata/version deletion for connector, provider, and action credentials.
- `test:failure-injection:live`: MinIO/Redis loss with liveness/readiness separation, inert upload failure, dependency
  recovery, SSE resume, duplicate/invalid webhook handling, and expired worker lease reclamation.
- `test:performance:live`: the production-size p95 proof described above.
- `test:backup-restore:live`: checksummed PostgreSQL/S3 backup, destructive deletion, physical restore, connector,
  provider, action, and context credential removal, session revocation, Redis flush, terminal job/outbox/action state,
  blocked Attention, healthy restart, and no delayed external replay.

Restore verification also fails independently for unsafe prefixes, bad confirmation, missing maintenance
acknowledgement, corrupt checksums/manifests, missing/extra objects, or active database clients.

## Connector, AI, And External Action Canaries

Deterministic contract tests cover pagination, OAuth refresh, cursor advancement, webhook signatures, rate limits,
deletion/tombstones, retries, idempotency, provider timeouts, citations, GitHub App tokens, SMTP templates/suppression,
signed webhooks, callbacks, outcomes, and feedback.

Real-provider proof is the protected `external-canaries` environment and `test:external-canaries` workflow. It uses
dedicated disposable GitHub, Google Drive, Notion, OpenAI, SMTP, and webhook fixtures, builds the exact candidate
images, records only redacted IDs, closes the canary GitHub issue, deletes stored credentials, and destroys the stack.
If those fixtures are not provisioned, the corresponding ledger rows remain explicitly blocked; mocked or local
provider success is not reported as external production proof.

## Security Acceptance

`pnpm run security:full` covers policy, licenses, moderate dependency audit, OSV, Gitleaks, and npm integrity/trust.
Remote security jobs additionally generate SBOMs and scan every production image, upload all-severity SARIF, and block
on fixed HIGH/CRITICAL findings. Helm rendering is linted, validated against Kubernetes 1.35 schemas, and scanned for
manifest misconfiguration.

Feature tests explicitly cover BOLA/RBAC, CSRF, SSRF and redirects, upload paths/types/sizes, webhook replay,
credential redaction, token leakage, secret-reference validation, CSP/CORS, and rate limits.

## Release Artifact Acceptance

`pnpm run release:artifacts` creates the MCP gateway TGZ, installable VS Code/Cursor VSIX, SPDX 2.3 client SBOM,
commit/version manifest, and sorted SHA-256 list. `release:artifacts:verify` validates sizes, digests, archive structure,
runtime manifests, entrypoints, current commit, and workspace version.

Tag CI refuses an unsigned or GitHub-unverified annotated tag. It builds, pushes, signs, and attests eight immutable
image digests, attests client artifacts, signs the complete checksum manifest with keyless Sigstore, and publishes the
verified bundle.

## Evidence Rules

- Unit, integration, live-stack, staging, external-canary, and release-signing evidence are distinct tiers.
- A test proves only the paths and invariants it asserts; a narrow green check cannot close a broader claim.
- Mocked browser fixtures are never live-stack evidence.
- A canary must use the candidate commit's images and retain a redacted receipt.
- Flaky threshold failures remain failures until the implementation has enough measured headroom and a clean rerun.
- Documentation and the upgrade ledger are updated after executable proof, not before it.

## Failure Modes

- Phase-number commands or placeholder tests return to the release path.
- Generated contracts drift from the running API.
- DOM assertions miss blank WebGL output.
- A connector initial import passes while refresh, pagination, deletion, or retry remains untested.
- An external action reports success without an external receipt or durable internal mutation.
- Restore reintroduces a credential or runnable side effect.
- A performance receipt uses a smaller dataset, fewer routes, or a relaxed threshold.
- A release tag is created before immutable-stack, staging, migration, security, and external-fixture status are known.
