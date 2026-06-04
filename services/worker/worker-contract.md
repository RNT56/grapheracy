# Worker Contract

## Purpose

Define ingestion stages before implementation.

## Stages

| Stage | Input | Output | Idempotency key |
| --- | --- | --- | --- |
| Source fetch | `Source` | Raw artifact in object storage | `source.id + checksum` |
| Source extract | Raw artifact | Normalized text and locations | `source.id + artifact checksum` |
| Content analyze | Normalized text | Candidate concepts and relations | `ingestionRun.id + extract checksum` |
| Proposal generate | Candidates | `ExtractionProposal[]` | `candidate hash + project.id` |
| Review-aware commit | Accepted decisions | `ContentNode` and `SemanticEdge` updates | `reviewDecision.id` |

## Requirements

- Every stage is retryable and idempotent.
- Every stage writes trace metadata to the `IngestionRun`.
- Every generated proposal includes `Provenance`.
- Graph updates require review state.
- Failed stages produce stable error codes and safe diagnostic messages.

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
