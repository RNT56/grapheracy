# Start Here

Graphview turns mixed knowledge sources into reviewed, provenance-rich graph data for internal research teams and
personal knowledge workflows.

## Current Phase

Phase 27 adds active agent context connectors for Codex, Claude Code, MCP-compatible agents, VS Code, and Cursor on top
of the Phase 25 digital nervous system loop and Phase 26 release-hardening gate.
The old prototype is preserved at `../prototypes/knowledge-graph-explorer.html` as UX evidence only.

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
11. `09-data-schema.md`
12. `10-user-journeys-and-value-map.md`
13. `11-living-graph-ui-vision-and-upgrade-plan.md`
14. `12-digital-nervous-system-phase25-plan.md`
15. `13-active-agent-context-connectors.md`
16. `../CHANGELOG.md`

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
- User journey and value map: `10-user-journeys-and-value-map.md`.
- Living graph UI vision and upgrade plan: `11-living-graph-ui-vision-and-upgrade-plan.md`.
- Digital nervous system Phase 25 plan: `12-digital-nervous-system-phase25-plan.md`.
- Active agent context connectors: `13-active-agent-context-connectors.md`.
- Architecture and contracts: `02-architecture.md`, `09-data-schema.md`, `../packages/shared-types/src/index.ts`,
  `../services/api/openapi.yaml`, and `../services/worker/worker-contract.md`.
