---
type: changed
owner: codex
---

- Extract connector, source/ingestion, review, Attention, action/outcome, AI planning, agent-tool, and cited-retrieval
  HTTP routes from application assembly into bounded router modules.
- Preserve the committed OpenAPI and generated TypeScript client exactly, including compatibility operation IDs.
- Ratchet API assembly to 450 lines and prevent bounded routes from migrating back into the monolith.
