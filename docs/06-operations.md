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

## Active Agent Context Connectors

Phase 27 adds active context capture for external agents and editor adapters:

- Acceptance command: `pnpm run phase27:check`.
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
- `GET /agent-context/sessions/{session_id}/stream` provides SSE-compatible replay for the active context workspace.
- `POST /agent-context/retention/run` purges expired encrypted blobs while preserving audit metadata.
- `GET /backup` exports active-context metadata by default. Add `include_agent_context_content=true` only when an
  operator explicitly needs encrypted redacted context blobs in the backup bundle.

Operators should run the agent gateway for authoritative file/search/shell/model context, install the VS Code/Cursor
extension only for passive editor-state reconciliation, flush extension and gateway outboxes after retryable offline,
rate-limit, conflict, or server failures, and keep retention windows short enough for private workspaces.
Permanent 4xx responses are not retried.

## Digital Nervous System Actions

Phase 26 keeps action execution gated by approved action proposals, operate permission, and a configurable safe-action
allowlist. `GRAPHVIEW_SAFE_ACTION_TYPES` accepts a comma-separated list of executable action types. Source freshness
actions only mutate sources in the proposal's project; missing or cross-project source IDs produce failed action runs
instead of silent mutation.

## Backup And Restore

The API exposes full graph-state backup and restore endpoints for the active project:

- `GET /backup` requires the admin local user and returns metadata plus the complete export bundle.
- `POST /restore` requires the admin local user and replaces the active project state with a backup bundle.
- `GET /export` remains an operator-only raw bundle export for debugging and integration handoff.
- `POST /import` remains an operator-only seed import for sources and proposals, not a full restore.

Backups preserve project, sources, reviewed nodes, semantic edges, ingestion runs, proposals, embeddings, review
decisions, provenance, timestamps, and original IDs. Restore is destructive for the active project and should only run
after a fresh backup has been captured.

## Compose

The development Compose file is `../infra/compose/docker-compose.dev.yml`.

```sh
docker compose -f infra/compose/docker-compose.dev.yml up web api worker postgres redis minio
```

The app services run from the local workspace for development. Production image hardening remains a later phase.

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
| `GRAPHVIEW_DATABASE_URL` | api | `sqlite:///./.graphview/graphview.sqlite` | No locally | API persistence URL. |
| `GRAPHVIEW_SECRET_KEY` | api | `local-dev-graphview-secret` | Yes outside local | Local reversible protection for connector token JSON. Production should replace this with KMS-backed secret handling. |
| `GRAPHVIEW_LLM_*` | api | disabled OpenAI-compatible defaults | API key yes | Provider-agnostic LLM extraction defaults. Project and connector settings can override these defaults. |
| `GRAPHVIEW_AUTO_COMMIT_THRESHOLD` | api | `0.92` | No | Default confidence threshold for system auto-commit decisions. |
| `GRAPHVIEW_SAFE_ACTION_TYPES` | api | Phase 25 safe action list | No | Comma-separated allowlist for approved action proposal execution. |
| `GRAPHVIEW_AI_DEFAULT_PROVIDER` | api | `graphview-local` | No | Default agent provider when a request does not name one. |
| `GRAPHVIEW_OPENAI_*` | api | OpenAI Responses defaults | API key yes | OpenAI agent provider configuration; operator-entered project keys can override the API key. |
| `GRAPHVIEW_ANTHROPIC_*` | api | Claude Messages defaults | API key yes | Anthropic agent provider configuration; operator-entered project keys can override the API key. |
| `GRAPHVIEW_GEMINI_*` | api | Gemini generate-content defaults | API key yes | Gemini agent provider configuration; operator-entered project keys can override the API key. |

## Release Process

1. Capture and verify a `GET /backup` bundle from the target environment.
2. Run `pnpm run phase27:check`. Use `pnpm run phase26:check` only when validating the previous release-hardening gate,
   and `pnpm run phase22:check` only when comparing against the historical AI V1 baseline.
   The Phase 27 gate includes `pnpm run phase27:smoke`; run that command directly when isolating active-context
   gateway/API smoke failures.
3. Run `pnpm run release:check`.
4. Consolidate fragments from `docs/changelog/unreleased/` into `CHANGELOG.md`.
5. Run full CI gates, including moderate audit, signature, OSV, and secret scans.
6. Generate SBOMs for release images.
7. Review security exceptions, dependency changes, living graph browser QA, digital nervous system action gates,
   observability status, and restore plan.
8. Tag a SemVer release after V1 release policy is defined.

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
