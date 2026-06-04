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

## Future Test Paths

- Web unit and component tests: `apps/web/src`.
- API unit and integration tests: `services/api/tests`.
- Worker unit and integration tests: `services/worker/tests`.
- Shared contracts: `packages/shared-types/src`.
- Graph model tests: `packages/graph-core/src`.
- Design system tests: `packages/design-system/src`.

## Required Coverage Areas From Phase 2 Onward

- Health and version endpoints.
- Auth adapter behavior.
- Source CRUD and provenance persistence.
- Ingestion idempotency.
- Proposal review decisions.
- Graph update transactions.
- Search behavior.
- Graph rendering interaction and large-graph performance.

## Failure Modes

- Placeholder tests mistaken for feature coverage.
- Contract changes without API and worker tests.
- Review flow changes without provenance assertions.
- Slow ingestion tests blocking local feedback without integration-test separation.
