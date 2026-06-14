# Active Agent Context Connectors

## Purpose

Phase 27 lets Graphview show live and historical LLM or agent working context across Codex, Claude Code, MCP-compatible
agents, VS Code, and Cursor. The system captures files opened or read, searches, shell commands, prompts, model-call
reports, edits, diffs, tests, commits, and session lifecycle events as authority-labeled observations connected to the
existing source, provenance, activity, and graph projection surfaces.

Captured context is not reviewed graph memory. It can explain what an agent saw or did, but it cannot create accepted
nodes or edges unless it later flows through the existing proposal and review gates.

## Components

- API: `/agent-context/*` manages adapter clients, sessions, event ingest, graph projection, content reads, SSE replay,
  retention, backup metadata, and activity integration.
- Gateway: `services/agent-gateway` provides MCP SDK-backed tool registration, Codex and Claude wrapper commands, file
  range reads, search capture, shell capture, prompt/model-call reports, edit/diff reports, and offline outbox retry.
- Extension: `apps/vscode-extension` reports active editors, visible ranges, selections, saves, workspace/git metadata,
  and adapter heartbeats for VS Code and Cursor.
- Worker: `services/worker` owns retryable normalization, enrichment, and retention stages for active context events.
- Web: the Active Context lens shows session selection, live timeline, authority badges, prompt/read/edit badges,
  redaction states, content inspection, graph projection, and streaming updates.

## Capture Authority

- `gateway`: Graphview-instrumented tool or proxy call. This is the authoritative source for exact agent context.
- `adapter_reported`: trusted adapter telemetry sent by a first-party runtime or wrapper.
- `passive_reconciled`: best-effort editor or file-watcher observation used only as a reconciliation hint.

Provider-hidden reasoning is not captured unless a runtime explicitly emits it. Binary and oversized files store
metadata, hashes, and locators only.

## Token Setup

Maintainers create one-time capture tokens:

```sh
curl -X POST "$GRAPHVIEW_API_BASE_URL/agent-context/clients" \
  -H "Authorization: Bearer $GRAPHVIEW_UI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"display_name":"local-codex","runtime_kind":"codex","settings":{"workspace_roots":["/path/to/repo"]}}'
```

The response includes a `gvctx_...` token once. Store it in a local secret store or a shell profile that is not checked
into the workspace:

```sh
export GRAPHVIEW_API_BASE_URL=http://localhost:8000
export GRAPHVIEW_AGENT_CONTEXT_TOKEN=gvctx_replace_me
```

Adapter tokens have capture-only scope. UI reads still use normal Graphview permissions.

## Gateway Startup

Run the gateway manifest or helpers from the workspace:

```sh
pnpm --filter @graphview/agent-gateway test
pnpm --filter @graphview/agent-gateway exec graphview-agent-gateway manifest
pnpm --filter @graphview/agent-gateway exec graphview-agent-gateway mcp-server
```

Required environment:

- `GRAPHVIEW_API_BASE_URL`: Graphview API base URL.
- `GRAPHVIEW_AGENT_CONTEXT_TOKEN`: one-time-created capture-only adapter token.
- `GRAPHVIEW_AGENT_CONTEXT_OUTBOX`: optional offline queue file. Defaults to `.graphview/agent-context-outbox.jsonl`.

The gateway redacts secrets before sending events, denies sensitive paths by default, computes checksums for payloads,
and replays queued retryable requests when Graphview is reachable. Network failures, 408, 409, 425, 429, and 5xx
responses are queued; permanent 4xx responses fail fast.

## MCP Configuration

Use the gateway package as the MCP server command in agents that support local MCP servers:

```json
{
  "mcpServers": {
    "graphview-context": {
      "command": "pnpm",
      "args": ["--filter", "@graphview/agent-gateway", "exec", "graphview-agent-gateway", "mcp-server"],
      "env": {
        "GRAPHVIEW_API_BASE_URL": "http://localhost:8000",
        "GRAPHVIEW_AGENT_CONTEXT_TOKEN": "gvctx_replace_me"
      }
    }
  }
}
```

The manifest exposes `start_session`, `read_file`, `search`, `run_shell`, `report_prompt`, `report_model_call`,
`report_edit`, `get_diff`, and `end_session`. The `end_session` tool updates `/agent-context/sessions/{session_id}`
with `PATCH`.

## Codex And Claude Code Wrappers

Use the wrapper binaries when running a local agent session that should be captured:

```sh
pnpm --filter @graphview/agent-gateway exec graphview-codex start-session
pnpm --filter @graphview/agent-gateway exec graphview-claude start-session
```

Wrappers set the session and token environment expected by the gateway helpers. File reads, searches, shell commands,
prompts, model-call reports, edits, diffs, and end-session reports should go through the gateway when exact prompt
context matters.

## VS Code And Cursor

The first-party extension is VS Code-compatible and can run in Cursor with the same settings:

- `graphview.apiBaseUrl`: Graphview API base URL.
- `graphview.agentContextToken`: scoped `gvctx_...` adapter token.

The extension reports editor open/selection/save and heartbeat observations as `passive_reconciled` unless paired with
gateway events. Failed event posts are spooled in VS Code `globalState` and replayed by the heartbeat command and on
activation. These observations help explain what was visible in the editor but do not prove model prompt inclusion.

## Privacy Controls

- Redaction happens before encryption and storage.
- Encrypted content blobs are retained by policy and omitted from backup exports by default. Use
  `GET /backup?include_agent_context_content=true` only for explicit encrypted-content backup export.
- Content reads require maintainer permission through `GET /agent-context/artifacts/{artifact_id}/content`.
- Raw adapter tokens, provider keys, `.env` secrets, private keys, and unredacted command environments are never returned.
- Workspace path allowlists, denied path defaults, max blob size, max batch size, sequence idempotency, event checksums,
  and retention defaults are enforced at ingest. Relative paths are accepted as workspace-local; absolute paths must sit
  under the session `workspace_root` or client `settings.workspace_roots`.

## Troubleshooting

- `401 Unauthorized`: verify the token starts with `gvctx_`, belongs to an active context client, and has
  `context:capture` scope. Permanent 4xx responses are not added to the retry outbox.
- `403 Forbidden`: confirm the path is under the configured workspace root and does not match denied secret patterns.
- Missing gateway events: run the gateway outbox flush command after Graphview is reachable again.
- Missing editor events: run `Graphview: Send Agent Context Heartbeat` to flush the VS Code/Cursor outbox.
- Duplicate-looking events: check `client_event_id` and sequence fields; ingest is idempotent per session and sequence.
- Content unavailable: the artifact may be binary, oversized, purged by retention, or visible only to maintainers.

## Acceptance

Run the focused package checks while developing:

```sh
pnpm --filter @graphview/agent-gateway test
pnpm --filter @graphview/vscode-extension test
PYTHONPATH=src uv run --group dev pytest tests/test_api.py -q
```

Run the release gate before handoff:

```sh
pnpm run phase27:smoke
pnpm run phase27:check
```
