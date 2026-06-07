# API Service

Purpose: FastAPI service for auth, graph data, sources, ingestion runs, proposals, review decisions, provenance, AI
workflows, graph activity, and digital nervous system records.

Owner: backend worker.

Entrypoints:

- Generated OpenAPI contract: `openapi.yaml`
- App module: `services/api/src/graphview_api`
- Ingestion adapters: `services/api/src/graphview_api/ingestion.py`
- Connector adapters: `services/api/src/graphview_api/connectors.py`
- Optional LLM extraction and AI agent providers: `services/api/src/graphview_api/llm.py`
- Repository: `services/api/src/graphview_api/repository.py`
- Schemas: `services/api/src/graphview_api/schemas.py`
- Data schema reference: `docs/09-data-schema.md`
- Observability: `services/api/src/graphview_api/observability.py`

Commands:

- `pnpm --filter @graphview/api-contract dev`
- `pnpm --filter @graphview/api-contract typecheck`
- `pnpm --filter @graphview/api-contract test`

Environment variables: `POSTGRES_*`, `MINIO_*`, `OIDC_*`, `GRAPHVIEW_API_BASE_URL`, `GRAPHVIEW_ENV`,
`GRAPHVIEW_SECRET_KEY`, `GRAPHVIEW_LLM_*`, `GRAPHVIEW_AUTO_COMMIT_THRESHOLD`, `GRAPHVIEW_OPENAI_API_KEY`,
`GRAPHVIEW_SAFE_ACTION_TYPES`, `GRAPHVIEW_OPENAI_BASE_URL`, `GRAPHVIEW_OPENAI_MODEL`, `GRAPHVIEW_ANTHROPIC_API_KEY`,
`GRAPHVIEW_ANTHROPIC_BASE_URL`, `GRAPHVIEW_ANTHROPIC_MODEL`, `GRAPHVIEW_GEMINI_API_KEY`,
`GRAPHVIEW_GEMINI_BASE_URL`, and `GRAPHVIEW_GEMINI_MODEL`.

Runnable endpoints:

- `GET /graph`
- `GET /graph/settings`
- `PATCH /graph/settings`
- `GET /graph/neighborhood/{node_id}`
- `GET /graph/path`
- `GET /insights`
- `GET /extraction-lenses`
- `GET /graph-lenses`
- `GET /lineage/{entity_kind}/{entity_id}`
- `GET /graph/activity`
- `GET /graph/activity/stream`
- `GET /observability/ready`
- `GET /observability/metrics`
- `GET /sources`
- `GET /source-chunks`
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
- `GET /connectors`
- `GET /connector-accounts`
- `POST /connector-accounts`
- `GET /connector-targets`
- `POST /connector-targets`
- `PATCH /connector-targets/{target_id}`
- `GET /connector-sync-runs`
- `POST /connector-sync-runs`
- `GET /connector-sync-runs/{sync_run_id}`
- `GET /providers`
- `POST /planning-sessions`
- `GET /planning-sessions`
- `GET /planning-sessions/{session_id}`
- `POST /planning-sessions/{session_id}/messages`
- `POST /planning-sessions/{session_id}/build-spec`
- `POST /agent-runs`
- `GET /agent-runs/{agent_run_id}`
- `POST /agent-runs/{agent_run_id}/approve-action`
- `POST /graph/query`
- `POST /graph/research`
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
- `PATCH /owners/{owner_id}`
- `GET /routing-policies`
- `POST /routing-policies`
- `PATCH /routing-policies/{policy_id}`
- `GET /decision-records`
- `POST /decision-records`
- `GET /action-proposals`
- `POST /action-proposals`
- `POST /action-proposals/{action_proposal_id}/approve`
- `POST /action-proposals/{action_proposal_id}/reject`
- `GET /action-runs`
- `POST /action-runs`
- `GET /outcomes`
- `POST /action-runs/{action_run_id}/outcome`
- `GET /feedback-events`
- `POST /feedback-events`

Test path: `services/api/tests`.

Phase 4 ingestion supports inline text, markdown, backend URL fetch, and PDF text extraction. It writes a source,
ingestion run, reviewable proposals, provenance, and deterministic local embeddings in one repository transaction.
Phase 5 adds local seeded-user role enforcement, readiness and in-memory request metrics, and operator-only full
backup/restore.
Phase 6 adds mode discovery plus `repository` and `ops-document` ingestion for engineering repository maps and general
ops document maps.
Phase 7 adds deterministic `semantic_edge` proposals and guards edge review commits until endpoint nodes are accepted.
Phase 8 adds lineage trace endpoints for sources, proposals, reviewed nodes, and reviewed edges.
Phase 9 adds graph insight diagnostics for review progress, graph quality, top connected nodes, and provenance coverage.
Phase 10 adds bounded focused graph neighborhoods for reviewed-node exploration.
Phase 11 adds bounded shortest paths between reviewed graph nodes.
Phase 12 adds prioritized review worklists for pending proposals and blocked relationships.
Phase 13 adds review dashboard summaries for proposal volume, pending readiness, decision mix, reviewer activity, and
acceptance/commit rates.
Phase 14 adds review activity feeds for recent decisions with related proposal and source context.
Phase 15 adds source review coverage for per-source proposal counts, pending/reviewed splits, and decision mix.
Phase 17 adds connector accounts, targets, sync runs, source chunks, topic hierarchy, inherited extraction settings,
provider-boundary LLM extraction, and confidence-threshold auto-commit.
Phases 18-22 add durable planning sessions, agent runs, research tasks, provider catalog descriptors, graph Q&A,
scoped research, citations, and review-gated AI action proposals. `POST /graph/query` is read-only. `POST
/graph/research` creates sources, chunks, and extraction proposals through existing ingestion paths. AI action approval
is the only endpoint that applies an agent proposal.
Phase 25 adds the digital nervous system loop: persisted signals, observations, alerts, Attention items, owners, routing
policies, decision records, review-gated action proposals, safe action runs, outcomes, feedback events, activity replay,
and backup/restore coverage. Action payloads are redacted in API responses and restored bundles do not replay side
effects. Phase 26 makes the safe action execution allowlist configurable, scopes source freshness actions to the
proposal project, adds activity stream anti-buffering headers, and validates migration continuity through the activity
and digital nervous system tables.

The static `openapi.yaml` is generated from the FastAPI app. When request or response models change, update
`schemas.py`, run the API tests, regenerate `openapi.yaml`, and update `docs/09-data-schema.md` if persistence or public
contract semantics changed.

Failure modes: OpenAPI drift, auth adapter mismatch, over-permissive operator endpoints, failed URL/PDF extraction,
lens descriptor drift, premature relationship commits, incomplete lineage traces, stale insight summaries, unbounded
neighborhood responses, unbounded path queries, stale review worklists, stale review dashboards, incomplete review
activity context, incomplete source review coverage, connector token leakage, duplicate sync proposals, incomplete chunk
provenance persistence, provider secret leakage, silent cross-provider fallback, uncited AI answers, unreviewed AI
mutations, restore bundle drift, and migration rollback gaps.
