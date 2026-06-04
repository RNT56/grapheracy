# Worker Contract

## Purpose

Define ingestion stages and the Phase 4 deterministic worker contract.

## Stages

| Stage | Input | Output | Idempotency key |
| --- | --- | --- | --- |
| Source fetch | `Source` | Raw artifact in object storage | `source.id + checksum` |
| Source extract | Raw artifact | Normalized text and locations | `source.id + artifact checksum` |
| Content analyze | Normalized text | Candidate concepts and relations | `ingestionRun.id + extract checksum` |
| Content embed | Normalized text | `ContentEmbedding` | `source.id + embedding model + checksum` |
| Proposal generate | Candidates and embedding metadata | `ExtractionProposal[]` | `candidate hash + project.id` |
| Review-aware commit | Accepted decisions | `ContentNode` and `SemanticEdge` updates | `reviewDecision.id` |

## Requirements

- Every stage is retryable and idempotent.
- Every stage writes trace metadata to the `IngestionRun`.
- Every generated proposal includes `Provenance`.
- Embeddings identify the model and vector shape used to produce them.
- Graph updates require review state.
- Failed stages produce stable error codes and safe diagnostic messages.

## Phase 4 Implementation

- `services/worker/src/graphview_worker/ingestion.py` normalizes text and markdown, extracts PDF text with `pypdf`,
  creates deterministic local hash embeddings, and generates heuristic `content_node` proposals.
- The API owns backend URL fetch in Phase 4 and persists source, run, proposal, provenance, and embedding records in one
  repository transaction.
- External LLM proposal generation remains a provider boundary; Phase 4 uses a deterministic local heuristic so tests do
  not require secrets or network access.

## Events

- `source.created`
- `ingestion.started`
- `proposal.ready`
- `review.committed`
- `graph.updated`

## Failure Modes

- Duplicate proposals from retried analysis.
- Lost source location data during extraction.
- Commit stage accepting stale review decisions.
- Worker logs exposing source secrets or private document content.
