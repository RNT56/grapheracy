# Roadmap

## Phase 1: Project Preparation

Status: complete.

Goals:

- Preserve the single-file prototype unchanged under `prototypes/`.
- Create monorepo structure for apps, services, packages, docs, and infra.
- Establish `CLAUDE.md` as canonical maintainer and agent entrypoint.
- Add repo-markdown documentation source of truth.
- Add changelog fragments and release consolidation process.
- Install security and dependency governance before broad package adoption.
- Define public domain interfaces, API skeleton, worker contract, and event model.
- Add CI skeletons for lint, typecheck, test, audits, secret scan, docs hygiene, and changelog validation.

## Phase 2: Runnable Service Scaffolds

Status: complete.

- Scaffold React/Vite web app.
- Scaffold FastAPI API service.
- Scaffold async worker service.
- Add typed shared contracts to API and web.
- Add health checks, auth stub, DB migrations, and UI shell informed by the prototype.

## Phase 3: Core Graph Product

Status: complete.

- Implement graph persistence.
- Add source CRUD.
- Add import/export.
- Add proposal review flow.
- Preserve provenance through graph commits.
- Add Postgres full-text search.

## Phase 4: Ingestion Workers

Status: complete.

- Add text and markdown ingestion.
- Add URL fetch through backend.
- Add PDF extraction.
- Add deterministic local embeddings.
- Add provider-boundary proposal generation with a local heuristic implementation.

## Phase 5: Hardening

Status: complete.

- Harden graph rendering and large-graph performance.
- Enforce access control.
- Add observability.
- Add backup and restore.
- Finalize release process.

## Phase 6: Mode Extensions

Status: complete.

- Add engineering repository mode.
- Add general ops document map mode.

## Phase 7: Relationship Proposals

Status: complete.

- Generate deterministic semantic edge proposals during ingestion.
- Resolve proposed edge endpoints to reviewed node IDs.
- Guard edge commits until endpoint nodes are accepted.
- Surface pending relationship proposals in the web review queue.

## Phase 8: Lineage Trace

Status: complete.

- Add trace endpoints for sources, proposals, nodes, and edges.
- Connect committed graph items back to source, ingestion run, proposal, review decision, and provenance.
- Surface lineage summaries in the web review queue.

## Phase 9: Graph Insights

Status: complete.

- Add graph insight diagnostics for review progress, graph quality, and provenance coverage.
- Surface top connected nodes, orphan edge counts, and source/proposal breakdowns.
- Show insight summaries in the web review queue.

## Phase 10: Neighborhood Explorer

Status: complete.

- Add bounded focused graph neighborhoods for reviewed nodes.
- Reuse deterministic graph-core neighborhood extraction semantics.
- Show neighborhood summaries in the web review queue.

## Phase 11: Path Finder

Status: complete.

- Add bounded shortest paths between reviewed graph nodes.
- Reuse deterministic graph-core path traversal semantics.
- Show path summaries in the web review queue.

## Phase 12: Review Worklist

Status: complete.

- Add prioritized pending proposal worklists.
- Mark relationship proposals as ready or blocked based on reviewed endpoint nodes.
- Show ready and blocked review counts in the web review queue.

## Phase 13: Review Dashboard

Status: complete.

- Add review operating summaries for proposal volume, decision mix, and reviewer activity.
- Reuse review worklist readiness logic for ready and blocked pending counts.
- Show acceptance and commit rates in the web review queue.

## Phase 14: Review Activity Feed

Status: complete.

- Add recent review decision feeds with proposal and source context.
- Keep activity computed from durable review decisions rather than a separate activity table.
- Show latest review activity in the web review queue.

## Phase 15: Source Review Coverage

Status: complete.

- Add source-level review coverage for proposal and decision state.
- Keep coverage computed from sources, ingestion runs, proposals, and review decisions.
- Show highest-priority source review coverage in the web review queue.

## Phase 16: Full Graph Workspace UI

Status: complete.

- Replace the compact shell with a prototype-inspired Knowledge Graph Builder workspace.
- Keep outline, graph stage, inspector, ingest controls, review operations, and layout dock visible in the main UI.
- Preserve live API-backed graph, review, lineage, insight, path, neighborhood, activity, and source coverage behavior.

## Phase 17: Connector Ingestion and Graph Building

Status: complete.

- Add connector accounts, targets, sync runs, source chunks, topics, source origin metadata, graph settings, and expanded
  semantic relation values.
- Support manual sync and resync for upload, URL, repository, Google Workspace, and Notion connector targets.
- Build source hierarchy, explicit source-aware relationships, deterministic proposals, optional provider-boundary LLM
  proposals, embeddings, and confidence-threshold auto-commit with provenance.
- Surface connector setup, sync status, source hierarchy, inherited LLM settings, and auto-commit controls in the graph
  workspace.

## Phase 18: Durable AI Foundation

Status: complete.

- Add durable planning sessions, planning messages, graph build specs, agent runs, agent steps, research tasks, and
  agent action proposals.
- Add AI provider catalog contracts for Graphview local, OpenAI, Anthropic, and Gemini without returning secret
  material.
- Add Phase 18-22 release check commands.

## Phase 19: Planning Mode

Status: complete.

- Add a separate Planning Mode workspace with a session rail, planning conversation, graph build preview, provider
  status, and research launch controls.
- Add planning APIs that turn user planning messages into assistant messages and persisted graph build specs.
- Keep build specs non-mutating until research or action approval flows run.

## Phase 20: Graph Query Agent

Status: complete.

- Add read-only graph query over reviewed graph, sources, source chunks, lineage context, and citations.
- Persist graph query runs, steps, provider/model details, trace IDs, and cited graph context.
- Surface embedded graph AI answer and citation controls in the graph workspace.

## Phase 21: Research Extension Agent

Status: complete.

- Add scoped AI research that creates source records, source chunks, ingestion runs, embeddings, and reviewable proposals.
- Keep graph mutations review-gated through existing proposal and review decision paths.
- Surface research status and pending AI action proposals in the graph workspace.

## Phase 22: Provider Completion and Release Hardening

Status: complete.

- Add OpenAI Responses, Anthropic Messages, and Gemini generate-content adapters with mocked tests.
- Add deterministic local provider behavior for local development and CI.
- Document provider configuration, data-transfer policy, review gates, and release checks.

## Phase 23: AI-Native Graph Workspace and Agent Tooling

Status: complete.

- Simplify the default graph workspace around Overview, Focus, Evidence, Review, Sources, and Planning.
- Keep 3D graph exploration available as an explicit dimension option while preserving a quiet 2D overview default.
- Promote the source reader into a first-class Evidence surface with outline navigation, readable passages, citation
  anchors, and passage-level AI/proposal actions.
- Replace generic review actions with typed Needs attention work items that show change summary, evidence, citations,
  affected graph items, and accept/reject/edit actions.
- Recenter Planning Mode on chat with inline agent tool activity and artifact preview sidecars.
- Add shared agent tool contracts plus `/agent-tools` and `/agent-tool-calls` API surfaces for graph-native AI work.

## Phase 24: Living Graph UI and Agent Activity Visualization

Status: complete.

- Kept the visual knowledge graph as the center of the Graph workspace rather than a supporting dashboard widget.
- Added a renderer-agnostic visual state model for hover, focus, related, dimmed, scanning, cited, incoming, candidate,
  ready, blocked, accepted, rejected, edited, deferred, and stale graph objects.
- Added rich node and edge tooltips that remain visually tethered to graph objects in 2D and 3D.
- Added meaningful microanimations for graph hover, selection, camera focus, path tracing, evidence scans, proposal
  previews, and review outcomes.
- Visualized agent graph Q&A and research directly inside the graph through scan waves, active paths, incoming sources,
  ghost nodes, ghost edges, citations, and review gates.
- Added graph-linked evidence and citation paths so source chunks, graph nodes, AI answers, and proposals remain visually
  connected.
- Added proposal and review animations that show candidate graph objects becoming accepted, rejected, edited, deferred, or
  blocked without bypassing review decisions.
- Preserved reduced-motion support, graph-size performance budgets, and 2D/3D interaction parity.
- Added Phase 24 source-contract and Playwright browser QA scaffolds for graph activity routes, nonblank 2D/3D rendering,
  tethered tooltip source URL behavior, and reduced-motion expectations.
- Wired `phase24:check` through package scripts, web build, and browser QA.
- Use `11-living-graph-ui-vision-and-upgrade-plan.md` as the implementation record for this phase.

## Phase 25: Digital Nervous System Loop

Status: complete.

- Added continuous sensing through API signals, connector-generated signals, scheduled syncs, and webhook-ready intake
  shapes.
- Added first-class signals, observations, alerts, attention items, owners, routing policies, decision records, action
  proposals, action runs, outcomes, feedback events, and graph activity events.
- Expanded Needs attention into a graph-centered Attention workspace for proposal review, stale knowledge, conflicts,
  anomalies, connector issues, action follow-up, and outcome review.
- Added ownership, assignment, severity, SLA, escalation, blockers, evidence links, graph links, and suggested actions.
- Added safe action execution boundaries for approved side effects such as proposal creation, connector sync, source
  freshness updates, research tasks, notifications, tickets, and internal workflow stubs.
- Added outcome tracking and feedback loops that can update graph freshness, confidence, routing policy, and future
  prioritization through review-gated or policy-gated records.
- Added temporal memory for source freshness, repeated signals, state changes, graph change timelines, recurring review
  cycles, and outcome due dates.
- Added durable graph activity replay and optional streaming so Phase 24 living graph visuals can show the full nervous
  system loop.
- Hardened connectors as sensing inputs with scheduled syncs, auth refresh, pagination, rate-limit handling, retry,
  deletion/stale detection, sync health, and connector-generated attention signals.
- Preserved review gates, action permission checks, redacted payloads, backup/restore coverage, and no side-effect replay
  after restore.
- Use `12-digital-nervous-system-phase25-plan.md` as the implementation record for this phase.

## Coordinator Notes

- `CHANGELOG.md` and this roadmap are coordinator-owned.
- Every worker should add an unreleased fragment for meaningful changes.
- No production feature implementation belongs in Phase 1.
