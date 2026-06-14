import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { activate, buildEditorEvent, deactivate, flushOutbox, postWithOutbox } from "../src/extension.mjs";

const OUTBOX_KEY = "graphview.agentContextOutbox";
const SESSION_KEY = "graphview.agentContextSessionId";

function mockContext(initial = []) {
  const options = Array.isArray(initial) ? { outbox: initial } : initial;
  const store = new Map([[OUTBOX_KEY, options.outbox || []]]);
  if (options.sessionId) store.set(SESSION_KEY, options.sessionId);
  return {
    subscriptions: [],
    globalState: {
      get: (key, fallback) => (store.has(key) ? store.get(key) : fallback),
      update: async (key, value) => {
        store.set(key, value);
      }
    },
    store
  };
}

function mockVscode({
  appName = "Visual Studio Code",
  workspaceName = "Graphview",
  workspaceFolders = [],
  activeTextEditor
} = {}) {
  const handlers = {};
  const commands = new Map();
  const disposable = { dispose: () => undefined };
  return {
    env: { appName },
    workspace: {
      name: workspaceName,
      workspaceFolders,
      getConfiguration: () => ({
        get: (key) => (key === "apiBaseUrl" ? "http://graphview.invalid" : "gvctx_test")
      }),
      onDidSaveTextDocument: (handler) => {
        handlers.save = handler;
        return disposable;
      }
    },
    window: {
      activeTextEditor,
      onDidChangeActiveTextEditor: (handler) => {
        handlers.activeEditor = handler;
        return disposable;
      },
      onDidChangeTextEditorSelection: (handler) => {
        handlers.selection = handler;
        return disposable;
      },
      showInformationMessage: (message) => {
        handlers.lastInformationMessage = message;
      }
    },
    commands: {
      registerCommand: (command, handler) => {
        commands.set(command, handler);
        return disposable;
      }
    },
    __commands: commands,
    __handlers: handlers
  };
}

async function withFetch(fetchImplementation, callback) {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = fetchImplementation;
  try {
    return await callback();
  } finally {
    globalThis.fetch = previousFetch;
  }
}

test("buildEditorEvent maps active editor state as passive reconciliation", () => {
  const mapped = buildEditorEvent({
    sessionId: "ctxsession_test",
    document: {
      uri: { fsPath: "/workspace/src/App.tsx" },
      languageId: "typescriptreact",
      isDirty: true
    },
    selection: { start: { line: 4 }, end: { line: 8 } },
    visibleRanges: [{ start: { line: 1 }, end: { line: 20 } }]
  });

  assert.equal(mapped.session_id, "ctxsession_test");
  assert.equal(mapped.event.event_kind, "selection_changed");
  assert.equal(mapped.event.authority, "passive_reconciled");
  assert.equal(mapped.event.artifact.kind, "selection");
  assert.equal(mapped.event.payload.start_line, 5);
  assert.equal(mapped.event.payload.end_line, 9);
  assert.equal(mapped.event.payload.is_dirty, true);
});

test("buildEditorEvent maps active editor open from visible ranges", () => {
  const mapped = buildEditorEvent({
    sessionId: "ctxsession_test",
    document: {
      uri: { fsPath: "/workspace/package.json" },
      languageId: "json",
      isDirty: false
    },
    visibleRanges: [{ start: { line: 2 }, end: { line: 12 } }]
  });

  assert.equal(mapped.event.event_kind, "file_opened");
  assert.equal(mapped.event.artifact.kind, "editor");
  assert.equal(mapped.event.summary, "Observed active editor package.json.");
  assert.equal(mapped.event.payload.start_line, 3);
  assert.equal(mapped.event.payload.end_line, 13);
  assert.deepEqual(mapped.event.payload.visible_ranges, [{ start_line: 3, end_line: 13 }]);
  assert.equal(mapped.event.payload.is_dirty, false);
  assert.equal(mapped.event.artifact.metadata.source, "vscode-extension");
});

test("activate reports active editor open, save events, and workspace metadata", async () => {
  await deactivate();
  const previousVscode = globalThis.vscode;
  const requests = [];
  const vscode = mockVscode({
    appName: "Cursor",
    workspaceFolders: [
      { name: "graphview", uri: { fsPath: "/workspace/graphview" } },
      { name: "docs", uri: { fsPath: "/workspace/graphview/docs" } }
    ],
    activeTextEditor: {
      document: {
        uri: { fsPath: "/workspace/graphview/apps/web/src/App.tsx" },
        languageId: "typescriptreact",
        isDirty: false
      },
      selection: { start: { line: 20 }, end: { line: 22 } },
      visibleRanges: [{ start: { line: 4 }, end: { line: 30 } }]
    }
  });
  globalThis.vscode = vscode;

  await withFetch(
    async (url, init) => {
      const body = JSON.parse(init.body);
      requests.push({ url, body, headers: init.headers, method: init.method });
      if (url.endsWith("/agent-context/sessions")) return { ok: true, json: async () => ({ id: "ctxsession_cursor" }) };
      if (url.endsWith("/agent-context/events/batch")) {
        return { ok: true, json: async () => ({ accepted_count: body.events.length }) };
      }
      return { ok: false, status: 404, text: async () => "not found" };
    },
    async () => {
      try {
        const context = mockContext();
        await activate(context);

        const sessionRequest = requests.find((request) => request.url.endsWith("/agent-context/sessions"));
        assert.equal(sessionRequest.method, "POST");
        assert.equal(sessionRequest.headers.authorization, "Bearer gvctx_test");
        assert.equal(sessionRequest.body.runtime_kind, "cursor");
        assert.equal(sessionRequest.body.authority, "passive_reconciled");
        assert.equal(sessionRequest.body.workspace_root, "/workspace/graphview");
        assert.deepEqual(sessionRequest.body.metadata, {
          app_name: "Cursor",
          adapter: "vscode-extension",
          workspace_name: "Graphview",
          workspace_folders: [
            { name: "graphview", path: "/workspace/graphview" },
            { name: "docs", path: "/workspace/graphview/docs" }
          ]
        });
        assert.equal(context.store.get(SESSION_KEY), "ctxsession_cursor");

        const initialBatch = requests.filter((request) => request.url.endsWith("/agent-context/events/batch"))[0];
        assert.equal(initialBatch.body.session_id, "ctxsession_cursor");
        const activeEditorEvent = initialBatch.body.events[0];
        assert.equal(activeEditorEvent.event_kind, "file_opened");
        assert.equal(activeEditorEvent.authority, "passive_reconciled");
        assert.equal(activeEditorEvent.payload.path, "/workspace/graphview/apps/web/src/App.tsx");
        assert.equal(activeEditorEvent.payload.start_line, 5);
        assert.equal(activeEditorEvent.payload.end_line, 31);
        assert.equal(activeEditorEvent.artifact.kind, "editor");

        await vscode.__handlers.save({
          uri: { fsPath: "/workspace/graphview/apps/web/src/App.tsx" },
          languageId: "typescriptreact",
          isDirty: false
        });

        const savedBatch = requests.filter((request) => request.url.endsWith("/agent-context/events/batch"))[1];
        const savedEvent = savedBatch.body.events[0];
        assert.equal(savedBatch.body.session_id, "ctxsession_cursor");
        assert.equal(savedEvent.event_kind, "file_opened");
        assert.equal(savedEvent.payload.saved, true);
        assert.equal(savedEvent.payload.path, "/workspace/graphview/apps/web/src/App.tsx");
        assert.equal(savedEvent.artifact.kind, "editor");
      } finally {
        globalThis.vscode = previousVscode;
        await deactivate();
      }
    }
  );
});

test("postWithOutbox persists failed adapter events for offline replay", async () => {
  const context = mockContext();

  await withFetch(
    async () => {
      throw new Error("offline");
    },
    async () => {
      const result = await postWithOutbox(
        "/agent-context/events/batch",
        { session_id: "ctxsession_test", events: [] },
        mockVscode(),
        context
      );

      assert.equal(result.queued, true);
      assert.equal(context.store.get(OUTBOX_KEY).length, 1);
    }
  );
});

test("flushOutbox replays queued adapter events and keeps failures", async () => {
  const context = mockContext([
    { path: "/agent-context/events/batch", body: { session_id: "ctxsession_ok", events: [] } },
    { path: "/agent-context/events/batch", body: { session_id: "ctxsession_retry", events: [] } }
  ]);
  let calls = 0;

  await withFetch(
    async () => {
      calls += 1;
      if (calls === 2) throw new Error("still offline");
      return { ok: true, json: async () => ({ accepted_count: 0 }) };
    },
    async () => {
      const result = await flushOutbox(context, mockVscode());

      assert.equal(result.flushed, 1);
      assert.equal(result.remaining, 1);
      assert.equal(context.store.get(OUTBOX_KEY)[0].body.session_id, "ctxsession_retry");
    }
  );
});

test("postWithOutbox does not queue permanent Graphview policy failures", async () => {
  const context = mockContext();

  await withFetch(
    async () => ({
      ok: false,
      status: 403,
      text: async () => "denied"
    }),
    async () => {
      const result = await postWithOutbox(
        "/agent-context/events/batch",
        { session_id: "ctxsession_denied", events: [] },
        mockVscode(),
        context
      );

      assert.equal(result.queued, false);
      assert.equal(result.rejected, true);
      assert.equal(context.store.get(OUTBOX_KEY).length, 0);
    }
  );
});

test("package manifest stays valid for VS Code packaging", async () => {
  const manifest = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  const extensionSource = await readFile(new URL(`../${manifest.main}`, import.meta.url), "utf8");

  assert.equal(manifest.name, "@graphview/vscode-extension");
  assert.equal(manifest.displayName, "Graphview Active Context");
  assert.equal(manifest.publisher, "graphview");
  assert.equal(manifest.private, true);
  assert.equal(manifest.type, "module");
  assert.equal(manifest.main, "src/extension.mjs");
  assert.equal(manifest.engines.vscode, "^1.96.0");
  assert.deepEqual(manifest.files, ["src", "README.md", "package.json"]);
  assert.ok(manifest.categories.includes("Other"));
  assert.ok(extensionSource.includes("export async function activate"));

  const commandIds = manifest.contributes.commands.map((command) => command.command);
  assert.deepEqual(commandIds, [
    "graphview.startAgentContextSession",
    "graphview.flushAgentContextHeartbeat"
  ]);
  assert.ok(manifest.activationEvents.includes("onStartupFinished"));
  for (const command of commandIds) {
    assert.ok(manifest.activationEvents.includes(`onCommand:${command}`));
  }

  const properties = manifest.contributes.configuration.properties;
  assert.equal(properties["graphview.apiBaseUrl"].type, "string");
  assert.equal(properties["graphview.apiBaseUrl"].default, "http://127.0.0.1:8000");
  assert.equal(properties["graphview.agentContextToken"].type, "string");
  assert.equal(properties["graphview.agentContextToken"].default, "");
  assert.equal(manifest.scripts.check, "pnpm run typecheck && pnpm run test");
  assert.equal(manifest.scripts.typecheck, "node --check src/extension.mjs");
  assert.equal(manifest.scripts.test, "node --test tests/*.test.mjs");
  assert.deepEqual(Object.keys(manifest.dependencies || {}), []);
  assert.deepEqual(Object.keys(manifest.devDependencies), ["@types/vscode"]);
});
