# Start Here

Graphview turns mixed knowledge sources into reviewed, provenance-rich graph data for internal research teams and
personal knowledge workflows.

## Current Phase

Phase 4 provides deterministic ingestion scaffolding on top of the runnable web, API, worker, persistence, proposal
review, provenance, search, import, and export workflows. The old prototype is preserved at
`../prototypes/knowledge-graph-explorer.html` as UX evidence only.

## Read Order

1. `../README.md`
2. `../CLAUDE.md`
3. `01-product-goals.md`
4. `02-architecture.md`
5. `03-security.md`
6. `04-development.md`
7. `05-testing.md`
8. `06-operations.md`
9. `07-agent-workflows.md`
10. `08-roadmap.md`
11. `../CHANGELOG.md`

## Subsystem Documentation Standard

Every new subsystem must document:

- Purpose.
- Owner.
- Entrypoints.
- Commands.
- Environment variables.
- Test path.
- Failure modes.

## Acceptance Map

- Setup path: `04-development.md`.
- Agent entry path: `../CLAUDE.md`.
- CI skeleton: `../.github/workflows/`.
- Changelog process: `../CHANGELOG.md` and `changelog/README.md`.
- Security policy: `../SECURITY.md` and `03-security.md`.
- Architecture and contracts: `02-architecture.md`, `../packages/shared-types/src/index.ts`,
  `../services/api/openapi.yaml`, and `../services/worker/worker-contract.md`.
