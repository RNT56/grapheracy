# Agent Workflows

## Purpose

Coordinate multi-worker preparation without overlapping edits or undocumented handoffs.

## Coordinator

The coordinator owns `docs/08-roadmap.md`, `CHANGELOG.md`, conflict resolution, and final Phase 1 acceptance.

## Worker Streams

| Worker | Scope | Primary files |
| --- | --- | --- |
| A | Repository foundation | Root metadata, workspace files, package/service placeholders, prototype move. |
| B | Documentation system | `README.md`, `CLAUDE.md`, `docs/`, PR template, changelog templates. |
| C | Security and governance | `SECURITY.md`, dependency policy, CI security gates, Renovate, license and SBOM plans. |
| D | Architecture and product goals | Product goals, architecture, domain model, API, worker lifecycle, ADRs. |
| E | CI and operations | Workflows, Compose plan, local setup, test strategy, release process, env matrix. |

## Claiming Work

1. Read `CLAUDE.md`.
2. Check `git status --short --branch`.
3. State the worker stream and files you intend to edit.
4. Avoid files claimed by another worker.
5. Add a closeout note using `rituals/session-close.md`.

## Handoff Rules

- Keep changes small enough for review.
- Include exact commands run.
- Flag incomplete checks or missing external tools.
- Note files that should not be edited concurrently.
- Do not rewrite another worker's docs without coordination.

## Failure Modes

- Two workers editing the same roadmap or changelog sections.
- Feature implementation sneaking into scaffolding tasks.
- Handoff missing tests or security impact.
- Tool-specific guidance diverging from `../CLAUDE.md`.
