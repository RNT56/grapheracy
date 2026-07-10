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

## Phase 2 Dependency Approval Notes

Direct JavaScript dependencies are pinned in `pnpm-workspace.yaml` and locked in `pnpm-lock.yaml`. They are required for
the runnable React/Vite shell and TypeScript contract checks, including React type packages used only at compile time.

Direct Python dependencies are locked through `uv.lock`. FastAPI, Pydantic Settings, SQLAlchemy, Alembic, Uvicorn, HTTPX,
and PyPDF are required for the API scaffold and ingestion path. Arq, Pydantic Settings, and PyPDF are required for the
worker scaffold. Pytest remains a dev dependency for service tests.

Lifecycle scripts remain denied by default. Any package that requires a build or postinstall exception must be documented
before it is allowed.

## Phase 4 Dependency Approval Notes

- HTTPX moved to an API runtime dependency because backend URL fetch is a Phase 4 ingestion feature. It was already
  present in the lockfile for tests, has no npm lifecycle-script exposure, and is covered by API ingestion tests.
- PyPDF was added to the API and worker runtime dependency sets for PDF text extraction. The direct need is bounded to
  local PDF parsing; no native build or postinstall script is required; `uv.lock` records the exact resolved version.
- External LLM and embedding providers are intentionally not added in Phase 4. The implemented provider boundary uses
  deterministic local heuristics and hash embeddings until secrets, vendor risk, data retention, and cost controls are
  reviewed.

## Phase 5 Access Control Notes

- Local seeded users are `reader`, `researcher`, and `maintainer`.
- Reader access can read graph data and readiness state.
- Researcher access can create sources, ingestion runs, proposals, and review decisions.
- Maintainer access adds destructive and operator actions: source deletion, import/export, backup/restore, and metrics.
- Phase 5 does not add production OIDC. The local role boundary is a testable adapter shape for the internal SSO work.

## Phase 24 Dependency Approval Notes

Phase 24 introduced the browser and graphics dependencies now retained by Graphview 1.0. The current dependency
approval record is:

- `three`: lazy runtime for the isolated 3D renderer boundary, including hit-testing, orbit, tooltip projection, and
  context recovery. It is not loaded by default 2D sessions and does not own graph domain state.
- `sigma` and `graphology`: the primary 2D WebGL renderer and canonical in-browser graph model. Incremental lifecycle,
  reducers, camera state, and WebGL picking remain isolated behind the shared renderer scene contract.
- `@types/three`: development-only TypeScript types for `three`. It has no runtime footprint and should stay scoped to
  the web package.
- `@playwright/test`: development-only browser automation for nonblank 2D/3D graph rendering, tooltip/tether behavior,
  URL handling, reduced-motion checks, and mobile smoke coverage. It downloads browser binaries through Playwright's
  normal installer outside package lifecycle scripts; CI should cache browsers and document any install step separately.
- `pngjs`: development-only PNG inspection for screenshot pixel checks. It keeps nonblank render assertions local and
  deterministic without adding native image-processing dependencies.

Approval is conditional on the coordinator reviewing `pnpm-workspace.yaml` and `pnpm-lock.yaml`, confirming no package
lifecycle allowlist expansion, and recording moderate `pnpm audit`, OSV, signature, and license results before Phase 24
is released.

## Phase 27 Dependency Approval Notes

Phase 27 adds active agent context capture and approved connector dependencies:

- `cryptography`: API runtime dependency for app-level encryption of redacted active-context text blobs before storage.
  Alternatives considered were a local HMAC stream envelope and metadata-only storage; `cryptography` provides a
  reviewed primitive with clear maintenance and no JavaScript lifecycle exposure. `uv.lock` records `cryptography`
  plus `cffi` and `pycparser`.
- `@modelcontextprotocol/sdk`: gateway runtime dependency for MCP server registration and stdio transport. It is the
  official TypeScript SDK, MIT licensed, Node 18+ compatible, and locked in `pnpm-lock.yaml`. The lockfile adds the SDK
  transitive HTTP, schema, and protocol packages used by its server/client implementation.
- `@types/vscode`: extension development dependency for VS Code-compatible adapter typing. It has no runtime footprint
  and is scoped to `apps/vscode-extension`.

Lifecycle scripts remain denied by `.npmrc`. No package-specific lifecycle allowlist is added. Release requires the
normal security, license, changelog, typecheck, test, browser, and release-readiness gates through `pnpm run
phase27:check`; external audit, OSV, signature, and secret scans remain CI/release gates.

## Required Gates

- JS audit: `pnpm audit --audit-level=moderate`.
- npm package signatures where applicable: `npm audit signatures`.
- OSV lockfile scan: `osv-scanner scan source -r .`.
- Python dependency audit after service dependencies are added.
- Secret scan: `pnpm run security:secrets`; it uses an installed `gitleaks` binary or the official Go module fallback.
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

## AI Provider Secrets And Review Gates

- Configure AI credentials through environment-backed settings such as `GRAPHVIEW_OPENAI_API_KEY`,
  `GRAPHVIEW_ANTHROPIC_API_KEY`, and `GRAPHVIEW_GEMINI_API_KEY`, or through operator-only provider credential routes
  that persist project-scoped encrypted API keys.
- Provider catalog and settings responses must expose only configured/enabled state, model IDs, capabilities, and
  non-secret defaults; never raw API keys, encrypted API keys, connector tokens, encrypted token JSON, or prompt payloads
  containing private content.
- Agent runs store provider, model, trace ID, summaries, citations, confidence, and status for audit. Avoid logging full
  prompts when they may include private source text or user secrets.
- Graph query should prefer stored Graphview graph, source chunk, lineage, neighborhood, and path context over external
  tools for private connector content unless an operator explicitly configures provider use.
- AI research may create sources, source chunks, ingestion runs, embeddings, proposals, research tasks, and action
  proposals. Reviewed nodes and edges must still flow through the existing review decision path.

## Active Agent Context Capture

- Adapter clients use one-time `gvctx_...` bearer tokens created by maintainers. Token hashes are stored; raw tokens are
  returned only at creation and are not restored from backups.
- Context ingest routes accept only capture-scoped adapter tokens. Requested adapter scopes are normalized to
  `context:capture`; UI reads continue to use Graphview reader/operator permissions, and full artifact content reads
  require maintainer access.
- Capture authority must be preserved in every event: `gateway` is authoritative, `adapter_reported` is trusted adapter
  telemetry, and `passive_reconciled` is best-effort editor observation.
- Text blobs are redacted before encrypted-at-rest storage. The default deny policy rejects `.env`, private-key, and
  certificate path fragments before capture.
- Normal export/backup includes context metadata only. Restoring a bundle must not recreate usable adapter tokens or
  rehydrate raw captured content by default.
- Retention cleanup must purge expired encrypted blobs without deleting session/event audit metadata.

Production disaster restore is stricter than logical project import. It runs only with Graphview API, worker, and
Keycloak database clients stopped; refuses remaining client connections; never restores Vault; removes connector and AI
provider credential references; revokes adapter token hashes; clears connector leases and Redis sessions; and converts
all unfinished job, outbox, ingestion, connector, AI, and external-action state to explicit inert terminal records.
Completed external receipts remain audit evidence and are never enqueued again.

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
- Operator-only backup, restore, export, or metrics routes becoming readable by non-maintainer users.
- AI provider, run, or catalog routes returning secrets or allowing reviewed graph writes without proposal review.
- Active context adapters capturing denied files, unredacted shell output, raw provider keys, or passive editor state that
  is displayed as exact prompt context. Server ingest rejects default denied paths and absolute paths outside configured
  workspace roots before writing artifact records.
