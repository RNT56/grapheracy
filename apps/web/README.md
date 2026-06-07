# Web App

Purpose: React 19.2, TypeScript, and Vite 8 product UI for graph exploration, source review, proposal review, AI
planning, embedded graph Q&A, and scoped research.

Owner: frontend worker.

Entrypoints:

- `src/main.tsx`
- `src/App.tsx`
- `src/GraphCanvas.tsx`

Commands:

- `pnpm --filter @graphview/web dev`
- `pnpm --filter @graphview/web build`
- `pnpm --filter @graphview/web typecheck`
- `pnpm --filter @graphview/web test`

Environment variables:

- `GRAPHVIEW_PUBLIC_BASE_URL`
- `GRAPHVIEW_API_BASE_URL`

Test path: `apps/web/tests`.

Phase 5 graph rendering uses `@graphview/graph-core` render plans to filter orphan edges, cap visible large-graph
payloads, preserve deterministic layout, and surface omitted node/edge counts in the graph tool.
Phase 6 adds active graph lens selection backed by `/graph-lenses`, while ingestion uses `/extraction-lenses` to run
signal-gated Research, Engineering, and Ops extraction by default.
Phase 7 surfaces pending relationship proposals so reviewers can see edge work separately from node work.
Phase 8 surfaces lineage summaries for reviewed graph items using `/lineage`.
Phase 9 surfaces graph insight summaries using `/insights`.
Phase 10 surfaces focused neighborhood summaries using `/graph/neighborhood/{node_id}`.
Phase 11 surfaces bounded path summaries using `/graph/path`.
Phase 12 surfaces prioritized review worklist summaries using `/review-queue`.
Phase 13 surfaces review dashboard summaries using `/review-dashboard`.
Phase 14 surfaces recent review activity using `/review-activity`.
Phase 15 surfaces source review coverage using `/review-sources`.
Phase 16 replaces the compact shell with the full Knowledge Graph Builder workspace: outline, graph stage, inspector,
ingest controls, review operations, and layout dock. Force, Radial, Arc, 2D, 3D, Contents, Fit, graph search, node
selection, and collapsible panels are wired in the React shell.
Phases 18-22 add a separate Planning Mode workspace with session rail, chat surface, graph build preview, and provider
status, plus embedded graph AI controls in the existing graph workspace. Graph Q&A stays read-only and shows citations.
Scoped research starts agent runs and displays review-gated action proposals without inventing local graph mutations.
Phase 24 adds living graph activity, tethered tooltips, reduced-motion handling, and 2D/3D renderer parity. Phase 25 adds
the graph-centered Attention mode for the digital nervous system loop: signals, alerts, owners, routing policies,
decision records, gated action proposals, action runs, outcomes, and feedback are surfaced without bypassing review or
operate permissions.

Failure modes: graph rendering performance regressions, stale API contracts, auth adapter mismatch, provenance UI
omissions, locally-invented AI graph changes, missing citations, and compact-control text overflow.
