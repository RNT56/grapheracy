# Security And Dependency Governance

## Purpose

Install strict controls before broad package adoption.

## Owners

Security worker owns policy. Coordinator owns release-blocking enforcement.

## Dependency Rules

- Use pnpm workspace catalogs for JavaScript dependency versions.
- Keep `minimumReleaseAge: 1440` and strict mode enabled in `pnpm-workspace.yaml`.
- Commit and review `pnpm-lock.yaml` in every dependency PR.
- Deny lifecycle scripts by default through `.npmrc`.
- Allow lifecycle scripts only with a documented package-specific reason.
- Prefer boring, well-maintained packages with small transitive trees.
- Avoid packages with recent maintainer compromise, unmaintained status, heavy transitive trees, install scripts, or
  unclear provenance.
- Add an ADR when a direct dependency becomes architectural.

## Dependency Approval Checklist

For every new direct dependency, document:

- Direct product need.
- Alternatives considered.
- Maintenance health and release cadence.
- Recent security advisories or maintainer compromise signals.
- Transitive dependency size and risk.
- Install scripts, native builds, or postinstall behavior.
- License compatibility with internal use.
- Lockfile diff summary.
- `pnpm audit --audit-level=moderate` or ecosystem equivalent.
- OSV scan result against lockfiles.

## Required Gates

- JS audit: `pnpm audit --audit-level=moderate`.
- npm package signatures where applicable: `npm audit signatures`.
- OSV lockfile scan: `osv-scanner scan source -r .`.
- Python dependency audit after service dependencies are added.
- Secret scan: `gitleaks detect`.
- License check.
- Typecheck, lint, and tests.
- Docs hygiene and changelog validation.

Local Phase 1 policy checks run through `pnpm run security:local` and `pnpm run security:licenses`. Full external
scanner gates are wired in CI and require the tools installed there.

## Secrets

- Commit `.env.example` only.
- Ignore `.env` and environment-specific variants.
- Production secrets must live in external secret stores.
- Never bake secrets into images, fixtures, logs, docs, or incident notes.

## Containers

- Run as non-root users.
- Use minimal base images.
- Pin major runtime image lines.
- Do not bake secrets into image layers.
- Generate SBOMs for app, API, and worker images before release.

## Failure Modes

- Fresh package compromise before security scanners catch up.
- Lockfile regeneration hiding risky transitive changes.
- Local-only secrets copied into docs or image layers.
- CI security tools missing or silently skipped.
- Allowlisted lifecycle scripts expanding without review.
