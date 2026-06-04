# Graphview

Graphview is an internal knowledge graph product for ingesting mixed sources, extracting and reviewing concepts,
preserving provenance, and exploring relationships in an interactive graph.

The repository is in Phase 1: production project preparation. The standalone prototype is preserved as UX evidence at
`prototypes/knowledge-graph-explorer.html`; it is not production code.

## Start Here

- Maintainer and agent entrypoint: `CLAUDE.md`
- Human documentation entrypoint: `docs/00-start-here.md`
- Product goals: `docs/01-product-goals.md`
- Architecture: `docs/02-architecture.md`
- Security: `docs/03-security.md`
- Development: `docs/04-development.md`
- Testing: `docs/05-testing.md`
- Operations: `docs/06-operations.md`
- Agent workflows: `docs/07-agent-workflows.md`
- Roadmap: `docs/08-roadmap.md`
- Changelog: `CHANGELOG.md`
- Security policy: `SECURITY.md`

## Local Setup

Required for Phase 1 checks:

- Node 24 Active LTS target; local validation scripts use standard Node APIs.
- pnpm 10.27 or newer.
- Python 3.14 target for future services.
- uv for Python workspace management.
- Docker for local service orchestration once Phase 2 adds runnable services.

```sh
corepack enable
pnpm install --frozen-lockfile
pnpm run lint
pnpm run security:local
pnpm run changelog:check
```

`pnpm run typecheck` and `pnpm run test` are wired for workspace packages and currently pass through because Phase 1
defines contracts and scaffolding rather than production implementations.

## Repository Layout

- `apps/web`: future React/Vite product UI.
- `apps/docs-app`: future docs app consuming repo markdown.
- `services/api`: future FastAPI service and OpenAPI contract.
- `services/worker`: future ingestion worker contract.
- `packages/shared-types`: shared public TypeScript contracts.
- `packages/graph-core`: graph model and rendering abstraction boundary.
- `packages/design-system`: design tokens and shared UI primitives boundary.
- `docs`: source of truth for product, architecture, security, operations, and roadmap.
- `infra`: Docker, Compose, and operational scripts.
- `prototypes`: preserved reference prototypes.

## Remote

Canonical remote: `https://github.com/RNT56/grapheracy.git`
