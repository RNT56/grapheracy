# Product Goals

## Purpose

Graphview is an AI-native knowledge graph and agent workbench. Users ingest mixed knowledge sources, let agents read
and structure them, review proposed graph changes, preserve provenance, and use the resulting graph as durable context
for research and planning work.

## V1 Audience

- Internal research teams mapping literature, notes, interviews, and documents.
- Personal knowledge workflows that need provenance and review instead of opaque summarization.

## V1 Scope

- Single internal organization.
- Role-based access within that organization.
- Source records with provenance.
- Ingestion runs with traceable worker stages.
- Extraction proposals reviewed before graph commits.
- Interactive graph exploration.
- A graph-centered user interface where the visual knowledge graph is the primary workspace and shows meaningful
  hover, focus, evidence, proposal, review, and agent-activity states.
- Chat-centric Planning Mode where agents read sources, run research, produce artifacts, and propose graph changes.
- Contextual agent tools for graph query, source search/open, research, proposal creation, review actions, connector
  sync, and layout changes.
- A digital nervous system operating loop for signals, observations, attention routing, decisions, approved actions,
  outcomes, and feedback into graph memory.
- Postgres-backed full-text search.
- S3-compatible object storage for source artifacts.

## Non-V1 Scope

- Multi-tenant SaaS.
- Public anonymous access.
- Marketplace ingestion plugins.
- Real-time collaborative editing.
- OpenSearch or Meilisearch unless Postgres search becomes measured bottleneck.
- Heavy graph rendering commitment before Sigma.js and Cosmograph are evaluated in Phase 2.

## Upgrade Paths

Engineering mode adds repository ingestion, code-symbol aware extraction, dependency graph map seeds, and pull-request
or issue provenance.

General ops mode adds policy, process, vendor, incident, and project document maps with ownership and review metadata.

## Success Criteria

- Users can trace every graph node and edge back to source material and review decisions.
- Reviewers can see graph health, review progress, and provenance coverage without exporting raw graph data.
- Reviewers can inspect the local neighborhood around a high-signal node without loading the full graph.
- Reviewers can see how two reviewed concepts are connected through a bounded path.
- Reviewers can prioritize ready proposals and see why relationship proposals are blocked.
- Reviewers can monitor proposal volume, review decisions, and acceptance/commit rates without exporting raw data.
- Reviewers can see recent review activity with the proposal and source context needed for audit follow-up.
- Reviewers can identify which sources still have pending proposal review work.
- Users can work from a full graph workspace with quick overview, Focus, Evidence, Related, Needs attention, Sources,
  and Planning surfaces.
- Users can experience the graph as a living workspace with meaningful microanimations, graph-linked details, visible
  evidence paths, proposal previews, review transitions, and agent research activity.
- Users can keep 3D graph exploration available while the default graph view stays clean and minimal.
- Users can open Planning Mode as a chat-first agent workspace, persist graph build specs as artifacts, and launch
  scoped research from the conversation.
- Users can ask read-only AI questions over reviewed graph data, sources, source chunks, lineage, neighborhoods, and
  paths with citations.
- Users can extend the graph through AI research while preserving source/chunk provenance and reviewable proposals.
- Users can see agent tool calls inline with status, citations, affected graph items, and review-gated action proposals.
- Users can move from sensed change to graph-linked attention, decision, approved action, outcome, and feedback without
  losing evidence or provenance.
- Owners can route, assign, escalate, resolve, and learn from attention items across sources, graph scopes, connectors,
  actions, and stale knowledge.
- Ingestion is idempotent, replayable, and observable.
- Reviewers can accept, reject, or edit proposals before graph updates.
- The product stays container-neutral and deployable into internal infrastructure.
