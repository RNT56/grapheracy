# Changelog Fragments

Unreleased fragments live in `unreleased/` and are consolidated into the root `CHANGELOG.md` during release.

## Fragment Format

Use one markdown file per meaningful change:

```md
---
type: added
owner: worker-a
---

Short user-facing or maintainer-facing summary.
```

Allowed types: `added`, `changed`, `deprecated`, `removed`, `fixed`, `security`.

## Rules

- Add a fragment for architectural, operational, security, dependency, or user-visible changes.
- Do not add fragments for typo-only changes unless they affect published docs.
- Consolidate fragments into `CHANGELOG.md` before tagging a release.
