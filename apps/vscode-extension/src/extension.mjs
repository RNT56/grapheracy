/** @typedef {import("vscode").ExtensionContext} ExtensionContext */
/** @typedef {import("vscode").TextDocument} TextDocument */

let activeSessionId;
let sequence = 1;
const OUTBOX_KEY = "graphview.agentContextOutbox";

export function buildEditorEvent({ sessionId, document, selection, visibleRanges = [], authority = "passive_reconciled" }) {
  const nextSequence = sequence++;
  const path = document.uri?.fsPath || document.fileName || document.uri?.toString?.() || "untitled";
  const title = path.split(/[\\/]/).pop() || "Editor";
  const startLine = selection?.start?.line != null ? selection.start.line + 1 : visibleRanges[0]?.start?.line + 1 || 1;
  const endLine = selection?.end?.line != null ? selection.end.line + 1 : visibleRanges[0]?.end?.line + 1 || startLine;
  return {
    session_id: sessionId,
    event: {
      client_event_id: `editor-${Date.now()}-${nextSequence}`,
      sequence: nextSequence,
      event_kind: selection ? "selection_changed" : "file_opened",
      authority,
      summary: selection ? `Selected ${title} lines ${startLine}-${endLine}.` : `Observed active editor ${title}.`,
      payload: {
        path,
        language_id: document.languageId,
        is_dirty: Boolean(document.isDirty),
        start_line: startLine,
        end_line: endLine,
        visible_ranges: visibleRanges.map((range) => ({ start_line: range.start.line + 1, end_line: range.end.line + 1 }))
      },
      artifact: {
        kind: selection ? "selection" : "editor",
        path,
        title,
        content_type: document.languageId ? `text/x-${document.languageId}` : "text/plain",
        metadata: { source: "vscode-extension" }
      },
      occurred_at: new Date().toISOString()
    }
  };
}

async function getVscode() {
  return globalThis.vscode || import("vscode");
}

function configuration(vscode) {
  const config = vscode.workspace.getConfiguration("graphview");
  return {
    apiBaseUrl: config.get("apiBaseUrl") || "http://127.0.0.1:8000",
    token: config.get("agentContextToken") || process.env.GRAPHVIEW_AGENT_CONTEXT_TOKEN || ""
  };
}

function workspaceMetadata(vscode) {
  const workspaceFolders = vscode.workspace.workspaceFolders || [];
  return {
    app_name: vscode.env.appName,
    adapter: "vscode-extension",
    workspace_name: vscode.workspace.name,
    workspace_folders: workspaceFolders.map((folder) => ({
      name: folder.name,
      path: folder.uri?.fsPath || folder.uri?.toString?.()
    }))
  };
}

async function postGraphview(path, body, vscode) {
  const { apiBaseUrl, token } = configuration(vscode);
  if (!token) return { skipped: true, reason: "missing-token" };
  const canonicalPath = path.startsWith("/api/v1/") ? path : `/api/v1${path.startsWith("/") ? path : `/${path}`}`;
  const response = await fetch(`${apiBaseUrl}${canonicalPath}`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const error = new Error(`Graphview request failed ${response.status}: ${await response.text()}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function enqueueOutbox(context, path, body, error) {
  if (!context?.globalState) return { queued: false, reason: "missing-global-state" };
  const current = context.globalState.get(OUTBOX_KEY, []);
  const outbox = Array.isArray(current) ? current : [];
  const canonicalPath = path.startsWith("/api/v1/") ? path : `/api/v1${path.startsWith("/") ? path : `/${path}`}`;
  const queued = [
    ...outbox,
    { path: canonicalPath, body, error: error?.message || String(error || "offline"), queued_at: new Date().toISOString() }
  ].slice(-200);
  await context.globalState.update(OUTBOX_KEY, queued);
  return { queued: true, count: queued.length };
}

export async function postWithOutbox(path, body, vscode, context) {
  try {
    return await postGraphview(path, body, vscode);
  } catch (error) {
    if (error.status && error.status < 500 && error.status !== 429) {
      return { queued: false, rejected: true, status: error.status, error: error.message };
    }
    return enqueueOutbox(context, path, body, error);
  }
}

export async function flushOutbox(context, vscode) {
  if (!context?.globalState) return { flushed: 0, remaining: 0 };
  const current = context.globalState.get(OUTBOX_KEY, []);
  const outbox = Array.isArray(current) ? current : [];
  const remaining = [];
  let flushed = 0;
  for (const item of outbox) {
    try {
      await postGraphview(item.path, item.body, vscode);
      flushed += 1;
    } catch (error) {
      if (!error.status || error.status >= 500 || error.status === 429) {
        remaining.push({ ...item, error: error.message, last_attempt_at: new Date().toISOString() });
      }
    }
  }
  await context.globalState.update(OUTBOX_KEY, remaining);
  return { flushed, remaining: remaining.length };
}

async function ensureSession(vscode, context) {
  if (activeSessionId) return activeSessionId;
  activeSessionId = context?.globalState?.get?.("graphview.agentContextSessionId");
  if (activeSessionId) return activeSessionId;
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath;
  const created = await postGraphview(
    "/agent-context/sessions",
    {
      title: "VS Code active editor context",
      runtime_kind: vscode.env.appName?.toLowerCase().includes("cursor") ? "cursor" : "vscode",
      authority: "passive_reconciled",
      workspace_root: workspaceRoot,
      metadata: workspaceMetadata(vscode)
    },
    vscode
  );
  activeSessionId = created.id;
  await context?.globalState?.update?.("graphview.agentContextSessionId", activeSessionId);
  return activeSessionId;
}

async function captureEditor(editor, vscode, context, { includeSelection = true } = {}) {
  if (!editor?.document) return;
  const sessionId = await ensureSession(vscode, context).catch(() => undefined);
  if (!sessionId) return;
  const mapped = buildEditorEvent({
    sessionId,
    document: editor.document,
    selection: includeSelection ? editor.selection : undefined,
    visibleRanges: editor.visibleRanges || []
  });
  await postWithOutbox("/agent-context/events/batch", { session_id: sessionId, events: [mapped.event] }, vscode, context);
}

/** @param {ExtensionContext} context */
export async function activate(context) {
  const vscode = await getVscode();
  context.subscriptions.push(
    vscode.commands.registerCommand("graphview.startAgentContextSession", async () => {
      activeSessionId = undefined;
      await context.globalState.update("graphview.agentContextSessionId", undefined);
      await ensureSession(vscode, context);
      vscode.window.showInformationMessage("Graphview active context session started.");
    }),
    vscode.commands.registerCommand("graphview.flushAgentContextHeartbeat", async () => {
      await flushOutbox(context, vscode);
      const sessionId = await ensureSession(vscode, context);
      await postWithOutbox(
        "/agent-context/events/batch",
        {
          session_id: sessionId,
          events: [
            {
              client_event_id: `heartbeat-${Date.now()}`,
              sequence: sequence++,
              event_kind: "heartbeat",
              authority: "passive_reconciled",
              summary: "VS Code extension heartbeat.",
              payload: { app_name: vscode.env.appName }
            }
          ]
        },
        vscode,
        context
      );
    }),
    vscode.window.onDidChangeActiveTextEditor((editor) =>
      captureEditor(editor, vscode, context, { includeSelection: false })
    ),
    vscode.window.onDidChangeTextEditorSelection((event) => captureEditor(event.textEditor, vscode, context)),
    vscode.workspace.onDidSaveTextDocument(async (document) => {
      const sessionId = await ensureSession(vscode, context).catch(() => undefined);
      if (!sessionId) return;
      const mapped = buildEditorEvent({ sessionId, document, authority: "passive_reconciled" });
      mapped.event.event_kind = "file_opened";
      mapped.event.payload.saved = true;
      await postWithOutbox("/agent-context/events/batch", { session_id: sessionId, events: [mapped.event] }, vscode, context);
    })
  );
  await flushOutbox(context, vscode).catch(() => undefined);
  if (vscode.window.activeTextEditor) {
    await captureEditor(vscode.window.activeTextEditor, vscode, context, { includeSelection: false });
  }
}

export async function deactivate() {
  activeSessionId = undefined;
}
