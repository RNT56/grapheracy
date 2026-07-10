# Operations

## Purpose

Define local and production operational direction without implementing production services in Phase 1.

## Deployment Model

Graphview is container-neutral. Docker Compose is provided for local and development orchestration, while production
containers must be deployable into internal infrastructure without SaaS assumptions.

## Services

- Web app container.
- API container.
- Worker container.
- PostgreSQL 18 with pgvector.
- MinIO for local S3-compatible storage.
- Redis for Arq worker queue if Phase 2 confirms Arq.

## Observability

The API exposes dependency-free local observability endpoints:

- `GET /health` is a public process health check.
- `GET /observability/ready` requires a reader, reviewer, or admin local user and verifies repository/database access.
- `GET /observability/metrics` requires the admin local user and returns in-memory request counters, status counts,
  path counts, last request metadata, and API process start time.

Every API response includes an `X-Graphview-Trace-Id` response header. Clients may pass the same header on requests to
carry a caller trace ID through local debugging and future infrastructure logs.

## Lens Discovery

The API exposes `GET /extraction-lenses` and `GET /graph-lenses` for reader, reviewer, and admin users. Extraction
lenses control proposal generation, while graph lenses control active subgraph display: `all`, `research`,
`engineering`, and `ops`.

## Lineage Trace

The API exposes `GET /lineage/{entity_kind}/{entity_id}` for reader, reviewer, and admin users. Supported entity kinds
are `source`, `proposal`, `node`, and `edge`. Trace responses connect the requested entity to its source, ingestion run,
proposals, review decisions, reviewed graph items, and provenance so operators can diagnose how reviewed graph state was
created.

## Graph Insights

The API exposes `GET /insights` for reader, reviewer, and admin users. The endpoint computes current graph counts,
review progress, source-kind counts, node-kind counts, relationship counts, top connected nodes, orphan edges, and
provenance coverage from the active project records.

## Neighborhood Explorer

The API exposes `GET /graph/neighborhood/{node_id}` for reader, reviewer, and admin users. Query parameters are bounded:
`depth` is limited to `1` or `2`, and `limit` is limited to `1` through `100` nodes. Responses include omitted node and
edge counts so operators can see when a focused graph was capped.

## Path Finder

The API exposes `GET /graph/path` for reader, reviewer, and admin users. Query parameters are bounded: `max_depth` is
limited to `1` through `6`. Responses include source and target nodes, `path_found`, distance, and the reviewed nodes
and edges in the path when one is found.

## Review Worklist

The API exposes `GET /review-queue` for reader, reviewer, and admin users. Query parameter `limit` is bounded to `1`
through `100`. Responses prioritize pending proposals and include ready counts, blocked counts, missing endpoint node
IDs, and the reason a reviewer should act or wait.

## Review Dashboard

The API exposes `GET /review-dashboard` for reader, reviewer, and admin users. Responses summarize proposal volume,
pending readiness, review decision mix, reviewer counts, oldest pending proposal metadata, and acceptance/commit rates
from current project records.

## Review Activity

The API exposes `GET /review-activity` for reader, reviewer, and admin users. Query parameter `limit` is bounded to `1`
through `100`. Responses list recent review decisions with proposal context, source context, reviewer ID, decision time,
and a deterministic summary for audit follow-up.

## Source Review Coverage

The API exposes `GET /review-sources` for reader, reviewer, and admin users. Query parameter `limit` is bounded to `1`
through `100`. Responses summarize each source's proposal count, pending count, reviewed count, decision mix, last
review timestamp, and source review status.

## Connector Ingestion

The API exposes connector-backed graph building endpoints:

- `GET /connectors` lists supported connector kinds and target types.
- `GET /graph/settings` and `PATCH /graph/settings` read and update project extraction settings.
- `GET /connector-accounts` and `POST /connector-accounts` manage redacted connector accounts.
- `GET /connector-targets`, `POST /connector-targets`, and `PATCH /connector-targets/{target_id}` manage read-only
  sync targets.
- `GET /connector-sync-runs`, `POST /connector-sync-runs`, and `GET /connector-sync-runs/{sync_run_id}` create and
  inspect manual sync/resync runs.
- `GET /source-chunks` lists normalized source chunks with heading paths, block locators, links, mentions, and checksums.

Connector token JSON is protected locally with `GRAPHVIEW_SECRET_KEY`; production deployments should replace that with
KMS-backed secret handling. LLM extraction is disabled by default and can be enabled through project or target settings.
Auto-commit uses the inherited confidence threshold and records `system-autocommit` review decisions.

## Full Graph Workspace

The web app presents the Knowledge Graph Builder full graph workspace. It keeps the prototype's outline, graph stage,
inspector, ingest controls, review operations, and layout dock structure while using live API data from the active
project.

## Living Graph UI QA

Phase 24 release preparation adds a living graph browser QA path. The web app should keep the graph as the central
workspace surface, expose 2D and 3D graph modes, and render rich node tooltips with visible tethers and safe source URL
actions. Browser smoke tests use mocked API responses and PNG pixel checks so blank SVG/canvas output fails even when
the DOM is present.

Operational acceptance for Phase 24 should include:

- Source-level checks for graph visual state, tooltip model, graph activity event model, and activity routes.
- Playwright desktop and mobile checks for nonblank 2D and 3D graph rendering.
- Tooltip checks for readable content, visible tether, external source URL target, and `rel` protection.
- Reduced-motion verification before animated graph activity ships.
- Confirmation that unreviewed candidate nodes and edges remain visually distinct from reviewed graph memory.

## AI Planning And Graph Research

The API exposes AI V1 endpoints for planning, read-only graph Q&A, and scoped research:

- `GET /providers` lists Graphview local, OpenAI, Anthropic, and Gemini descriptors without secret material.
- `PATCH /providers/{provider_id}/credentials` lets operators save OpenAI, Anthropic, or Gemini API keys as
  project-scoped encrypted settings; `DELETE /providers/{provider_id}/credentials` clears a browser-entered key.
- `POST /planning-sessions` and `POST /planning-sessions/{session_id}/messages` persist Planning Mode conversation and
  graph build specs.
- `POST /graph/query` answers questions using reviewed graph context and citations only.
- `POST /graph/research` creates normal sources, source chunks, ingestion runs, embeddings, and reviewable proposals.
- `POST /agent-runs/{agent_run_id}/approve-action` is the review gate for AI-proposed side effects.

Agent runs record provider, model, trace ID, status, summaries, citations, and action proposal state for audit. External
provider use can be configured through environment-backed settings or operator-entered project credentials; local
provider use remains the default fallback.

## Continuous Connector Operations

Connector mutations enqueue durable jobs; operators inspect `GET /api/v1/connectors/{target_id}/health` for the
cursor, lease, retry attempt, imported/deleted counts, last success, next schedule, and actionable failure. Scheduled
syncs cover every project and use target-local `interval_minutes` and `schedule_enabled` settings. GitHub, Google Drive,
and Notion webhook deliveries use provider IDs as durable idempotency keys, so a replay returns the original queued job.

Notion defaults to API version `2026-03-11`. A database target discovers and queries each child data source, pages
through active rows, stores a last-edited watermark, fetches only changed rows after the first snapshot, and records
trashed rows as tombstones. OAuth accounts may store `refresh_token`, `client_id`, `client_secret`, and `expires_at` in
their external secret reference; refresh rotates both the access and refresh tokens before the connector request.
Set `notion_version` explicitly only for a staged legacy migration. See the official
[data-source upgrade guide](https://developers.notion.com/guides/get-started/upgrade-guide-2025-09-03) and
[OAuth refresh contract](https://developers.notion.com/reference/refresh-a-token).

To register a Notion webhook without exposing its verification token:

1. Patch the target's `sync_settings.webhook_verification_pending` to `true` as an operator.
2. Register `https://<graphview>/api/v1/connectors/notion/<target_id>/webhook` in the Notion connection settings.
3. The one-time verification request is accepted only while armed and its token is written through the connector
   account's external secret reference; Graphview returns only a stored-status acknowledgement.
4. Complete verification in Notion, then patch `webhook_verification_pending` to `false`.
5. Subsequent events must carry Notion's HMAC-SHA256 signature over the exact body. Graphview also checks configured
   workspace/integration IDs and retains only a redacted event summary in the durable job.

## Secret Rotation And Removal

- `PATCH /api/v1/connector-accounts/{account_id}/credentials` rotates connector credentials at the existing opaque
  Vault reference and returns only the redacted account descriptor.
- `DELETE /api/v1/connector-accounts/{account_id}/credentials` disconnects the account and permanently deletes the
  Vault KV metadata and versions. Provider credential PATCH/DELETE routes use the same lifecycle.
- API startup migrates legacy database AES-GCM or reversible envelopes to the configured external store. It never
  rewrites an already opaque reference.
- Run `GRAPHVIEW_COMPOSE_PROJECT=graphview-live-ci pnpm run test:secrets:live` against candidate images. The proof
  checks Vault version increments, stable references, legacy migration after restart, response redaction, database
  neutralization, and permanent Vault purge.

## Active Agent Context Connectors

Phase 27 adds active context capture for external agents and editor adapters:

- Local acceptance command: `pnpm run quality:full`; production-stack acceptance command:
  `pnpm run test:agent-context:live`.
- `POST /agent-context/clients` creates a scoped adapter client and returns a one-time `gvctx_...` token to maintainers.
- `POST /agent-context/sessions`, `PATCH /agent-context/sessions/{session_id}`, and
  `POST /agent-context/events/batch` accept capture-only `gvctx_...` adapter bearer tokens and reject normal UI
  credentials. Requested client scopes are normalized to `context:capture`.
- Event batch responses include API-generated checksums over accepted, redacted event records.
- `GET /agent-context/sessions`, `GET /agent-context/sessions/{session_id}/events`, and
  `GET /agent-context/sessions/{session_id}/graph` expose reader-visible session metadata, timeline, and context graph
  projection.
- `GET /agent-context/artifacts/{artifact_id}/content` requires maintainer access and decrypts a redacted blob when it
  still exists.
- `GET /agent-context/sessions/{session_id}/stream` emits stable event IDs. Reconnecting clients send
  `Last-Event-ID`; Graphview resumes after that event or returns `409` when the retained cursor is unavailable.
- `POST /agent-context/retention/run` purges expired encrypted blobs while preserving audit metadata.
- `GET /backup` exports active-context metadata by default. Add `include_agent_context_content=true` only when an
  operator explicitly needs encrypted redacted context blobs in the backup bundle.

Operators should run the agent gateway for authoritative file/search/shell/model context, install the VS Code/Cursor
extension only for passive editor-state reconciliation, flush extension and gateway outboxes after retryable offline,
rate-limit, conflict, or server failures, and keep retention windows short enough for private workspaces.
Permanent 4xx responses are not retried.

## Digital Nervous System Actions

Action execution is gated by approved action proposals, operate permission, and the `GRAPHVIEW_SAFE_ACTION_TYPES`
allowlist. Internal source-freshness actions mutate only sources in the proposal's project. External actions execute
only as durable worker jobs through three production adapters:

- `create_external_ticket` mints a short-lived GitHub App installation token (or accepts an explicitly referenced
  installation token), scans all issue pages for the stable Graphview marker, and creates one GitHub Issue receipt.
- `create_notification` renders reviewed subject/body templates with inert string substitution, honors the suppression
  list, negotiates TLS when configured, uses a stable Message-ID, and records SMTP acceptance.
- `trigger_workflow` resolves only an allowlisted HTTPS destination and sends a stable event ID, timestamp, and
  HMAC-SHA256 signature. Receivers must reject stale timestamps and deduplicate the event ID. They can report a
  reviewed outcome to `POST /api/v1/action-runs/{action_run_id}/callback` with the same signature scheme; Graphview
  accepts a five-minute window and enqueues one `outcome.record` job per callback event ID.

The worker writes the action-run before calling an external system. Retries reuse that record and transition it through
`running`, `queued`, and `succeeded`; terminal provider errors and cancellation produce `failed` or `cancelled` records
and block linked Attention. Expired worker leases are reclaimed up to the configured job attempt limit. Provider error
text is redacted before job storage, connector health, action audit, or OpenTelemetry exception recording.

## Logical Project Export

The API exposes a redacted logical graph-state export and import for the active project:

- `GET /backup` requires the admin local user and returns metadata plus the complete export bundle.
- `POST /restore` requires the admin local user and replaces the active project state with a backup bundle.
- `GET /export` remains an operator-only raw bundle export for debugging and integration handoff.
- `POST /import` remains an operator-only seed import for sources and proposals, not a full restore.

Logical exports preserve project, sources, reviewed nodes, semantic edges, ingestion runs, proposals, embeddings, review
decisions, provenance, connector metadata, graph versions, saved layout coordinates, timestamps, and original IDs.
Restore revokes imported connector/context credentials, cancels unfinished logical work, suppresses pending project
jobs/outbox events, and writes an immutable restore audit event. It is destructive for the active project and should
only run after a fresh backup has been captured.

These endpoints are not the production disaster-recovery mechanism: they intentionally omit usable connector/provider
credentials, Redis sessions, queue state, audit internals, and normal object payloads.

## Production Disaster Recovery

The `graphview-ops` image backs up the complete PostgreSQL database and every non-backup object in the Graphview S3
bucket. Each archive contains the custom-format database dump, its SHA-256 file, a sorted object-key/size manifest, its
SHA-256 file, and an isolated object payload prefix. `verify` checks both manifest files, compares the archive object set,
and parses the database archive before a restore is allowed.

```sh
docker compose -p graphview -f infra/compose/docker-compose.production.yml run --rm ops backup --retention-days 30
BACKUP_PREFIX=backups/20260710T194032Z \
  docker compose -p graphview -f infra/compose/docker-compose.production.yml run --rm -e BACKUP_PREFIX ops verify
```

Restore is a maintenance-window operation. Stop every PostgreSQL client owned by Graphview—including Keycloak—then
pass both the database-name confirmation and the explicit maintenance acknowledgement:

```sh
docker compose -p graphview -f infra/compose/docker-compose.production.yml stop api worker keycloak
docker compose -p graphview -f infra/compose/docker-compose.production.yml run --rm \
  -e RESTORE_MAINTENANCE_CONFIRMED=1 ops restore \
  --backup-prefix backups/20260710T194032Z --confirm graphview
docker compose -p graphview -f infra/compose/docker-compose.production.yml up -d keycloak api worker
```

Restore refuses unsafe prefixes, invalid confirmation, missing maintenance acknowledgement, corrupt/incomplete
archives, or any remaining database client. After the database and object set are restored, it removes connector and AI
provider credential references, revokes active-context clients, cancels active context sessions, neutralizes unfinished
ingestion/connector/AI/action work, marks pending outbox events as suppressed, blocks linked Attention, clears connector
leases, and requires the authenticated Redis session flush to return `OK`. It never restores Vault itself. Reauthorize
connectors/providers and create new context clients after validation; never copy credentials from the backup archive.

Run `GRAPHVIEW_COMPOSE_PROJECT=graphview-live-ci pnpm run test:backup-restore:live` against the exact candidate images.
The gate creates credential, context, job, outbox, action, database, Redis, and object canaries; deletes the database and
object records; performs the real restore; proves every canary is restored inertly; restarts services; and confirms the
worker cannot replay the suppressed action.

## Compose

The development Compose file is `../infra/compose/docker-compose.dev.yml`. The production reference stack is
`../infra/compose/docker-compose.production.yml` and contains the static web proxy, API, worker, migration job,
PostgreSQL/pgvector, authenticated Redis, MinIO, ClamAV, PostgreSQL-backed Keycloak, Vault development reference, and
OpenTelemetry Collector.

```sh
docker compose -f infra/compose/docker-compose.dev.yml up web api worker postgres redis minio
```

Production images are multi-stage, non-root, and read-only at runtime. Start the exact reference images with generated
secrets and `docker compose -p graphview -f infra/compose/docker-compose.production.yml up -d --wait`; do not reuse the
Vault development token, Keycloak bootstrap account, or MinIO root credentials outside an isolated reference stack.

## OpenTelemetry

API server spans, SQLAlchemy calls, outbound HTTP calls, durable jobs, and outbox dispatches export over OTLP/gRPC.
The API emits bounded route-template request metrics and SSE connection/event/duration metrics; the worker emits queue
latency, active-job, terminal-status, execution-duration, and outbox-dispatch metrics. Enqueued jobs retain the W3C
`traceparent`, so execution in another worker process remains a child of the originating API request. The response
`X-Graphview-Trace-Id` is the same 32-hex distributed trace ID when telemetry is active.

Graphview never captures request or response headers. Server query strings are replaced with `<redacted>`, outbound
HTTP span URLs discard queries and fragments, provider exception text is redacted, and metric dimensions exclude
project IDs and job IDs. The reference Collector exposes Prometheus metrics on loopback port `8889` and keeps bounded
JSON trace and metric evidence in its non-root `/var/lib/otel` volume. Helm uses the same non-root image and an
ephemeral bounded volume. Production operators should replace or extend the reference file/debug exporters with their
chosen durable OTLP backend; the application contract remains vendor-neutral.

After the unmocked live browser workflow, prove the emitted contract with:

```sh
GRAPHVIEW_COMPOSE_PROJECT=graphview-live-ci pnpm run test:observability:live
```

The command fails unless it finds linked API and worker spans, the complete API/worker/SSE metric set, query-free URL
attributes, and no injected acceptance secret in Collector output.

## Environment Matrix

| Variable | Owner | Local default | Secret | Purpose |
| --- | --- | --- | --- | --- |
| `GRAPHVIEW_ENV` | all services | `local` | No | Runtime environment label. The API also accepts `GRAPHVIEW_ENVIRONMENT`. |
| `GRAPHVIEW_PUBLIC_BASE_URL` | web | `http://localhost:5173` | No | Browser app base URL. |
| `GRAPHVIEW_API_BASE_URL` | web/api | `http://localhost:8000` | No | API URL. |
| `POSTGRES_*` | api/worker | `.env.example` | Password yes | Database connection. |
| `MINIO_*` | api/worker | `.env.example` | Keys yes | Object storage. |
| `OIDC_*` | api | `.env.example` | Secret yes | Internal SSO adapter. |
| `ARQ_REDIS_URL` | worker | `redis://localhost:6379/0` | No locally | Worker queue. |
| `REDIS_HOST` / `REDIS_PASSWORD` | ops | `redis` / unset | Password yes | Explicit authenticated Redis session invalidation during production restore. |
| `RESTORE_MAINTENANCE_CONFIRMED` | ops | unset | No | Must be `1` only after API, worker, and Keycloak database clients are stopped. |
| `GRAPHVIEW_DATABASE_URL` | api | `sqlite:///./.graphview/graphview.sqlite` | No locally | API persistence URL. |
| `GRAPHVIEW_SECRET_KEY` | api | `local-dev-graphview-secret` | Yes outside local | Authenticated local AEAD key for development-only secret storage. Production connector/action credentials use external Vault references. |
| `GRAPHVIEW_LOCAL_SECRET_STORE_PATH` | api/worker | `./.graphview/secrets` | No | Development-only directory for atomic mode-0600 AES-GCM secret envelopes shared by local API and worker processes. |
| `GRAPHVIEW_LLM_*` | api | disabled OpenAI-compatible defaults | API key yes | Provider-agnostic LLM extraction defaults. Project and connector settings can override these defaults. |
| `GRAPHVIEW_AUTO_COMMIT_THRESHOLD` | api | `0.92` | No | Default confidence threshold for system auto-commit decisions. |
| `GRAPHVIEW_SAFE_ACTION_TYPES` | api | Phase 25 safe action list | No | Comma-separated allowlist for approved action proposal execution. |
| `GRAPHVIEW_ACTION_WEBHOOK_ALLOWED_HOSTS` | worker | empty | No | Exact HTTPS host allowlist for signed workflow actions. |
| `GRAPHVIEW_SMTP_HOST` / `GRAPHVIEW_SMTP_PORT` | worker | unset / `587` | No | SMTP delivery endpoint; Helm opens the configured external TCP port only when a host is set. |
| `GRAPHVIEW_SMTP_STARTTLS` / `GRAPHVIEW_SMTP_FROM_ADDRESS` | worker | `true` / unset | Address no | TLS policy and sender identity for reviewed notification actions. |
| `GRAPHVIEW_SMTP_SUPPRESSED_RECIPIENTS` | worker | empty | No | Comma-separated normalized recipients that must never receive Graphview mail. |
| `GRAPHVIEW_OTEL_EXPORTER_OTLP_ENDPOINT` | api/worker | unset | No | OTLP/gRPC Collector endpoint; unset keeps local tests on no-op providers. |
| `GRAPHVIEW_OTEL_SERVICE_NAME` | api/worker | `graphview-api` | No | Stable telemetry resource name; the production worker overrides it to `graphview-worker`. |
| `GRAPHVIEW_OTEL_METRIC_EXPORT_INTERVAL_MS` | api/worker | `60000` | No | Bounded periodic metric export interval; the Compose acceptance stack uses five seconds. |
| `GRAPHVIEW_AI_DEFAULT_PROVIDER` | api | `graphview-local` | No | Default agent provider when a request does not name one. |
| `GRAPHVIEW_OPENAI_*` | api | OpenAI Responses defaults | API key yes | OpenAI agent provider configuration; operator-entered project keys can override the API key. |
| `GRAPHVIEW_ANTHROPIC_*` | api | Claude Messages defaults | API key yes | Anthropic agent provider configuration; operator-entered project keys can override the API key. |
| `GRAPHVIEW_GEMINI_*` | api | Gemini generate-content defaults | API key yes | Gemini agent provider configuration; operator-entered project keys can override the API key. |

## Release Process

1. Capture and verify a `GET /backup` bundle from the target environment.
2. Run `pnpm run release:verify`; isolate failures with `quality:fast`, `quality:full`, `test:integration`, `test:e2e`,
   `test:performance`, `security:full`, or `test:deployment`.
3. Run the unmocked production-stack browser job with `GRAPHVIEW_LIVE_STACK=1 pnpm run test:e2e:live` against the
   exact candidate images.
4. Run `pnpm run test:observability:live` against the same Compose project and retain its trace/metric/redaction proof.
5. Consolidate fragments from `docs/changelog/unreleased/` into `CHANGELOG.md`.
6. Run full CI gates, including moderate audit, signature, OSV, and secret scans.
7. Generate SBOMs for release images, including the Graphview-owned non-root Collector image.
8. Review security exceptions, dependency changes, living graph browser QA, digital nervous system action gates,
   observability status, and restore plan.
9. Tag a SemVer release after V1 release policy is defined.

## Failure Modes

- Compose diverges from production container assumptions.
- Image layers include secrets.
- Non-root container policy is bypassed.
- SBOM generation is skipped before release.
- Operational docs lag behind environment variables.
- Backup capture or restore validation is skipped before a release.
- Metrics endpoints are exposed without admin-only access control.
- Mode descriptors drift between API, web shell, and shared contracts.
- Relationship proposals commit before endpoint nodes are reviewed.
- Lineage trace responses omit source, proposal, review decision, or provenance links needed for audit review.
- Insight summaries are trusted after graph mutations without a fresh `/insights` read.
- Neighborhood endpoints are called with unbounded depth or node limits.
- Path endpoints are called with unbounded depth or used as a substitute for full graph search.
- Review worklists are treated as durable queues instead of read-time views over proposal status.
- Review dashboards are copied into release notes without a fresh `/review-dashboard` read.
- Review activity feeds are used for audit review without checking that each item includes proposal and source context.
- Source review coverage is used for prioritization without verifying pending counts against current proposals.
- Full graph workspace UI changes are released without browser smoke checks against live API data.
- Connector token JSON is returned in read responses or written to logs.
- Connector resync runs duplicate unchanged source chunks, proposals, or reviewed graph items.
- Auto-commit thresholds are changed without checking duplicate/conflict and edge endpoint-readiness behavior.
- AI provider routes expose secret material, or AI research is allowed to write reviewed graph items without proposal
  review.
- Living graph UI changes pass DOM-only tests while the 2D or 3D rendered surface is blank.
- Tooltip source URLs navigate the current workspace instead of opening external sources with target and rel safeguards.
- Candidate proposal or agent activity visuals imply reviewed trust before the proposal/review record exists.
