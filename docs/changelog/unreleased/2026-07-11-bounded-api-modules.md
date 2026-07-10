---
type: changed
owner: codex
---

- Extract connector, source/ingestion, review, Attention, and action/outcome HTTP routes from application assembly
  into bounded router modules.
- Preserve the committed OpenAPI and generated TypeScript client exactly, including compatibility operation IDs.
- Ratchet API assembly to 900 lines and prevent bounded routes from migrating back into the monolith.
