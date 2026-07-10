# Release Checklist

1. Consolidate `docs/changelog/unreleased/` into `CHANGELOG.md`.
2. Capture a logical `GET /backup` bundle, run the production `graphview-ops backup` plus `verify`, and confirm the
   maintenance window, restore target, object manifest, and rollback owner.
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
21. Verify `POST /agent-context/clients` returns a one-time redacted `gvctx_...` adapter token for maintainers.
22. Verify `POST /agent-context/sessions`, `PATCH /agent-context/sessions/{session_id}`, and
    `POST /agent-context/events/batch` accept capture-only bearer tokens, normalize requested scopes to
    `context:capture`, and reject normal UI credentials.
23. Verify `GET /agent-context/sessions`, `GET /agent-context/sessions/{session_id}/events`, and
    `GET /agent-context/sessions/{session_id}/graph` expose authority-labeled context timelines and graph projections.
24. Verify event batch responses and session event reads include API-generated checksums for accepted events.
25. Verify `GET /agent-context/artifacts/{artifact_id}/content` requires maintainer permission and never returns raw
    adapter tokens, provider keys, private keys, or unredacted command environments.
26. Run `pnpm run test:agent-context:live` and verify ordered offline replay, stable `Last-Event-ID` SSE resume,
    encrypted object capture, redaction, and terminal session state against the exact candidate images.
27. In the same live proof, verify `POST /agent-context/retention/run` deletes the expired object while preserving its
    metadata audit record.
28. Verify `GET /backup` omits active-context encrypted content by default and
    `GET /backup?include_agent_context_content=true` includes encrypted blob envelopes only when explicitly requested.
29. Run `pnpm run test:secrets:live` against the exact candidate images and confirm stable-reference Vault rotation,
    legacy database-envelope migration, response redaction, database neutralization, and permanent Vault purge.
30. Run `pnpm run test:backup-restore:live` against the exact candidate images and confirm restored connector/provider
    credentials, adapter sessions, Redis sessions, jobs, outbox events, and actions are inert.
31. Verify `services/agent-gateway` and `apps/vscode-extension` pass tests and document retryable offline, rate-limit,
    conflict, and server outbox behavior. Confirm permanent 4xx responses are not queued.
32. Run `pnpm run test:performance:live` on the 100k-node/500k-edge seed and retain the four-route p95 JSON receipt.
33. Run `pnpm run test:smoke`, `pnpm run quality:full`, and `pnpm run release:verify`.
34. Run full CI security gates.
35. Run `pnpm run release:artifacts:verify`, then confirm tag CI generates SBOMs for all release images and packaged
    gateway/extension artifacts, records all image digests, verifies the annotated tag, and signs the checksum manifest.
36. Confirm no release-blocking security criteria in `../../SECURITY.md`.
37. Confirm runtime image users are non-root.
38. Tag release after coordinator approval.
