# Testing

## Purpose

Define Phase 1 checks and the future test strategy.

## Phase 1 Checks

- `pnpm run lint`
- `pnpm run security:local`
- `pnpm run security:licenses`
- `pnpm run changelog:check`
- `pnpm run typecheck`
- `pnpm run test`

These checks validate documentation hygiene, security policy, changelog process, workspace metadata, and placeholder
package scripts. Phase 1 intentionally does not add production feature tests because no production features are
implemented.

## Phase 2 Checks

- `pnpm run phase2:check`
- `pnpm --filter @graphview/web build`
- API tests through `pnpm --filter @graphview/api-contract test`
- Worker tests through `pnpm --filter @graphview/worker-contract test`

Phase 2 tests cover health/version endpoints, local auth rejection, worker stage ordering, shared TypeScript contract
presence, and the product-first web shell.

## Phase 3 Checks

- `pnpm run phase3:check`
- API workflow tests for source CRUD, proposal review commits, search, import, and export.
- Web shell tests for source and review controls.

## Phase 4 Checks

- `pnpm run phase4:check`
- API tests for text ingestion, backend URL fetch, proposal creation, embedding persistence, and review linkage.
- Worker tests for markdown normalization, deterministic embeddings, proposal generation, stage ordering, and PDF parsing.
- Web shell tests for the ingestion control and API route wiring.

## Phase 5 Checks

- `pnpm run phase5:check`
- API tests for role-enforced reads/writes, operator-only metrics, backup creation, and full restore of reviewed graph
  state.
- Graph-core tests for bounded render plan helpers and omitted-node/edge accounting.
- Web shell tests for API shape normalization and bounded graph-render budget wiring.
- Release readiness checks for documented hardening, observability, backup/restore, and release commands.

## Phase 6 Checks

- `pnpm run phase6:check`
- API tests for lens discovery, multi-lens ingestion, code symbol and dependency proposals, ops document ownership, and
  review metadata extraction.
- Worker tests for deterministic repository and ops-document proposal generation.
- Web shell tests for graph lens discovery wiring and source-kind-controlled ingestion.
- Shared contract tests for extraction and graph lens identifiers.

## Phase 7 Checks

- `pnpm run phase7:check`
- API tests for generated `semantic_edge` proposals, endpoint-node resolution, conflict response when endpoints are not
  accepted, and successful edge commits after node review.
- Worker tests for deterministic relationship proposal generation in Engineering and Ops extraction lenses.
- Web shell tests for relationship proposal visibility in the review queue.

## Phase 8 Checks

- `pnpm run phase8:check`
- API tests for source, node, edge, and missing-entity lineage trace responses.
- Web shell tests for `/lineage` route wiring and lineage card visibility.
- Release readiness checks for documented lineage endpoints and Phase 8 acceptance commands.

## Phase 9 Checks

- `pnpm run phase9:check`
- API tests for `/insights` graph counts, review progress, connected edges, top nodes, and provenance coverage.
- Graph-core contract tests for summary diagnostics.
- Web shell tests for `/insights` route wiring and insight card visibility.
- Release readiness checks for documented insight endpoints and Phase 9 acceptance commands.

## Phase 10 Checks

- `pnpm run phase10:check`
- API tests for `/graph/neighborhood/{node_id}` depth, center-node, edge, and missing-node behavior.
- Graph-core contract tests for focused neighborhood extraction.
- Web shell tests for `/graph/neighborhood` route wiring and neighborhood card visibility.
- Release readiness checks for documented neighborhood endpoints and Phase 10 acceptance commands.

## Phase 11 Checks

- `pnpm run phase11:check`
- API tests for `/graph/path` found, no-path, max-depth, and missing-node behavior.
- Graph-core contract tests for bounded shortest-path extraction.
- Web shell tests for `/graph/path` route wiring and path card visibility.
- Release readiness checks for documented path endpoints and Phase 11 acceptance commands.

## Phase 12 Checks

- `pnpm run phase12:check`
- API tests for `/review-queue` ready proposals, blocked relationship proposals, counts, ordering, and source metadata.
- Web shell tests for `/review-queue` route wiring and worklist card visibility.
- Shared contract tests for review worklist response types.
- Release readiness checks for documented review worklist endpoints and Phase 12 acceptance commands.

## Phase 13 Checks

- `pnpm run phase13:check`
- API tests for `/review-dashboard` proposal volume, ready/blocked counts, decision mix, reviewer counts, and rates.
- Web shell tests for `/review-dashboard` route wiring and dashboard card visibility.
- Shared contract tests for review dashboard response types.
- Release readiness checks for documented review dashboard endpoints and Phase 13 acceptance commands.

## Phase 14 Checks

- `pnpm run phase14:check`
- API tests for `/review-activity` recent decision ordering, limit handling, proposal joins, and source joins.
- Web shell tests for `/review-activity` route wiring and activity card visibility.
- Shared contract tests for review activity response types.
- Release readiness checks for documented review activity endpoints and Phase 14 acceptance commands.

## Phase 15 Checks

- `pnpm run phase15:check`
- API tests for `/review-sources` source ordering, pending/reviewed counts, decision mix, and limit handling.
- Web shell tests for `/review-sources` route wiring and source review card visibility.
- Shared contract tests for source review coverage response types.
- Release readiness checks for documented source review coverage endpoints and Phase 15 acceptance commands.

## Phase 16 Checks

- `pnpm run phase16:check`
- Web shell tests for the full Knowledge Graph Builder workspace, outline, inspector, graph stage, layout dock, ingest
  controls, and API-backed review surfaces.
- Browser smoke tests against the live local app to verify the full graph workspace renders from API data without console
  warnings or errors.
- Release readiness checks for documented full graph workspace scope and Phase 16 acceptance commands.

## Phase 17 Checks

- `pnpm run phase17:check`
- API tests for connector account and target CRUD, redacted token responses, manual sync, resync idempotency, stale remote
  source markers, optional LLM extraction, source chunks, proposals, embeddings, and auto-commit decisions.
- Worker tests for the connector-aware stage plan from fetch through review commit.
- Web shell tests for connector setup, sync controls, inherited LLM and auto-commit settings, source hierarchy, and
  connector status surfaces.
- Shared contract tests for connector, source chunk, graph settings, topic, origin metadata, and expanded relation types.

## Phase 18-22 Checks

- `pnpm run phase22:check`
- API tests for provider catalog redaction, planning session lifecycle, graph build specs, read-only graph query
  citations, research-created sources/proposals, permission checks, export coverage, and action approval.
- Provider tests for mocked OpenAI Responses, Anthropic Messages, and Gemini generate-content request payloads, disabled
  provider behavior, and structured output parsing.
- Worker tests for the AI stage plan from `agent.plan` through `agent.action.apply`.
- Web shell tests for Planning Mode, embedded Graph AI command flow, citation drawer, research status, and action approval
  UI wiring.
- Shared contract tests for planning sessions, messages, graph build specs, agent runs, steps, citations, research tasks,
  action proposals, and provider descriptors.

## Phase 23 Checks

- Expected command: `pnpm run phase23:check`.
- Web shell tests cover Overview, Focus, Evidence, Review, Sources, and Planning labels, source reader actions, typed
  Needs attention work items, embedded graph AI controls, and grouped 2D/3D graph controls.
- API and shared contract tests cover agent tool catalog and tool-call surfaces when those contracts are active.

## Phase 24 Checks

- Expected command: `pnpm run phase24:check`.
- Web source tests in `apps/web/tests/shell.test.mjs` assert Phase 24 living graph contracts: graph visual state,
  tooltip model, activity event model, `/graph/activity`, `/agent-runs/{agent_run_id}/activity`, tooltip/tether
  selectors, reduced-motion handling, and candidate/activity layers.
- Playwright browser scaffold in `apps/web/tests/browser/` verifies nonblank 2D and 3D graph rendering through PNG pixel
  checks and validates tethered tooltip URL behavior with mocked API data.
- Browser QA should run against desktop and mobile Chromium projects, with API responses intercepted so it does not
  require a live FastAPI service.
- Phase 24 browser checks run through the committed package scripts and dependency catalog for `@playwright/test`,
  `pngjs`, `three`, and `@types/three`.
- Reduced-motion, keyboard focus, hover tooltip parity, graph activity overlays, candidate proposal layers, and 2D/3D
  interaction parity remain required coverage before Phase 24 is marked complete.

## Phase 25 Checks

- Expected command: `pnpm run phase25:check`.
- API tests cover the full digital nervous system loop: signal routing, observation/alert/Attention creation, decision
  records, review-gated action proposals, approved action runs, outcomes, feedback events, graph activity replay,
  reader/operate permission boundaries, redacted payloads, and backup coverage.
- Web source tests cover the graph-centered Attention mode, Phase 25 REST routes, operating-loop controls, and shared
  Phase 25 visual statuses in `graph-core` and `GraphCanvas`.
- Browser checks continue to run the Phase 24 nonblank 2D/3D graph and tooltip URL coverage so the new activity states
  do not regress the primary graph workspace.

## Phase 26 Checks

- Expected command: `pnpm run phase26:check`.
- Web build checks must show the 3D renderer split into a lazy-loaded chunk so default 2D sessions do not eagerly load
  Three.js.
- API tests cover configurable safe-action allowlists, project-scoped source mutation execution, graph activity stream
  anti-buffering headers, and linear Alembic migration metadata through Phase 24 and Phase 25 tables.
- Browser checks continue to run desktop and mobile nonblank graph rendering and tooltip URL coverage, with Playwright
  artifacts cleaned before and after the gate.
- Pytest warning filters suppress only the known external Starlette TestClient deprecation so new warnings remain
  visible in local checks.

## Phase 27 Checks

- Expected command: `pnpm run phase27:check`.
- Focused smoke command: `pnpm run phase27:smoke`. It starts a temporary local API and verifies capture-only token
  normalization, gateway event capture, event checksums, redaction, content permissions, graph projection, and
  `end-session` PATCH behavior.
- API tests cover adapter token creation with capture-only scope normalization, session lifecycle, idempotent event
  batches, event checksums, redaction and encrypted-at-rest blob storage, content read permissions, context graph
  projection, SSE framing, retention purge with metadata preservation, default metadata-only backup, opt-in encrypted
  content backup/restore, and linear migration continuity through the active context tables.
- Gateway tests cover MCP-compatible tool manifests, file range capture, denied paths, secret redaction, batch event
  shaping, and offline outbox retry.
- VS Code/Cursor extension tests cover editor selection mapping as `passive_reconciled` telemetry plus offline outbox
  replay behavior.
- Web source tests cover the Active Context workspace, `/agent-context` routes, authority badges, shared context types,
  and existing 2D/3D browser graph QA mocks.
- Worker tests cover the context normalization, enrichment, and retention stage plan.

## Future Test Paths

- Web unit and component tests: `apps/web/src`.
- API unit and integration tests: `services/api/tests`.
- Worker unit and integration tests: `services/worker/tests`.
- Shared contracts: `packages/shared-types/src`.
- Graph model tests: `packages/graph-core/src`.
- Design system tests: `packages/design-system/src`.

## Required Coverage Areas From Phase 2 Onward

- Health and version endpoints. Initial coverage exists in Phase 2.
- Auth adapter behavior. Initial local-dev rejection coverage exists in Phase 2.
- Source CRUD and provenance persistence. Initial coverage exists in Phase 3.
- Ingestion idempotency. Initial deterministic ingestion coverage exists in Phase 4.
- Proposal review decisions. Initial coverage exists in Phase 3.
- Graph update transactions. Initial accepted-node commit coverage exists in Phase 3.
- Search behavior. Initial source and node search coverage exists in Phase 3.
- Graph rendering interaction and large-graph performance. Initial bounded render plan coverage exists in Phase 5.
- AI planning, graph query, and research review gates. Initial coverage exists in Phase 18-22.
- Living graph animation, tooltips, tethers, graph activity replay, candidate proposal previews, and 2D/3D browser
  rendering. Initial source and browser scaffold coverage exists in Phase 24.

## Failure Modes

- Placeholder tests mistaken for feature coverage.
- Contract changes without API and worker tests.
- Review flow changes without provenance assertions.
- Slow ingestion tests blocking local feedback without integration-test separation.
- Browser smoke tests that only check DOM presence and miss blank SVG/canvas output.
- Tooltip URL actions that navigate the current workspace, omit `rel` protections, or lose their graph tether.
