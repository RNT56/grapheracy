# Release Checklist

1. Consolidate `docs/changelog/unreleased/` into `CHANGELOG.md`.
2. Run `pnpm run phase1:check`.
3. Run full CI security gates.
4. Generate SBOMs for app, API, and worker images.
5. Confirm no release-blocking security criteria in `../../SECURITY.md`.
6. Confirm runtime image users are non-root.
7. Tag release after coordinator approval.
