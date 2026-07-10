# Architecture

## Purpose

Define Phase 1 service boundaries, contracts, data model, event model, worker lifecycle, and deployment direction.

## Stack

- Frontend: React 19.2, TypeScript, Vite 8, React Router, TanStack Query, Zustand.
- Graph rendering: typed Canvas/WebGL abstraction first; evaluate Sigma.js and Cosmograph in Phase 2.
- Backend: FastAPI, Pydantic, SQLAlchemy 2, Alembic, Uvicorn/Gunicorn.
- Workers: Python async workers; Arq is the default Phase 1 queue direction unless enterprise queue needs force Celery.
- Storage: PostgreSQL 18 with pgvector and S3-compatible object storage; MinIO for local development.
- Search: Postgres full-text search in V1.
- Auth: internal OIDC/SSO-ready interface with a local dev adapter and seeded users.
- Runtime defaults: Node 24 Active LTS, Python 3.14, pnpm 10.27+, uv.

## Service Boundaries

- `apps/web`: browser UI and graph interaction.
- `apps/docs-app`: later markdown-backed docs app.
- `services/api`: HTTP API, auth boundary, persistence boundary, and review workflows.
- `services/worker`: source fetch, extraction, analysis, proposal generation, and commit jobs.
- `packages/shared-types`: public cross-boundary contracts.
- `packages/graph-core`: graph model helpers and rendering abstraction.
- `packages/design-system`: design tokens and shared UI primitives.

## Domain Model

The public interfaces are defined in `../packages/shared-types/src/index.ts`, and the canonical data-schema reference is
`09-data-schema.md`.

- `GraphProject`: workspace-level graph container.
- `Topic`: scoped area of inquiry within a project.
- `Source`: user-provided or fetched knowledge source.
- `ContentNode`: reviewed graph node with provenance.
- `SemanticEdge`: reviewed relationship between content nodes.
- `IngestionRun`: traceable execution of source processing.
- `ExtractionProposal`: worker-generated candidate node or edge.
- `ReviewDecision`: reviewer action that accepts, rejects, edits, or defers a proposal.
- `ContentEmbedding`: vector record linked to a proposal and, after acceptance, a reviewed content node.
- `Provenance`: source location, actor, timestamps, and extraction metadata.

## API Skeleton

The generated OpenAPI contract lives in `../services/api/openapi.yaml`, and the runnable FastAPI app lives in
`../services/api/src/graphview_api`. Regenerate OpenAPI from the running app after public request or response model
changes.

- `GET /health`
- `GET /version`
- `GET /observability/ready`
- `GET /observability/metrics`
- `GET /graph`
- `GET /graph/neighborhood/{node_id}`
- `GET /graph/path`
- `GET /insights`
- `GET /extraction-lenses`
- `GET /graph-lenses`
- `GET /lineage/{entity_kind}/{entity_id}`
- `GET /sources`
- `POST /sources`
- `PATCH /sources/{source_id}`
- `DELETE /sources/{source_id}`
- `GET /ingestion-runs`
- `POST /ingestion-runs`
- `GET /proposals`
- `POST /proposals`
- `GET /review-queue`
- `GET /review-dashboard`
- `GET /review-activity`
- `GET /review-sources`
- `GET /review-decisions`
- `POST /review-decisions`
- `GET /search`
- `GET /export`
- `GET /backup`
- `POST /restore`
- `POST /import`
- `GET /graph/settings`
- `PATCH /graph/settings`
- `GET /connectors`
- `GET /connector-accounts`
- `POST /connector-accounts`
- `GET /connector-targets`
- `POST /connector-targets`
- `PATCH /connector-targets/{target_id}`
- `GET /connector-sync-runs`
- `POST /connector-sync-runs`
- `GET /connector-sync-runs/{sync_run_id}`
- `GET /source-chunks`
- `GET /providers`
- `POST /planning-sessions`
- `GET /planning-sessions`
- `POST /graph/query`
- `POST /graph/research`
- `GET /graph/activity`
- `GET /graph/activity/stream`
- `GET /signals`
- `POST /signals`
- `GET /observations`
- `POST /observations`
- `GET /alerts`
- `POST /alerts/{alert_id}/assign`
- `GET /attention`
- `POST /attention/{attention_item_id}/transition`
- `GET /owners`
- `POST /owners`
- `GET /routing-policies`
- `POST /routing-policies`
- `GET /decision-records`
- `POST /decision-records`
- `GET /action-proposals`
- `POST /action-proposals`
- `POST /action-proposals/{action_proposal_id}/approve`
- `POST /action-runs`
- `POST /action-runs/{action_run_id}/outcome`
- `GET /feedback-events`
- `POST /feedback-events`
- `POST /agent-context/clients`
- `POST /agent-context/sessions`
- `PATCH /agent-context/sessions/{session_id}`
- `POST /agent-context/events/batch`
- `GET /agent-context/sessions`
- `GET /agent-context/sessions/{session_id}`
- `GET /agent-context/sessions/{session_id}/events`
- `GET /agent-context/sessions/{session_id}/graph`
- `GET /agent-context/artifacts/{artifact_id}/content`
- `GET /agent-context/sessions/{session_id}/stream`
- `POST /agent-context/retention/run`

Phase 4 adds backend-triggered ingestion for text, markdown, URLs, and PDFs. The request creates a source, ingestion run,
reviewable proposals, deterministic local embeddings, and provenance in one repository transaction.

Phase 5 enforces local seeded-user role checks across graph data actions, adds readiness and request metrics surfaces,
and adds operator-only backup/restore endpoints that preserve the full reviewed graph state.

Phase 6 splits extraction lenses from active graph lenses. Ingestion runs signal-gated Research, Engineering, and Ops
extraction by default. Active graph reads can use `lens=all|research|engineering|ops` to return full or filtered
subgraphs.

Phase 7 adds deterministic `semantic_edge` proposals alongside content-node proposals. The repository resolves proposed
edge endpoints from candidate labels to the node IDs assigned in the same ingestion result. Review commits reject an edge
until both endpoint nodes have already been accepted.

Phase 8 adds read-only lineage traces for `source`, `proposal`, `node`, and `edge` entities. The API resolves each trace
through existing repository records and returns the related source, ingestion runs, proposals, review decisions, reviewed
nodes, reviewed edges, and provenance.

Phase 9 adds read-only graph insight diagnostics through `GET /insights`. The endpoint summarizes graph counts, review
progress, source kinds, node kinds, relationship kinds, orphan edges, top connected nodes, and provenance coverage.

Phase 10 adds read-only focused neighborhoods through `GET /graph/neighborhood/{node_id}`. The endpoint returns a
bounded depth-1 or depth-2 subgraph around a reviewed node, with deterministic ranking and omitted-node/edge counts.

Phase 11 adds read-only path finding through `GET /graph/path`. The endpoint returns a bounded shortest path between two
reviewed nodes, or an explicit no-path response when both nodes exist but are not connected within the requested depth.

Phase 12 adds read-only review worklists through `GET /review-queue`. The endpoint prioritizes pending proposals and
marks relationship proposals as ready or blocked based on whether endpoint nodes have already been reviewed.

Phase 13 adds read-only review operating summaries through `GET /review-dashboard`. The endpoint aggregates proposal
volume, pending readiness, decision mix, reviewer participation, and acceptance/commit rates from current records.

Phase 14 adds read-only review activity feeds through `GET /review-activity`. The endpoint lists recent review decisions
with the related proposal, source, reviewer, timestamp, and deterministic summary for audit follow-up.

Phase 15 adds read-only source review coverage through `GET /review-sources`. The endpoint summarizes proposal volume,
pending/reviewed split, decision mix, last review timestamp, and review status for each source.

Phase 16 keeps the API surface stable and replaces the compact web shell with a full graph workspace. The React app now
uses the Knowledge Graph Builder layout pattern from the preserved prototype: floating outline, central reviewed graph
stage, inspector, ingest controls, review operations, and layout dock while remaining backed by live API data. The
graph renderer supports deterministic Force, Radial, Arc, 2D, and 3D view modes plus graph search, node selection,
relationship labels, content-density controls, and collapsible workspace chrome.

Phase 17 adds connector-backed graph building. The API stores connector accounts, connector targets, sync runs, source
chunks, graph settings, source origin metadata, and topics. Upload, URL, repository, Google Workspace, and Notion
adapters normalize remote content into source documents and chunks. Deterministic extraction always runs; optional LLM
extraction uses a provider boundary and the same reviewable proposal shape. Eligible high-confidence proposals are
accepted through `system-autocommit` review decisions, while duplicate or endpoint-blocked relationships remain pending.

Phases 18-22 add durable AI-native planning, provider descriptors, graph Q&A, scoped research, citations, agent runs,
tool calls, and review-gated AI action proposals. Agent-created graph changes still land as proposals and require the
existing review path before they become durable graph data.

Phase 24 adds living graph activity through shared visual state, renderer-agnostic tooltip/tether models, persisted
`graph_activity_events`, SSE-compatible replay, and 2D/3D renderer parity in the web workspace.

Phase 25 adds the digital nervous system loop: `Signal -> Observation -> Alert -> AttentionItem -> DecisionRecord ->
ActionProposal -> ActionRun -> Outcome -> FeedbackEvent`. The loop stores ownership, routing, SLA, review, execution,
outcome, and learning records in the API, exposes them in the graph-centered Attention mode, and keeps every mutating
action behind review and operate permission gates.

Phase 27 adds active agent context connectors. External agents and editor adapters create scoped context clients, start
sessions, report file/search/shell/prompt/model/edit/test/commit events, and attach redacted encrypted text blobs. The
API projects those records into a session-local context graph and graph activity events. Captured context remains
observed evidence, not reviewed graph memory, until an existing proposal/review workflow accepts a derived graph change.

## Worker Lifecycle

Worker stages are documented in `../services/worker/worker-contract.md`, with the runnable stage plan in
`../services/worker/src/graphview_worker/pipeline.py`.

1. Connector fetch.
2. Source extract.
3. Chunk normalize.
4. Hierarchy build.
5. Entity resolve.
6. Relation propose.
7. Content embed.
8. Proposal generate.
9. Autocommit evaluate.
10. Review commit.

Every stage must be idempotent, traceable, retryable, and linked to `IngestionRun` provenance.

## Event Model

- `source.created`
- `ingestion.started`
- `proposal.ready`
- `review.committed`
- `graph.updated`
- `signal.created`
- `observation.created`
- `alert.routed`
- `attention.assigned`
- `decision.recorded`
- `action.proposed`
- `action.approved`
- `action.run.succeeded`
- `outcome.resolved`
- `feedback.recorded`
- `agent_context.session_started`
- `agent_context.event_recorded`
- `agent_context.session_completed`
- `agent_context.retention_run`

Events are internal integration contracts. They must include stable IDs, actor context when available, timestamps,
schema version, and trace ID.

## Data Persistence

Postgres is the system of record for graph projects, topics, sources, nodes, edges, proposals, review decisions, and
job state. pgvector is reserved for embeddings once extraction workflows require semantic retrieval. Object storage
holds raw source artifacts and derived text where database storage would be inefficient.

Phase 3 adds a SQLAlchemy repository with a local SQLite default for development and tests. The table model mirrors the
Postgres direction and keeps JSON payloads explicit for provenance, topic IDs, proposal values, and edited review values.
Future migrations can replace JSON text with richer Postgres types where measured need justifies it.

Phase 4 adds `content_embeddings` records linked to proposals and later accepted content nodes. Embeddings use a
deterministic local hash model in Phase 4 so review workflows can be tested without external secrets. pgvector remains
the production direction once semantic retrieval requirements are measured.

Phase 5 restore replaces the active project with a backup bundle while preserving original IDs, provenance, ingestion
runs, proposals, embeddings, review decisions, and timestamps.

Phase 6 keeps mode data in source and proposal payloads rather than adding separate mode tables. This preserves the
single-project data model while making mode-specific extraction visible through proposal metadata.

Phase 7 keeps relationship extraction in proposal payloads as well. `semantic_edge` proposals carry `sourceNodeId`,
`targetNodeId`, `relation`, `weight`, provenance, and mode metadata when relevant.

Phase 8 does not add a separate lineage table. Trace responses are assembled from the existing source, ingestion run,
proposal, review decision, node, edge, and provenance records so exported and restored bundles remain the source of
truth.

Phase 9 insights are computed on read from the existing graph, source, proposal, review decision, and provenance tables.
No aggregate table is introduced, which keeps backup and restore semantics unchanged.

Phase 10 neighborhoods are computed on read from reviewed nodes and edges. No saved view or cache table is introduced,
so neighborhood responses always reflect the current reviewed graph state.

Phase 11 paths are computed on read from reviewed nodes and edges with a bounded breadth-first traversal. No path cache
or path table is introduced.

Phase 12 worklists are computed on read from proposals, ingestion runs, sources, and reviewed node IDs. No queue table is
introduced, so proposal status remains the source of truth.

Phase 13 dashboards are computed on read from proposals, review decisions, and the existing worklist readiness logic. No
aggregate table is introduced, so review operating metrics always reflect current proposal and decision state.

Phase 14 activity feeds are computed on read from review decisions, proposals, ingestion runs, and sources. No activity
table is introduced, so the feed remains a projection of durable review records.

Phase 15 source review coverage is computed on read from sources, ingestion runs, proposals, and review decisions. No
coverage table is introduced, so source status remains a projection of proposal and decision state.

Phase 16 adds no persistence. The full graph workspace is a presentation layer over existing graph, source, proposal,
review, lineage, insight, neighborhood, path, activity, and source-coverage endpoints.

Phase 17 adds durable connector and hierarchy persistence: `connector_accounts`, `connector_targets`,
`connector_sync_runs`, `source_chunks`, `topics`, and `graph_settings`. `Source` records also store connector kind,
remote IDs, parent IDs, remote modification timestamps, remote URLs, metadata, and stale markers. Local development uses
`GRAPHVIEW_SECRET_KEY` for authenticated local AES-GCM secret envelopes; production deployments use opaque Vault
handling.

Phase 18-22 add AI-native planning, graph Q&A, scoped research, and a provider catalog without replacing graph
persistence. `planning_sessions`, `planning_messages`, `graph_build_specs`, `agent_runs`, `agent_steps`,
`research_tasks`, and `agent_action_proposals` store planning, question-answering, research, provider/model, trace, and
action-review state. Planning Mode is a separate UI workspace. `GET /providers` exposes redacted provider/model
descriptors, while `POST /planning-sessions` and `POST /planning-sessions/{session_id}/messages` persist planning
conversation state. Embedded graph AI uses `POST /graph/query` for read-only cited answers and `POST /graph/research`
for scoped research that creates normal sources, chunks, ingestion runs, embeddings, and reviewable proposals. Agent
action approval is the only AI action endpoint that can apply review decisions or other future side effects.

## Failure Modes

- Worker stage retries without idempotency can duplicate proposals or graph edges.
- Missing provenance breaks trust in graph updates.
- Premature renderer choice can force rewrites before graph size is understood.
- Auth adapter drift can create differences between local and internal SSO behavior.
- Search technology added too early can create avoidable operational overhead.
- Lineage traces can become incomplete if graph commits omit proposal IDs or provenance links.
- Insight counts can mislead reviewers if computed from stale aggregate tables instead of current graph records.
- Neighborhood responses can become too large if depth and node limits are not enforced.
- Path queries can become expensive if max-depth bounds are relaxed before graph size is measured.
- Reviewers can waste time on blocked relationship proposals if endpoint readiness is not surfaced.
- Review operating metrics can mislead if acceptance rates are read from stale aggregates instead of current decisions.
- Review activity feeds can become misleading if proposal or source context is omitted from recent decision entries.
- Source review coverage can misprioritize reviewers if pending proposal counts are not joined back to sources.
- The full graph workspace can regress into a static prototype if live API-backed review and ingestion controls are not
  preserved.
- Connector ingestion can leak credentials if token JSON is returned from read endpoints or logged during sync.
- Resync can duplicate graph proposals unless target ID, remote ID, checksum, model, and trace metadata remain part of
  idempotency checks.
- AI agents can undermine provenance if answers or research proposals omit source/chunk citations, provider/model,
  confidence, and trace IDs.
- Provider credentials can leak if provider catalogs, run outputs, logs, or connector settings return raw API keys.
- Agent research can overreach if scoped research writes reviewed nodes/edges directly instead of creating reviewable
  proposals through existing ingestion and review workflows.
- Active context capture can overstate what an LLM saw if passive editor observations are not labeled separately from
  gateway-authoritative file and model-call events.
- Full captured content can leak private material if redaction, encryption, token scope, read permissions, and retention
  policy are bypassed.
