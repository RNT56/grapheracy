# Development

## Purpose

Define the documented setup path, commands, environment variables, and local development expectations.

## Required Tools

- Node 24 Active LTS.
- pnpm 10.27 or newer.
- Python 3.14.
- uv.
- Docker and Docker Compose.

## Setup

```sh
corepack enable
pnpm install --frozen-lockfile
pnpm run phase1:check
```

## Root Commands

| Command | Status | Purpose |
| --- | --- | --- |
| `pnpm run setup` | Runnable | Install with the committed lockfile. |
| `pnpm run lint` | Runnable | Check markdown links, docs freshness, and workspace metadata. |
| `pnpm run docs:check` | Runnable | Run documentation hygiene checks. |
| `pnpm run changelog:check` | Runnable | Validate changelog and unreleased fragments. |
| `pnpm run security:local` | Runnable | Check repository security policy configuration. |
| `pnpm run security:licenses` | Runnable | Check license policy metadata. |
| `pnpm run security:audit` | Runnable after install | Run pnpm audit at moderate severity. |
| `pnpm run security:signatures` | CI gate | Verify npm registry signatures where package metadata supports it. |
| `pnpm run security:osv` | CI gate | Run OSV-Scanner against the source tree and lockfiles. |
| `pnpm run security:secrets` | CI gate | Run gitleaks secret scanning. |
| `pnpm run typecheck` | Runnable placeholder | Runs package type checks as implementations appear. |
| `pnpm run test` | Runnable placeholder | Runs package tests as implementations appear. |
| `pnpm run phase1:check` | Runnable | Runs the local Phase 1 acceptance checks. |

## Environment Variables

Use `.env.example` as the local template. Production values must come from external secret management.

## Package Additions

Do not run casual package installs. Use a dedicated dependency PR, update the lockfile, and complete the checklist in
`03-security.md`.

## Failure Modes

- Local Node or pnpm version below policy.
- Missing lockfile review after dependency changes.
- Root commands added without documentation.
- Feature implementation added before Phase 2 scaffolding.
