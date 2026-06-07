# Worker Service

Purpose: async worker contract and deterministic ingestion primitives for source extraction, analysis, proposal
generation, and review-aware commit planning.

Owner: worker systems worker.

Entrypoints:

- Worker contract: `worker-contract.md`
- Worker module: `services/worker/src/graphview_worker`
- Ingestion primitives: `services/worker/src/graphview_worker/ingestion.py`

Commands:

- `pnpm --filter @graphview/worker-contract dev`
- `pnpm --filter @graphview/worker-contract typecheck`
- `pnpm --filter @graphview/worker-contract test`

Environment variables: `POSTGRES_*`, `MINIO_*`, `ARQ_REDIS_URL`, `GRAPHVIEW_ENV`, provider keys and model defaults
documented in `../api/README.md`, and graph-level AI settings persisted by the API.

Test path: `services/worker/tests`.

Phase 4 supports deterministic text/markdown/PDF extraction, local hash embeddings, and heuristic content-node proposal
generation. URL fetch runs through the API boundary so network retrieval stays inside the authenticated API surface.
Phase 6 extends the same deterministic primitives to repository and ops-document sources through extraction-lens
proposal generation.
Phase 7 adds deterministic relationship proposal generation for semantic edges between extracted candidates.
Phase 17 adds connector source normalization, chunking, hierarchy generation, optional LLM extraction, and
confidence-threshold auto-commit.
Phases 18-22 add AI agent stage names for planning, retrieval, reasoning, research fetch, proposal generation,
review-waiting actions, and approved action application. Agent execution must reuse the API repository, source
ingestion, proposal, and review paths instead of writing graph nodes or edges directly.

Failure modes: non-idempotent retries, untraceable stages, duplicate proposals, extraction-lens drift, failed
PDF extraction, relationship endpoints without accepted nodes, provider retries without trace IDs, duplicate research
sources, and graph commits without review state.
