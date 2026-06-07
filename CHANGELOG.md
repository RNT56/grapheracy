# Changelog

All notable changes to Graphview are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses SemVer once the first
versioned release is cut. Before release consolidation, multi-worker changes land as fragments under
`docs/changelog/unreleased/`.

## [Unreleased]

### Added

- Phase 1 project foundation for a monorepo-based internal knowledge graph product.
- Repo-markdown documentation system with ADRs, rituals, and changelog fragments.
- Security and dependency governance policy before broad dependency adoption.
- Contract skeletons for shared graph types, API endpoints, worker stages, and events.
- CI skeletons for lint, typecheck, tests, audits, secret scanning, docs hygiene, and changelog validation.
- Runnable Phase 2 scaffolds for the React/Vite web app, FastAPI API, async worker stage plan, local auth stub, and
  baseline Alembic migration.
- Phase 3 core graph workflow with persistent source CRUD, proposal review commits, provenance, search, import/export,
  and a web shell wired to those endpoints.
- Phase 4 ingestion workflow with text, markdown, backend URL fetch, PDF extraction, deterministic local embeddings,
  provider-boundary proposal generation, and web shell ingestion controls.
- Phase 5 hardening with bounded graph rendering, local role enforcement, observability endpoints, full backup/restore,
  and executable release readiness checks.
- Phase 6 mode extensions with mode discovery, engineering repository ingestion, and ops document map ingestion.
- Phase 7 relationship proposal generation with reviewed endpoint guards and web queue visibility for pending edges.
- Phase 8 lineage trace endpoints and web summaries for sources, proposals, reviewed nodes, and reviewed edges.
- Phase 9 graph insight diagnostics for review progress, graph quality, top connected nodes, and provenance coverage.
- Phase 10 focused graph neighborhoods for reviewed-node exploration in the API, graph-core, and web shell.
- Phase 11 bounded shortest-path exploration between reviewed graph nodes in the API, graph-core, and web shell.
- Phase 12 prioritized review worklists with ready/blocked proposal metadata and web queue summaries.
- Phase 13 review dashboards with proposal volume, pending readiness, decision mix, reviewer activity, and
  acceptance/commit-rate summaries.
- Phase 14 review activity feeds with recent decisions, proposal context, source context, and web summaries.
- Phase 15 source review coverage with per-source pending/reviewed proposal counts, decision mix, and web summaries.
- Phase 16 full Knowledge Graph Builder workspace UI with outline, graph stage, inspector, ingest controls, review
  operations, and layout dock.
- Phase 17 connector setup, manual sync/resync, source chunks, topic hierarchy, inherited LLM extraction settings, and
  confidence-threshold auto-commit with provenance.
- Phases 18-22 AI-native planning, graph Q&A, scoped research, provider catalog support for OpenAI, Anthropic, Gemini,
  citations, durable agent state, and review-gated AI action proposals.
- Phase 25 digital nervous system loop with persisted signals, observations, alerts, Attention items, owners, routing
  policies, decision records, gated action proposals/runs, outcomes, feedback events, activity replay, backup/restore,
  and a graph-centered Attention mode in the web workspace.

### Changed

- Preserved the standalone prototype as reference material at `prototypes/knowledge-graph-explorer.html`.

### Security

- Added strict dependency approval requirements, lockfile review rules, delayed npm package adoption, and secret handling
  expectations.
- Added AI provider secret handling, private-source retrieval, trace/audit, credential redaction, and review-gated
  mutation requirements.
- Added Phase 25 safe-action gates, operate/review permission checks, redacted action payloads, and no side-effect replay
  on restore for persisted nervous-system records.
