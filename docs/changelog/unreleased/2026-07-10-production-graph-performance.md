---
type: changed
owner: codex
---

# Production graph projection performance

- Replace the production subgraph path that materialized an entire project with bounded, indexed source/target
  adjacency traversal supporting depth-two neighborhoods and exact returned-edge omission counts.
- Make PostgreSQL JSONB row serialization accept native decoded values as well as expand-compatible legacy JSON text.
- Split hybrid retrieval into GIN-backed lexical candidates and HNSW-backed vector candidates before reranking.
- Add an OIDC-authenticated live benchmark that idempotently seeds 100,000 nodes and 500,000 edges and enforces a
  250 ms p95 ceiling for clustered overview, progressive detail, focused subgraph, and hybrid search.
