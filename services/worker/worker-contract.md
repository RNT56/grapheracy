# Worker Contract

## Purpose

Define ingestion stages and the deterministic worker contract.

## Stages

| Stage | Input | Output | Idempotency key |
| --- | --- | --- | --- |
| Connector fetch | `ConnectorTarget` | `RawConnectorArtifact[]` | `target.id + remote id + remote modified timestamp` |
| Source extract | Raw artifact | `NormalizedSourceDocument` | `remote id + artifact checksum` |
| Chunk normalize | `NormalizedSourceDocument` | `SourceChunk[]` | `source.id + chunk checksum` |
| Hierarchy build | `SourceChunk[]` | Topics plus `contains` / `part_of` proposals | `target.id + heading path + checksum` |
| Entity resolve | Candidate nodes | Existing node matches or new node proposals | `normalized label + aliases + remote ids` |
| Relation propose | Links, mentions, citations, imports, relations | Source-aware edge proposals | `source.id + relation hash + endpoints` |
| Content embed | Normalized text | `ContentEmbedding` | `source.id + embedding model + checksum` |
| Proposal generate | Deterministic and optional LLM candidates | `ExtractionProposal[]` | `candidate hash + project.id + model` |
| Autocommit evaluate | Ready proposals | System review decisions for eligible proposals | `proposal.id + threshold + endpoints` |
| Review commit | Accepted decisions | `ContentNode` and `SemanticEdge` updates | `reviewDecision.id` |
| Agent plan | Planning messages and graph context | `GraphBuildSpec` draft or assistant message | `project.id + session.id + message.id + provider + model` |
| Agent retrieve | Graph query or research scope | Source, chunk, proposal, lineage, and neighborhood context | `project.id + query hash + lens + scope` |
| Agent reason | Retrieved context and user intent | Cited answer or structured research synthesis | `agentRun.id + provider + model + input checksum` |
| Agent research fetch | Research task and source policy | Imported source records and source chunks | `project.id + task query + provider + model + source identity` |
| Agent propose | Synthesis plus imported sources | Reviewable `ExtractionProposal[]` and action proposals | `project.id + task.id + proposal checksum` |
| Agent action await review | Pending action proposal | Durable review gate state | `agentActionProposal.id` |
| Agent action apply | Approved action proposal | Review decision, connector sync, source import, or graph mutation through existing paths | `agentActionProposal.id + approval actor` |
| Agent context normalize | Captured context events and artifacts | Redacted metadata, artifact records, and blob references | `session.id + event sequence + checksum` |
| Agent context enrich | Context events, repository metadata, diffs, tests, and commits | Inferred file-symbol, import/reference, diff/test/commit relationships | `event.id + enrichment kind + input checksum` |
| Agent context retention | Session policy and encrypted blobs | Deleted expired blob content with retained metadata audit records | `blob.id + retention policy version` |

## Requirements

- Every stage is retryable and idempotent.
- Every stage writes trace metadata to the `IngestionRun`.
- Every generated proposal includes `Provenance`.
- Embeddings identify the model and vector shape used to produce them.
- Graph updates require review state, including system auto-commit decisions.
- Failed stages produce stable error codes and safe diagnostic messages.

## Phase 4 Implementation

- `services/worker/src/graphview_worker/ingestion.py` normalizes text and markdown, extracts PDF text with `pypdf`,
  creates deterministic local hash embeddings, and generates heuristic `content_node` proposals.
- The API owns backend URL fetch in Phase 4 and persists source, run, proposal, provenance, and embedding records in one
  repository transaction.
- External LLM proposal generation remains a provider boundary; Phase 4 uses a deterministic local heuristic so tests do
  not require secrets or network access.

## Phase 6 Mode Extensions

- Repository sources produce deterministic proposals for repository nodes, code symbols, dependencies, and issue or pull
  request references.
- Ops document sources produce deterministic proposals for policy, process, vendor, incident, project, owner, and
  review-cycle metadata.
- Mode-specific metadata stays inside proposal values so review and provenance flows remain unchanged.

## Phase 7 Relationship Proposals

- Ingestion can emit `semantic_edge` proposals after candidate content-node proposals.
- Relationship proposals use candidate labels at extraction time and are resolved to node IDs by the API persistence
  boundary.
- Edge commits require reviewed endpoint nodes.

## Phase 17 Connector Ingestion

- Connector targets fetch upload, URL, repository, Google Workspace, and Notion content into normalized source documents.
- Source chunks preserve heading paths, block type, ordinal, links, mentions, checksums, and locators for provenance.
- Hierarchy extraction creates topics, document nodes, and source-aware `contains`, `part_of`, `references`, `imports`,
  and `implements` relationships.
- Deterministic extraction always runs first. Optional LLM extraction uses a provider boundary and writes the same
  reviewable proposal shape when enabled by graph or connector settings.
- Auto-commit uses the configured confidence threshold and records `system-autocommit` review decisions; edge proposals
  wait until both endpoints exist.

## Phases 18-22 AI Agent Runtime

- Planning Mode writes `planning_sessions`, `planning_messages`, and versioned `graph_build_specs`; approving or editing
  a build spec does not mutate the graph by itself.
- Every `agent_run` records kind, provider, resolved model, trace ID, status, input, output, timestamps, citations, and
  pending action proposals.
- Graph Q&A runs only the retrieve and reason stages and must not write sources, proposals, nodes, or edges.
- Scoped research creates a `research_task`, imports sources and chunks through existing ingestion boundaries, then
  creates reviewable proposals. Duplicate work is suppressed by project, task, query, provider, model, source identity,
  checksum, and build spec version.
- Agent-created graph changes become `agent_action_proposals` unless graph settings explicitly allow auto-commit through
  the existing review/autocommit contract.
- Provider clients are isolated from repository writes. Worker or API orchestration owns persistence and review gates.

## Phase 27 Active Agent Context

- Active context capture starts with scoped `gvctx_...` adapter clients and sessions. The worker treats captured context
  as observation, not reviewed graph memory.
- Gateway and MCP tool events are authoritative for exact file reads, searches, shell commands, prompts, model calls,
  edits, diffs, tests, and session boundaries.
- VS Code and Cursor observations are reconciliation hints unless they are linked to a gateway/tool event.
- Enrichment may infer file-to-symbol, import/reference, diff/test, and commit relationships, but inferred edges never
  override observed event relationships or bypass proposal/review gates.
- Redaction, encryption, retention, and access checks happen before downstream enrichment reads captured content.

## Events

- `source.created`
- `ingestion.started`
- `proposal.ready`
- `review.committed`
- `graph.updated`
- `agent.run.started`
- `agent.step.completed`
- `agent.action.pending_review`
- `research.task.completed`
- `agent_context.session_started`
- `agent_context.file_read`
- `agent_context.prompt_built`
- `agent_context.model_request`
- `agent_context.model_response`
- `agent_context.edit_applied`
- `agent_context.test_run`
- `agent_context.session_ended`

## Failure Modes

- Duplicate proposals from retried analysis.
- Lost source location data during extraction.
- Commit stage accepting stale review decisions.
- Edge proposals committed before endpoint nodes exist.
- Worker logs exposing source secrets or private document content.
- Provider fallback changing the recorded model without user or graph settings.
- AI action application bypassing proposals or review decisions.
- Captured agent context being treated as reviewed graph truth.
- Adapter outbox replay duplicating events without sequence idempotency.
- Editor-only passive observations being mistaken for exact model prompt context.
