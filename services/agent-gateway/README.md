# Graphview Agent Gateway

## Purpose

Captures authoritative agent context for Graphview through Graphview-aware tools and CLI wrappers. The gateway is
backed by the approved MCP TypeScript SDK for Phase 27 and exposes stdio MCP tools plus local commands for Codex,
Claude Code, and other agent runtimes that can call shell tools.

## Environment

- `GRAPHVIEW_API_BASE_URL`: Graphview API URL, default `http://127.0.0.1:8000`.
- `GRAPHVIEW_AGENT_CONTEXT_TOKEN`: one-time capture-only `gvctx_...` adapter token from
  `POST /agent-context/clients`.
- `GRAPHVIEW_AGENT_CONTEXT_SESSION_ID`: active session ID for event capture commands.
- `GRAPHVIEW_AGENT_CONTEXT_OUTBOX`: JSONL retry outbox, default `.graphview/agent-context-outbox.jsonl`.

## Commands

```sh
graphview-agent-gateway manifest
graphview-agent-gateway mcp-server
graphview-agent-gateway start-session '{"title":"Codex run","runtime_kind":"codex"}'
graphview-agent-gateway read-file '{"session_id":"ctxsession_...","path":"services/api/src/graphview_api/main.py","startLine":1,"endLine":80}'
graphview-agent-gateway search '{"session_id":"ctxsession_...","query":"AgentContextSession"}'
graphview-agent-gateway run-shell '{"session_id":"ctxsession_...","command":"git","args":["status","--short"]}'
graphview-agent-gateway report-prompt '{"session_id":"ctxsession_...","text":"Prompt text"}'
graphview-agent-gateway report-model-call '{"session_id":"ctxsession_...","provider":"openai","model":"gpt-5","prompt_text":"Prompt text"}'
graphview-agent-gateway report-edit '{"session_id":"ctxsession_...","path":"apps/web/src/App.tsx","diff":"..."}'
graphview-agent-gateway get-diff '{"session_id":"ctxsession_...","path":"apps/web/src/App.tsx"}'
graphview-agent-gateway end-session '{"session_id":"ctxsession_..."}'
graphview-agent-gateway flush-outbox
```

The `graphview-codex` and `graphview-claude` binaries point at the same gateway entrypoint so runtime-specific wrapper
config can use stable command names without duplicating implementation. `end-session` updates
`/agent-context/sessions/{session_id}` with `PATCH`.

## Failure Modes

- Missing or invalid adapter tokens fail fast. Network failures, 408, 409, 425, 429, and 5xx responses queue the
  request in the outbox for retry; permanent 4xx responses are not queued.
- Denied paths such as `.env`, private keys, and certificate files are rejected before capture.
- Secret-looking text is redacted before events are sent.
- Binary or oversized content should be reported as metadata-only by callers.
