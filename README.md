# Graphview

Graphview is an internal knowledge graph product for ingesting mixed sources, extracting and reviewing concepts,
preserving provenance, and exploring relationships in an interactive graph.

The repository is in Phase 27: active agent context connectors on top of the digital nervous system loop, AI-native
planning, graph Q&A, scoped research, provider registry hardening, and connector-backed graph building for uploads,
URLs, repositories, Google Workspace, and Notion. Planning Mode is a separate workspace, while continued research,
graph questions, graph-centered Attention, and active agent context operate through the existing source, proposal,
review, provenance, lineage, and activity flows. The standalone prototype is preserved as UX evidence at
`prototypes/knowledge-graph-explorer.html`; it is not production code.

Phase 27 is the current release-readiness gate through `pnpm run phase27:check`; Phase 22 remains available through
`pnpm run phase22:check` as the historical AI V1 baseline.

## Start Here

- Maintainer and agent entrypoint: `CLAUDE.md`
- Human documentation entrypoint: `docs/00-start-here.md`
- Product goals: `docs/01-product-goals.md`
- Architecture: `docs/02-architecture.md`
- Security: `docs/03-security.md`
- Development: `docs/04-development.md`
- Testing: `docs/05-testing.md`
- Operations: `docs/06-operations.md`
- Agent workflows: `docs/07-agent-workflows.md`
- Roadmap: `docs/08-roadmap.md`
- Data schema: `docs/09-data-schema.md`
- User journeys and value map: `docs/10-user-journeys-and-value-map.md`
- Living graph UI vision and upgrade plan: `docs/11-living-graph-ui-vision-and-upgrade-plan.md`
- Digital nervous system Phase 25 plan: `docs/12-digital-nervous-system-phase25-plan.md`
- Active agent context connectors: `docs/13-active-agent-context-connectors.md`
- Changelog: `CHANGELOG.md`
- Security policy: `SECURITY.md`

## Local Setup

Required for local checks:

- Node 24 Active LTS target; local validation scripts use standard Node APIs.
- pnpm 10.27 or newer.
- Python 3.14 target for services.
- uv for Python workspace management.
- Docker for local service orchestration.

```sh
pnpm install --frozen-lockfile
uv python install 3.14.5
pnpm run phase27:check
```

Phase 4 provides runnable app, API, and worker scaffolds plus source CRUD, proposal review commits, provenance, search,
import/export, text/markdown/URL/PDF ingestion, deterministic local embeddings, and reviewable proposal generation.
Phase 5 adds bounded large-graph rendering, role-enforced API actions, readiness and metrics endpoints, full
backup/restore, and release readiness checks.
Phase 6 adds mode discovery, engineering repository ingestion for code symbols and dependencies, and ops document map
ingestion for policies, processes, vendors, incidents, projects, ownership, and review metadata.
Phase 7 adds deterministic semantic edge proposals, endpoint-node commit guards, and relationship visibility in the web
review queue.
Phase 8 adds lineage trace endpoints and web summaries that connect reviewed graph items back to source, ingestion run,
proposal, review decision, and provenance.
Phase 9 adds graph insight diagnostics for counts, review progress, top connected nodes, orphan edges, and provenance
coverage.
Phase 10 adds focused graph neighborhoods for reviewed nodes, with bounded API responses and web summaries for immediate
context around high-signal nodes.
Phase 11 adds bounded shortest paths between reviewed nodes, with deterministic API and graph-core traversal plus a web
summary for graph connections.
Phase 12 adds a prioritized review worklist that separates ready proposals from blocked relationship proposals and
surfaces the next review action.
Phase 13 adds a review dashboard that summarizes proposal volume, pending readiness, decision mix, reviewer activity,
and acceptance/commit rates.
Phase 14 adds a review activity feed that shows recent decisions with related proposal and source context.
Phase 15 adds source review coverage that shows which sources still have pending proposal work.
Phase 16 replaces the compact shell with a full Knowledge Graph Builder workspace: floating outline, graph stage,
inspector, ingest controls, review operations, and a prototype-style layout dock. The dock now drives Force, Radial,
Arc, 2D, 3D, Contents, Fit, and graph search states, with collapsible outline and inspector panels.
Phase 17 adds connector setup, manual sync/resync, source chunks, topic hierarchy, inherited LLM extraction settings,
and confidence-threshold auto-commit with provenance.
Phases 18-22 add durable planning and agent records, provider catalog support for OpenAI, Anthropic, Gemini, and the
local deterministic provider, a polished Planning Mode workspace, embedded graph Q&A, scoped research that creates
sources/chunks/proposals, citation drawers, and review-gated AI action proposals.
Phase 24 adds the living graph UI, activity overlays, tethered explanatory tooltips, reduced-motion behavior, and 2D/3D
renderer parity. Phase 25 adds persisted signals, observations, alerts, Attention items, owners, routing policies,
decision records, gated action proposals/runs, outcomes, feedback events, backup/restore coverage, and the web Attention
mode for the digital nervous system loop. Phase 26 lazy-loads the 3D renderer, hardens action execution policy,
validates migration continuity, tightens activity stream delivery, and cleans browser QA artifacts. Phase 27 adds
scoped `gvctx_...` adapter tokens, `/agent-context/sessions`, `/agent-context/events/batch`, encrypted redacted context
blobs, the local agent gateway, VS Code/Cursor telemetry, worker enrichment stages, and the Active Context web lens.

```sh
pnpm --filter @graphview/web dev
pnpm --filter @graphview/api-contract dev
pnpm --filter @graphview/worker-contract dev
```

## Repository Layout

- `apps/web`: React/Vite product UI shell.
- `apps/docs-app`: future docs app consuming repo markdown.
- `apps/vscode-extension`: VS Code-compatible active context adapter for VS Code and Cursor.
- `services/api`: FastAPI service and generated OpenAPI contract.
- `services/agent-gateway`: local MCP-compatible active context gateway and Codex/Claude wrapper helpers.
- `services/worker`: ingestion worker contract and deterministic ingestion primitives.
- `packages/shared-types`: shared public TypeScript contracts.
- `packages/graph-core`: graph model and rendering abstraction boundary.
- `packages/design-system`: design tokens and shared UI primitives boundary.
- `docs`: source of truth for product, architecture, security, operations, and roadmap.
- `infra`: Docker, Compose, and operational scripts.
- `prototypes`: preserved reference prototypes.

## Remote

Canonical remote: `https://github.com/RNT56/grapheracy.git`
