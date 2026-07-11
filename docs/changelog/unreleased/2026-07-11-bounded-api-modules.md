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
- Route source CRUD, lineage, and synchronous/durable ingestion selection through a typed SourcesService and
  repository port; make API test object stores session-owned so repeated verification no longer leaks temp folders.
- Route connector catalog, credential, target, and synchronous/durable sync selection through a typed
  ConnectorService and repository port while preserving the injectable LLM provider factory.
- Route proposal projections, dashboards, provenance coverage, creation, and reviewer-authority transitions through
  a typed ReviewService and repository port.
- Route decisions, action proposals, approval/rejection, action runs, outcomes, and feedback through a typed
  ActionsService and repository port while preserving reviewer and worker authority.
- Ratchet API assembly to 220 lines and prevent bounded routes from migrating back into the monolith.
