# Start Here

Graphview turns mixed sources and active work context into reviewed, provenance-rich graph memory for internal research
and knowledge operations.

## Current State

Graphview 1.0 is the active release candidate. Stable quality commands, the current bounded architecture, live-stack
evidence, known external-fixture blockers, and release ownership are recorded in `14-graphview-1.0-upgrade-ledger.md`.
Documents named after earlier phases are historical implementation records, not proof that a production workflow is
currently accepted.

The old prototype is preserved at `../prototypes/knowledge-graph-explorer.html` as UX evidence only.

## Read Order

1. `../README.md`
2. `14-graphview-1.0-upgrade-ledger.md`
3. `01-product-goals.md`
4. `02-architecture.md`
5. `03-security.md`
6. `04-development.md`
7. `05-testing.md`
8. `06-operations.md`
9. `09-data-schema.md`
10. `10-user-journeys-and-value-map.md`
11. `07-agent-workflows.md`
12. `08-roadmap.md`
13. `11-living-graph-ui-vision-and-upgrade-plan.md`
14. `12-digital-nervous-system-phase25-plan.md`
15. `13-active-agent-context-connectors.md`
16. `../CHANGELOG.md`

## Subsystem Documentation Standard

Every subsystem documents its purpose, owner, entrypoints, commands, environment, test path, operational signal, and
failure modes. A roadmap claim is not complete until the proof ledger points to executable coverage and production
reference evidence.

## Acceptance Map

- Local setup and stable commands: `04-development.md`.
- Test matrix and acceptance tiers: `05-testing.md`.
- Production deployment, recovery, and release: `06-operations.md`.
- Security and identity: `03-security.md` and `../SECURITY.md`.
- Architecture and contracts: `02-architecture.md`, `09-data-schema.md`,
  `../packages/shared-types/src/index.ts`, `../services/api/openapi.yaml`, and
  `../services/worker/worker-contract.md`.
- Current claim-to-proof mapping: `14-graphview-1.0-upgrade-ledger.md`.
