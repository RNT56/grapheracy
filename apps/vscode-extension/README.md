# Graphview VS Code / Cursor Extension

## Purpose

Reports editor state into Graphview's Active Context lens. Editor-open, selection, visible range, save, and heartbeat
events are marked as `passive_reconciled` because they indicate what the editor observed, not what an LLM prompt
authoritatively included.

## Setup

1. Create an adapter token with `POST /agent-context/clients`.
2. Configure `graphview.apiBaseUrl` and `graphview.agentContextToken`.
3. Run `Graphview: Start Agent Context Session`.

Cursor compatibility uses the same VS Code extension API surface. The extension detects Cursor by `vscode.env.appName`
and reports `runtime_kind: cursor`.

## Local Checks

```sh
pnpm --filter @graphview/vscode-extension typecheck
pnpm --filter @graphview/vscode-extension test
pnpm --filter @graphview/vscode-extension check
```

The test suite covers editor-open, selection, save, outbox replay, workspace session metadata, and package manifest
validation without requiring a live VS Code host.

## Failure Modes

- Missing token skips posting instead of exposing secrets in logs.
- Failed event posts are stored in extension `globalState` and replayed by `Graphview: Send Agent Context Heartbeat` or
  on the next activation.
- Editor observations remain `passive_reconciled`.
- Full file content is not captured by this extension; authoritative reads should use the agent gateway.
