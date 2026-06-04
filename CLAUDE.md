# CLAUDE.md

This is the canonical maintainer and agent entrypoint for Graphview. Future tool-specific files, including any
`AGENTS.md`, must point back here instead of redefining project rules.

## Session Start Ritual

1. Read `README.md`.
2. Read `docs/00-start-here.md`.
3. Read `docs/08-roadmap.md`.
4. Read `CHANGELOG.md`.
5. Inspect `git status --short --branch`.
6. Claim a task in the active handoff notes before editing shared files.

## Session Close Ritual

Every worker closes with:

- Changed files summary.
- Tests and checks run, with exact commands.
- Docs updated or a reason docs were not required.
- Changelog fragment added or a reason it was not required.
- Risks, follow-up work, and rollback notes.
- Next worker handoff, including files that should not be edited concurrently.

Use `docs/rituals/session-close.md` for the handoff format.

## Code Hygiene

- Keep typed boundaries between apps, services, workers, and packages.
- Do not introduce hidden globals or ambient runtime coupling.
- Do not add direct dependencies without the dependency approval workflow in `docs/03-security.md`.
- Do not accept generated churn in lockfiles, docs, snapshots, or formatted files.
- Do not mix feature implementation into scaffolding changes.
- Do not ship feature work without tests and docs for the changed behavior.
- Prefer boring, maintained packages with small transitive trees and clear provenance.

## Security Rules

Before adding or updating a dependency, review and document:

- Lockfile diff.
- `pnpm audit --audit-level=moderate` or the applicable ecosystem audit.
- OSV result for lockfiles.
- Maintenance health, release cadence, issue posture, and maintainer changes.
- Install scripts and native build steps.
- License compatibility.
- Direct product need and alternatives considered.

Lifecycle scripts are denied by default through `.npmrc`. Any required build script must be allowlisted and explained in
`docs/03-security.md`.

## Documentation Entrypoints

- Product goals: `docs/01-product-goals.md`
- Architecture: `docs/02-architecture.md`
- Security: `docs/03-security.md`
- Development: `docs/04-development.md`
- Testing: `docs/05-testing.md`
- Operations: `docs/06-operations.md`
- Agent workflows: `docs/07-agent-workflows.md`
- Roadmap: `docs/08-roadmap.md`

Every subsystem doc must include purpose, owner, entrypoints, commands, environment variables, test path, and failure
modes.

## Multi-Worker Rules

- Claim a task before editing.
- Avoid overlapping files unless the coordinator explicitly assigns a merge.
- Keep changes small and handoff-ready.
- Update handoff notes before ending a session.
- Never rewrite another worker's docs without coordination.
- Preserve the prototype in `prototypes/knowledge-graph-explorer.html` unchanged unless a task explicitly says to create a
  new prototype variant.

## Maintainer Commands

- `pnpm install --frozen-lockfile`: install workspace metadata with the committed lockfile.
- `pnpm run lint`: run local docs and workspace metadata checks.
- `pnpm run typecheck`: run package type checks when packages add typed implementations.
- `pnpm run test`: run package tests when packages add test suites.
- `pnpm run security:local`: run local security policy checks.
- `pnpm run changelog:check`: validate changelog and unreleased fragment rules.
