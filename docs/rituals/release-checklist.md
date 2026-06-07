# Release Checklist

1. Consolidate `docs/changelog/unreleased/` into `CHANGELOG.md`.
2. Capture a `GET /backup` bundle and confirm the restore target and rollback owner.
3. Verify `GET /observability/ready` and admin-only `GET /observability/metrics`.
4. Verify `GET /extraction-lenses` includes Research, Engineering, and Ops, and `GET /graph-lenses` includes All.
5. Verify repository ingestion produces at least one Engineering-tagged `semantic_edge` proposal.
6. Verify `GET /lineage/edge/{edge_id}` connects the reviewed edge to source, proposals, review decisions, and
   provenance.
7. Verify `GET /insights` reports current graph counts, review progress, and provenance coverage.
8. Verify `GET /graph/neighborhood/{node_id}` returns a bounded focused graph with omitted counts.
9. Verify `GET /graph/path` returns a bounded path or explicit no-path result between reviewed nodes.
10. Verify `GET /review-queue` reports ready and blocked pending proposals with missing endpoint IDs.
11. Verify `GET /review-dashboard` reports proposal volume, decision mix, reviewer counts, and acceptance/commit rates.
12. Verify `GET /review-activity` reports recent decisions with proposal and source context.
13. Verify `GET /review-sources` reports source-level pending and reviewed proposal counts.
14. Verify the web app shows the full Knowledge Graph Builder workspace with outline, graph stage, inspector, and dock.
15. Verify `GET /providers` redacts credentials and reports enabled providers, defaults, and capabilities.
16. Verify Planning Mode can create a session, append messages, and persist a graph build spec without mutating the
    graph.
17. Verify `POST /graph/query` returns citations and does not create sources, proposals, nodes, or edges.
18. Verify `POST /graph/research` creates sources, chunks, proposals, and a pending action proposal with provenance.
19. Verify `POST /agent-runs/{agent_run_id}/approve-action` is the only AI endpoint that applies an action proposal.
20. Verify the web app shows Planning Mode, embedded graph AI command controls, citation drawer, research status, and
    action approval sheet without compact-control overflow.
21. Run `pnpm run phase22:check`.
22. Run `pnpm run release:check`.
23. Run full CI security gates.
24. Generate SBOMs for app, API, and worker images.
25. Confirm no release-blocking security criteria in `../../SECURITY.md`.
26. Confirm runtime image users are non-root.
27. Tag release after coordinator approval.
