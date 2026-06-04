# Contributing

Graphview is currently an internal research and personal-knowledge graph project. Phase 1 work is limited to project
preparation and scaffolding.

## Start

1. Read `CLAUDE.md`.
2. Read `docs/00-start-here.md`.
3. Inspect `git status --short --branch`.
4. Claim a task in `docs/07-agent-workflows.md` or the active handoff note.

## Change Rules

- Keep changes scoped to one worker stream.
- Add or update docs for every subsystem change.
- Add an unreleased changelog fragment for user-visible, operational, security, or architectural changes.
- Do not add dependencies without following `docs/03-security.md`.
- Do not modify `prototypes/knowledge-graph-explorer.html` unless the task explicitly covers prototype work.

## Pull Request Checklist

- Root commands are documented in `docs/04-development.md`.
- Tests or planned-test status are documented in `docs/05-testing.md`.
- Security impact is captured in `SECURITY.md` or `docs/03-security.md`.
- Changelog fragment is added under `docs/changelog/unreleased/`.
