# Graphview

Graphview turns mixed knowledge sources into a reviewed, provenance-rich graph that people and agents can explore,
question, and act on without silently promoting generated claims into trusted memory.

Graphview 1.0 is an internal, self-hosted product targeting PostgreSQL/pgvector, Redis/Arq, S3-compatible storage,
generic OIDC, Vault-backed secret references, OpenTelemetry, and either Compose or Kubernetes/Helm. The preserved
single-file prototype remains available at `prototypes/knowledge-graph-explorer.html` as UX evidence; production code
does not import it.

## What Ships

- Sigma 3 and Graphology as the primary incremental 2D WebGL graph, with lazy Three.js exploration and an accessible
  non-WebGL list/table equivalent.
- Clustered, server-assisted level of detail for projects containing up to 100,000 nodes and 500,000 edges.
- Upload, URL, repository/GitHub, Google Workspace, and Notion ingestion with durable jobs, cursors, retries,
  tombstones, webhook verification, connector health, and review-gated graph commits.
- Cited graph Q&A, scoped research, planning sessions, provider-neutral AI boundaries, and durable run state.
- A graph-centered Attention loop from signals and observations through reviewed decisions, approved actions,
  outcomes, and feedback.
- Production GitHub Issue, SMTP, and HMAC-signed webhook action adapters whose credentials resolve only inside workers.
- Active agent context capture through the MCP gateway and VS Code/Cursor extension, with ordered offline replay,
  redaction, encrypted retained content, SSE resume, and reviewed derivation.
- `/api/v1`, generated OpenAPI/TypeScript contracts, one-release compatibility aliases, RFC 7807 errors, OIDC
  Authorization Code + PKCE, project authorization, CSRF protection, audit records, and OpenTelemetry.
- Non-root immutable images, SBOM/provenance/signing workflows, destructive inert-restore proof, Compose, and Helm.

## Release Status

The integration branch is a Graphview 1.0 release candidate. The proof-based status, including any external canary
that remains blocked on a protected credential fixture, is maintained in
[`docs/14-graphview-1.0-upgrade-ledger.md`](docs/14-graphview-1.0-upgrade-ledger.md). Historical phase documents describe
how capabilities arrived; they are not release evidence.

## Quick Start

Requirements: Node 24, pnpm 10.27+, Python 3.14, uv, and Docker for production-reference services.

```sh
pnpm install --frozen-lockfile
uv python install 3.14.5
pnpm run quality:fast
```

Run the strongest local gate before publishing changes:

```sh
pnpm run quality:full
pnpm run security:full
pnpm run test:deployment
```

Start the development surfaces:

```sh
pnpm --filter @graphview/web dev
pnpm --filter @graphview/api-contract dev
pnpm --filter @graphview/worker-contract dev
```

SQLite and local AEAD storage are explicitly limited development adapters. Production-like verification uses the
reference stack documented in [`docs/06-operations.md`](docs/06-operations.md).

## Documentation

- [Maintainer and agent guide](CLAUDE.md)
- [Start here](docs/00-start-here.md)
- [Product goals](docs/01-product-goals.md)
- [Architecture](docs/02-architecture.md)
- [Security](docs/03-security.md)
- [Development](docs/04-development.md)
- [Testing](docs/05-testing.md)
- [Operations and release](docs/06-operations.md)
- [Agent workflows](docs/07-agent-workflows.md)
- [Historical roadmap](docs/08-roadmap.md)
- [Data schema](docs/09-data-schema.md)
- [User journeys and value map](docs/10-user-journeys-and-value-map.md)
- [Graphview 1.0 proof ledger](docs/14-graphview-1.0-upgrade-ledger.md)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)

## Repository Layout

- `apps/web`: React product workspace and browser acceptance.
- `apps/docs-app`: documentation route validator.
- `apps/vscode-extension`: VS Code/Cursor active-context adapter.
- `services/api`: FastAPI application, migrations, OpenAPI contract, and domain modules.
- `services/worker`: Arq worker functions and durable job execution.
- `services/agent-gateway`: MCP-compatible local context gateway.
- `packages/api-client`: generated TypeScript API client.
- `packages/shared-types`: public and renderer-neutral contracts.
- `packages/graph-core`: Graphology/Sigma renderer planning and graph semantics.
- `packages/design-system`: accessible design tokens and primitives.
- `infra`: immutable images, Compose, Helm, Keycloak, observability, backup, and restore assets.
- `docs`: product, architecture, operations, testing, and evidence source of truth.
- `prototypes`: preserved reference material excluded from production imports.

Canonical remote: `https://github.com/RNT56/grapheracy.git`
