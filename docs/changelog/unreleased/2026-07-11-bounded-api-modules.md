---
type: changed
owner: codex
---

- Extract connector, source/ingestion, review, Attention, action/outcome, AI planning, agent-tool, and cited-retrieval
  HTTP routes from application assembly into bounded router modules, together with graph compatibility and
  search/backup/import operations.
- Preserve the committed OpenAPI and generated TypeScript client exactly, including compatibility operation IDs.
- Route the graph module through a typed application service and repository port, with focused domain-service tests
  and an architecture check preventing persistence access from returning to its router.
- Ratchet API assembly to 220 lines and prevent bounded routes from migrating back into the monolith.
