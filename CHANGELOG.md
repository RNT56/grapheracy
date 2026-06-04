# Changelog

All notable changes to Graphview are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses SemVer once the first
versioned release is cut. Before release consolidation, multi-worker changes land as fragments under
`docs/changelog/unreleased/`.

## [Unreleased]

### Added

- Phase 1 project foundation for a monorepo-based internal knowledge graph product.
- Repo-markdown documentation system with ADRs, rituals, and changelog fragments.
- Security and dependency governance policy before broad dependency adoption.
- Contract skeletons for shared graph types, API endpoints, worker stages, and events.
- CI skeletons for lint, typecheck, tests, audits, secret scanning, docs hygiene, and changelog validation.
- Runnable Phase 2 scaffolds for the React/Vite web app, FastAPI API, async worker stage plan, local auth stub, and
  baseline Alembic migration.
- Phase 3 core graph workflow with persistent source CRUD, proposal review commits, provenance, search, import/export,
  and a web shell wired to those endpoints.

### Changed

- Preserved the standalone prototype as reference material at `prototypes/knowledge-graph-explorer.html`.

### Security

- Added strict dependency approval requirements, lockfile review rules, delayed npm package adoption, and secret handling
  expectations.
