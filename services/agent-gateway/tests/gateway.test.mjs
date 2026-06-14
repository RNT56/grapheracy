import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import {
  assertAllowedPath,
  createMcpServer,
  eventFromArtifact,
  executeGatewayTool,
  flushOutbox,
  postWithOutbox,
  readFileRange,
  redactedText,
  searchWorkspace,
  toolManifest
} from "../src/index.mjs";

test("manifest exposes required context capture tools", () => {
  const toolNames = new Set(toolManifest.tools.map((tool) => tool.name));
  assert.ok(toolNames.has("start_session"));
  assert.ok(toolNames.has("read_file"));
  assert.ok(toolNames.has("report_model_call"));
  assert.ok(toolNames.has("end_session"));
});

test("MCP SDK server registers without mutating graph state", () => {
  const server = createMcpServer();

  assert.equal(typeof server.setRequestHandler, "function");
  assert.equal(typeof server.connect, "function");
});

test("readFileRange captures selected text and redacts secrets", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  await mkdir(join(root, "src"));
  await writeFile(join(root, "src", "config.ts"), "line 1\nOPENAI_API_KEY=sk-secret\nline 3\n");

  const result = await readFileRange({ workspaceRoot: root, path: "src/config.ts", startLine: 2, endLine: 3 });

  assert.equal(result.path, "src/config.ts");
  assert.match(result.text, /OPENAI_API_KEY=\[redacted\]/);
  assert.doesNotMatch(result.text, /sk-secret/);
  assert.equal(result.locator, "src/config.ts#L2-L3");
});

test("denied default paths are rejected before capture", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  await writeFile(join(root, ".env"), "TOKEN=secret\n");

  assert.throws(() => assertAllowedPath(".env", root), /denied/);
});

test("searchWorkspace filters denied path results before capture", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  await mkdir(join(root, "src"));
  await writeFile(join(root, "src", "notes.txt"), "needle safe\n");
  await writeFile(join(root, "private.pem"), "needle secret\n");

  const results = await searchWorkspace({ workspaceRoot: root, query: "needle" });

  assert.deepEqual(
    results.map((result) => result.path),
    ["src/notes.txt"]
  );
});

test("eventFromArtifact produces Graphview batch-compatible event shape", () => {
  const event = eventFromArtifact({
    sequence: 7,
    eventKind: "prompt_built",
    authority: "adapter_reported",
    artifact: { kind: "prompt", title: "Prompt", content_type: "text/plain" },
    text: redactedText("token=secret"),
    payload: { summary: "Built prompt" }
  });

  assert.equal(event.client_event_id, "prompt_built-7");
  assert.equal(event.event_kind, "prompt_built");
  assert.equal(event.artifact.kind, "prompt");
  assert.equal(event.content.text, "token=[redacted]");
});

test("postWithOutbox queues failed Graphview requests", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  const outbox = join(root, "outbox.jsonl");

  const result = await postWithOutbox(
    "/agent-context/events/batch",
    { session_id: "ctxsession_missing", events: [] },
    {
      GRAPHVIEW_API_BASE_URL: "http://127.0.0.1:1",
      GRAPHVIEW_AGENT_CONTEXT_TOKEN: "gvctx_test",
      GRAPHVIEW_AGENT_CONTEXT_OUTBOX: outbox
    }
  );

  assert.equal(result.queued, true);
  const queued = await readFile(outbox, "utf8");
  assert.match(queued, /agent-context\/events\/batch/);
});

test("postWithOutbox does not queue permanent Graphview failures", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  const outbox = join(root, "outbox.jsonl");
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("forbidden", { status: 403 });
  try {
    await assert.rejects(
      () =>
        postWithOutbox(
          "/agent-context/events/batch",
          { session_id: "ctxsession_missing", events: [] },
          {
            GRAPHVIEW_API_BASE_URL: "http://127.0.0.1:8000",
            GRAPHVIEW_AGENT_CONTEXT_TOKEN: "gvctx_test",
            GRAPHVIEW_AGENT_CONTEXT_OUTBOX: outbox
          }
        ),
      /403/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  const queued = await readFile(outbox, "utf8").catch(() => "");
  assert.equal(queued, "");
});

test("end_session uses PATCH so the gateway matches the Graphview API", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return Response.json({ id: "ctxsession_test", status: "completed" });
  };
  try {
    const result = await executeGatewayTool(
      "end_session",
      { session_id: "ctxsession_test" },
      {
        GRAPHVIEW_API_BASE_URL: "http://127.0.0.1:8000",
        GRAPHVIEW_AGENT_CONTEXT_TOKEN: "gvctx_test"
      }
    );
    assert.equal(result.status, "completed");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls[0].init.method, "PATCH");
  assert.match(String(calls[0].url), /agent-context\/sessions\/ctxsession_test$/);
});

test("executeGatewayTool maps prompt reports to idempotent outbox events", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  const outbox = join(root, "outbox.jsonl");

  const result = await executeGatewayTool(
    "report_prompt",
    { session_id: "ctxsession_test", sequence: 11, text: "token=secret" },
    {
      GRAPHVIEW_API_BASE_URL: "http://127.0.0.1:1",
      GRAPHVIEW_AGENT_CONTEXT_TOKEN: "gvctx_test",
      GRAPHVIEW_AGENT_CONTEXT_OUTBOX: outbox
    }
  );

  assert.equal(result.queued, true);
  const queued = await readFile(outbox, "utf8");
  assert.match(queued, /prompt_built/);
  assert.doesNotMatch(queued, /token=secret/);
});

test("run_shell captures stdout and stderr while redacting shell secrets", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  const outbox = join(root, "outbox.jsonl");

  const result = await executeGatewayTool(
    "run_shell",
    {
      session_id: "ctxsession_test",
      sequence: 13,
      workspaceRoot: root,
      command: process.execPath,
      args: ["-e", "console.log('token=shell-secret'); console.error('password=stderr-secret')"]
    },
    {
      GRAPHVIEW_API_BASE_URL: "http://127.0.0.1:1",
      GRAPHVIEW_AGENT_CONTEXT_TOKEN: "gvctx_test",
      GRAPHVIEW_AGENT_CONTEXT_OUTBOX: outbox
    }
  );

  assert.equal(result.queued, true);
  const queued = await readFile(outbox, "utf8");
  assert.doesNotMatch(queued, /shell-secret|stderr-secret/);

  const item = JSON.parse(queued.trim());
  const event = item.body.events[0];
  assert.equal(event.event_kind, "shell_command");
  assert.equal(event.payload.status, "succeeded");
  assert.equal(event.payload.exit_code, 0);
  assert.match(event.content.text, /token=\[redacted\]/);
  assert.match(event.content.text, /password=\[redacted\]/);
  assert.ok(event.payload.args.every((arg) => !/shell-secret|stderr-secret/.test(arg)));
});

test("flushOutbox replays queued requests with their original method", async () => {
  const root = await mkdtemp(join(tmpdir(), "graphview-agent-gateway-"));
  const outbox = join(root, "outbox.jsonl");
  const env = {
    GRAPHVIEW_API_BASE_URL: "http://graphview.test",
    GRAPHVIEW_AGENT_CONTEXT_TOKEN: "gvctx_test",
    GRAPHVIEW_AGENT_CONTEXT_OUTBOX: outbox
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("offline");
  };
  try {
    const result = await postWithOutbox("/agent-context/sessions/ctxsession_test", { status: "completed" }, env, "PATCH");
    assert.equal(result.queued, true);
  } finally {
    globalThis.fetch = originalFetch;
  }

  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return Response.json({ id: "ctxsession_test", status: "completed" });
  };
  try {
    const result = await flushOutbox(env);
    assert.equal(result.flushed, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls[0].init.method, "PATCH");
  assert.match(String(calls[0].url), /agent-context\/sessions\/ctxsession_test$/);
});

test("MCP tools/call dispatches gateway tools through the SDK server", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return Response.json({ accepted: true });
  };

  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const server = createMcpServer({
    GRAPHVIEW_API_BASE_URL: "http://graphview.test",
    GRAPHVIEW_AGENT_CONTEXT_TOKEN: "gvctx_test"
  });
  const client = new Client({ name: "graphview-agent-gateway-test", version: "0.0.0" }, { capabilities: {} });

  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);

    const tools = await client.listTools();
    assert.ok(tools.tools.some((tool) => tool.name === "report_prompt"));

    const response = await client.callTool({
      name: "report_prompt",
      arguments: { session_id: "ctxsession_test", sequence: 19, text: "token=mcp-secret" }
    });
    assert.equal(response.content[0].type, "text");
    assert.deepEqual(JSON.parse(response.content[0].text), { accepted: true });
  } finally {
    await client.close().catch(() => {});
    await server.close().catch(() => {});
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls[0].init.method, "POST");
  assert.match(String(calls[0].url), /agent-context\/events\/batch$/);
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.events[0].event_kind, "prompt_built");
  assert.equal(body.events[0].content.text, "token=[redacted]");
});
