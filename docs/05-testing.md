# Testing

## Purpose

Define Phase 1 checks and the future test strategy.

## Phase 1 Checks

- `pnpm run lint`
- `pnpm run security:local`
- `pnpm run security:licenses`
- `pnpm run changelog:check`
- `pnpm run typecheck`
- `pnpm run test`

These checks validate documentation hygiene, security policy, changelog process, workspace metadata, and placeholder
package scripts. Phase 1 intentionally does not add production feature tests because no production features are
implemented.

## Phase 2 Checks

- `pnpm run phase2:check`
- `pnpm --filter @graphview/web build`
- API tests through `pnpm --filter @graphview/api-contract test`
- Worker tests through `pnpm --filter @graphview/worker-contract test`

Phase 2 tests cover health/version endpoints, local auth rejection, worker stage ordering, shared TypeScript contract
presence, and the product-first web shell.

## Phase 3 Checks

- `pnpm run phase3:check`
- API workflow tests for source CRUD, proposal review commits, search, import, and export.
- Web shell tests for source and review controls.

## Phase 4 Checks

- `pnpm run phase4:check`
- API tests for text ingestion, backend URL fetch, proposal creation, embedding persistence, and review linkage.
- Worker tests for markdown normalization, deterministic embeddings, proposal generation, stage ordering, and PDF parsing.
- Web shell tests for the ingestion control and API route wiring.

## Future Test Paths

- Web unit and component tests: `apps/web/src`.
- API unit and integration tests: `services/api/tests`.
- Worker unit and integration tests: `services/worker/tests`.
- Shared contracts: `packages/shared-types/src`.
- Graph model tests: `packages/graph-core/src`.
- Design system tests: `packages/design-system/src`.

## Required Coverage Areas From Phase 2 Onward

- Health and version endpoints. Initial coverage exists in Phase 2.
- Auth adapter behavior. Initial local-dev rejection coverage exists in Phase 2.
- Source CRUD and provenance persistence. Initial coverage exists in Phase 3.
- Ingestion idempotency. Initial deterministic ingestion coverage exists in Phase 4.
- Proposal review decisions. Initial coverage exists in Phase 3.
- Graph update transactions. Initial accepted-node commit coverage exists in Phase 3.
- Search behavior. Initial source and node search coverage exists in Phase 3.
- Graph rendering interaction and large-graph performance.

## Failure Modes

- Placeholder tests mistaken for feature coverage.
- Contract changes without API and worker tests.
- Review flow changes without provenance assertions.
- Slow ingestion tests blocking local feedback without integration-test separation.
