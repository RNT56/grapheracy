# Security Policy

Graphview is pre-release internal software. Report vulnerabilities privately to the repository owner until a formal
security mailbox is created.

## Supported Versions

No production version is supported yet. Security fixes apply to the default branch until the first release branch exists.

## Triage SLA

- Critical exposure or active exploitation: acknowledge within 1 business day, mitigate or disable affected path within
  2 business days.
- High severity dependency or auth/data issue: acknowledge within 2 business days, remediation plan within 5 business
  days.
- Moderate severity issue: acknowledge within 5 business days, schedule in the next maintenance batch.
- Low severity hardening issue: track in roadmap or backlog with rationale.

## Release-Blocking Criteria

A release is blocked when any of these are true:

- Known critical or high vulnerability without an accepted mitigation.
- Undocumented dependency addition or unexplained lockfile churn.
- Secrets in git history, image layers, logs, fixtures, or docs.
- Container image runs as root without a documented exception.
- Auth, provenance, or review-decision behavior changes without tests.
- SBOM generation fails for a release image.

## Dependency Approval

Follow `docs/03-security.md` before adding or updating dependencies. Required evidence includes lockfile review, audit
results, OSV scan, maintenance health, install-script review, license check, and direct need.

## Incident Notes

Use `docs/rituals/incident-notes-template.md` for incident records. Do not include secrets, tokens, personal contact
details, or private customer data in incident notes.
