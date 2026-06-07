# Agent Workflows

## Purpose

Coordinate multi-worker preparation without overlapping edits or undocumented handoffs.

## Coordinator

The coordinator owns `docs/08-roadmap.md`, `CHANGELOG.md`, conflict resolution, and phase acceptance.

## Worker Streams

| Worker | Scope | Primary files |
| --- | --- | --- |
| A | Repository foundation | Root metadata, workspace files, package/service placeholders, prototype move. |
| B | Documentation system | `README.md`, `CLAUDE.md`, `docs/`, PR template, changelog templates. |
| C | Security and governance | `SECURITY.md`, dependency policy, CI security gates, Renovate, license and SBOM plans. |
| D | Architecture and product goals | Product goals, architecture, domain model, API, worker lifecycle, ADRs. |
| E | CI and operations | Workflows, Compose plan, local setup, test strategy, release process, env matrix. |

## AI V1 Multiworker Streams

| Worker | Scope | Primary files |
| --- | --- | --- |
| Coordinator | Gates, OpenAPI merge, migrations, roadmap, changelog, final acceptance. | `CHANGELOG.md`, `docs/08-roadmap.md`, `services/api/openapi.yaml`, migration order. |
| A | AI contracts, schema, migrations, export/restore. | `packages/shared-types/src/index.ts`, `services/api/src/graphview_api/db.py`, `services/api/src/graphview_api/schemas.py`, `services/api/migrations/versions/`. |
| B | Agent runtime API, repository persistence, authorization, graph retrieval. | `services/api/src/graphview_api/main.py`, `services/api/src/graphview_api/repository.py`, API tests. |
| C | Provider registry and OpenAI, Anthropic, Gemini adapters with mocked tests. | `services/api/src/graphview_api/llm.py`, `services/api/src/graphview_api/settings.py`, provider tests. |
| D | Research orchestration and worker stage contract. | `services/worker/src/graphview_worker/`, `services/worker/worker-contract.md`, worker tests. |
| E | Planning Mode and embedded graph AI UI. | `apps/web/src/App.tsx`, `apps/web/src/styles.css`, `apps/web/tests/`. |
| F | Docs, security, QA, release checks. | `docs/`, `README.md`, `.env.example`, `package.json`, release/changelog checks. |

## AI V1 Gates

1. Baseline freeze: preserve dirty Phase 17/17.5 work, run `git status --short --branch`, and assign owners.
2. Contract freeze: shared TypeScript, API schemas, migration names, statuses, and provider descriptors land before UI
   and provider work depends on them.
3. Runtime integration: UI uses frozen API shapes; backend changes after this point require coordinator review.
4. Trust and review: every agent-created graph mutation is a reviewable proposal unless explicit graph settings permit
   existing auto-commit behavior.
5. Release acceptance: full checks, docs, changelog fragments, provider security notes, and handoff details are complete.

## Digital Nervous System UI and Agent Tooling Streams

| Worker | Scope | Primary files |
| --- | --- | --- |
| Coordinator | Contract freeze, QA gates, docs, changelog, merge order. | `packages/shared-types/`, `services/api/src/graphview_api/schemas.py`, docs, tests. |
| A | Graph workspace UI, grouped graph controls, 2D/3D option, mobile navigation. | `apps/web/src/App.tsx`, `apps/web/src/GraphCanvas.tsx`, `apps/web/src/styles.css`. |
| B | Evidence reader, source outline, passage actions, citation surfaces. | Web app source reader, source chunk API tests. |
| C | Typed review queue and Needs attention work items. | Review queue repository/API, web review worklist, review tests. |
| D | Chat-centric Planning Mode with inline agent activity and artifact preview. | Planning UI, planning APIs, planning tests. |
| E | Agent tool catalog and tool-call execution. | API schemas, repository mappings, `/agent-tools`, `/agent-tool-calls`, shared contracts. |
| F | QA, accessibility, docs, and release notes. | Web tests, API tests, docs, changelog fragments. |

Gates:

1. Shared types and API schemas land before UI or worker code depends on new tool-call fields.
2. Mutating tools remain review-gated through proposals or action approvals.
3. Planning Mode stays chat-first; graph build specs and evidence bundles are side artifacts.
4. The UI uses direct operational labels: Focus, Evidence, Related, Needs attention, Sources, Planning.
5. 3D remains available as an explicit graph dimension option, but 2D overview remains default.

## Phase 24 Living Graph Streams

| Worker | Scope | Primary files |
| --- | --- | --- |
| Coordinator | Package/catalog wiring, final checks, merge order, roadmap/changelog consolidation. | Root package files, lockfile, release checks, `CHANGELOG.md`. |
| A | Living graph interaction model, visual state resolver, hover/focus/related/dimmed states. | `apps/web/src/App.tsx`, `apps/web/src/GraphCanvas.tsx`, web styles. |
| B | Tooltip and tether overlay, source URL actions, keyboard focus parity, reduced-motion behavior. | Web graph overlay components and styles. |
| C | Agent activity and graph-linked evidence visualization from existing agent, citation, source, and proposal records. | Web graph activity state, source/evidence UI, API read contracts where needed. |
| D | Candidate proposal and review transition visuals while preserving review-gated mutations. | Review UI, graph candidate layers, review tests. |
| E | 3D renderer evaluation, optional Three.js boundary, 2D/3D parity, performance fallbacks. | Graph renderer boundary, browser QA support. |
| F | QA, security notes, testing docs, operations docs, changelog fragment, and Playwright scaffold. | `apps/web/tests/`, `docs/`, `apps/web/playwright.config.ts`. |

Gates:

1. The graph remains the central workspace surface; Phase 24 must not turn it into a dashboard preview.
2. `GraphVisualState`, `GraphTooltipModel`, and `GraphActivityEvent` contracts are shared before UI workers depend on
   new activity shapes.
3. Tooltip, tether, and source URL behavior work through hover and keyboard focus, and source URLs open externally with
   target/rel safeguards.
4. Agent scans, citations, incoming sources, candidate proposals, and review outcomes stay visually distinct from
   reviewed graph memory.
5. Browser QA includes nonblank 2D and 3D render checks, mobile coverage, reduced-motion behavior, and tooltip URL
   behavior before Phase 24 completion.

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
- UI or provider workers inventing API shapes after contract freeze.
- AI research writing graph nodes or edges outside existing source/proposal/review flows.
