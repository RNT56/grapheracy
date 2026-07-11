---
type: changed
owner: codex
---

- Extract connector, source/ingestion, review, Attention, action/outcome, AI planning, agent-tool, and cited-retrieval
  HTTP routes from application assembly into bounded router modules, together with graph compatibility and
  search/backup/import operations.
- Preserve the committed OpenAPI and generated TypeScript client exactly, including compatibility operation IDs.
- Route the graph module through a typed application service and repository port, with focused domain-service tests
  and an architecture check preventing persistence access from returning to its router.
- Route source CRUD, lineage, and synchronous/durable ingestion selection through a typed SourcesService and
  repository port; make API test object stores session-owned so repeated verification no longer leaks temp folders.
- Route connector catalog, credential, target, and synchronous/durable sync selection through a typed
  ConnectorService and repository port while preserving the injectable LLM provider factory.
- Route proposal projections, dashboards, provenance coverage, creation, and reviewer-authority transitions through
  a typed ReviewService and repository port.
- Route decisions, action proposals, approval/rejection, action runs, outcomes, and feedback through a typed
  ActionsService and repository port while preserving reviewer and worker authority.
- Route signals, observations, alerts, Attention transitions, ownership, and routing policies through a typed
  AttentionService and repository port, completing explicit boundaries across the nervous-system loop.
- Route search, export, backup, inert restore, and review-gated import through a typed DataOperationsService and
  repository port while preserving operator authority and agent-context content policy.
- Route capture-token authority, session/event transitions, retained content, replay-cursor validation, graph
  projection, and retention through a typed AgentContextService and repository port.
- Route provider credentials, planning sessions/messages, review-gated build specs, agent runs, and the tool catalog
  through a typed PlanningService and AI repository port.
- Route agent graph-query context, source search/open, review-gated proposal creation, and layout intent through a
  typed AgentToolsService while keeping direct reviewed-graph mutation impossible.
- Route cited Q&A, research-to-source/proposal derivation, and reviewed agent-action approval through a typed
  RetrievalService, completing service/port boundaries for every compatibility module.
- Split canonical V1 viewport, subgraph, hybrid search, persisted layouts, activity pagination, and resumable SSE
  into a dedicated graph transport backed by GraphProjectionService, with exact OpenAPI/client parity and an
  architecture check preventing direct persistence access.
- Split canonical V1 ingestion and AI enqueue commands plus job pagination, status, SSE, cancellation, and retry
  into dedicated transports backed by JobService, preserving queue validation, idempotency, project scope, and the
  committed wire contract.
- Split canonical streamed upload acceptance into UploadService, retaining normalized filenames, byte limits,
  checksum-bound idempotency, object storage, HTTP/ClamAV screening, cleanup, and durable ingestion dispatch.
- Split canonical approved-action dispatch and signed workflow outcome callbacks into V1ActionService, preserving
  callback secret references, replay-resistant event idempotency, timestamp windows, and durable outcome recording.
- Split canonical connector sync, health, GitHub delivery verification, Google watch callbacks, and Notion
  verification/events into V1ConnectorService; reduce the V1 composer to dependency wiring with a 60-line ceiling.
- Begin physical replacement of the all-purpose persistence façade by moving source CRUD, chunk reads, ingestion-run
  projections, and source/proposal/node/edge lineage traversal into SourceCatalogRepositoryMixin and ratcheting the
  legacy repository ceiling to 5,700 lines; lineage lookup helpers and provenance aggregation now live with that
  domain rather than leaking back into the façade.
- Move graph view/scoping, lens filtering, neighborhood and path traversal, and insight projections into
  GraphReadRepositoryMixin; ratchet the remaining compatibility façade below 5,250 lines.
- Move planning sessions/messages, build specs, agent runs, graph-query context, research tasks, and reviewed agent
  actions into AiPlanningRepositoryMixin; ratchet the remaining compatibility façade below 4,650 lines.
- Move atomic ingestion, source chunks, proposal/embedding writes, connector deltas, deletion tombstones, and sync-run
  accounting into IngestionRepositoryMixin; ratchet the remaining compatibility façade below 4,200 lines.
- Move owners, routing policies, signals, observations, Attention, decisions, action proposals/runs, outcomes, and
  feedback into NervousSystemRepositoryMixin; ratchet the remaining compatibility façade below 3,600 lines.
- Move active-context clients, sessions, ordered events, retained artifact/blob references, replay projections, and
  retention into AgentContextRepositoryMixin; ratchet the remaining compatibility façade below 3,100 lines.
- Move proposal writes/projections, review queue/dashboard/activity, provenance coverage, review authority
  transitions, review event shaping, and decision reads into ReviewRepositoryMixin; ratchet the façade below 2,350 lines.
- Move search, export, complete backup, inert restore, and rollback-safe reconstruction into
  DataOperationsRepositoryMixin; reduce the former all-purpose repository to a 1,160-line compatibility composition
  and shared-helper layer with a 1,200-line ceiling.
- Move workspace wire/view-model contracts, provider capability metadata, and settings-page descriptors out of the
  web shell into workspaceTypes; reduce App.tsx from 5,944 to 5,197 lines under a 5,250-line ceiling.
- Move API graph/activity/source/proposal/review/agent/citation/lens normalization into workspaceModel; reduce
  App.tsx further to 4,852 lines under a 4,900-line ceiling while contract tests follow the bounded model module.
- Move provider selection, credential management, automation guardrails, runtime readouts, and capability matrices
  into SettingsWorkspace; reduce App.tsx to 4,350 lines under a 4,400-line ceiling.
- Move planning sessions, conversation/tool traces, build-spec blueprints, artifact preview, and research actions into
  PlanningWorkspace; reduce App.tsx to 4,013 lines under a 4,050-line ceiling.
- Move active-context session navigation, retained-content inspection, authority presentation, and event timelines into
  AgentContextWorkspace; reduce App.tsx to 3,808 lines under a 3,850-line ceiling.
- Move source-content inspection and evidence/proposal/planning fan-out into pure sourceContentModel and
  contentExpansionModel boundaries; promote GraphRenderEdge to the shared visual contracts; reduce App.tsx to 3,357
  lines under a 3,400-line ceiling.
- Ratchet API assembly to 220 lines and prevent bounded routes from migrating back into the monolith.
