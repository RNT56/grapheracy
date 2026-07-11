#!/usr/bin/env node
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFile, mkdir, readFile, readdir, rename, stat, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { promisify } from "node:util";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const execFileAsync = promisify(execFile);
const defaultDeniedFragments = [".env", "id_rsa", "id_ed25519", ".pem", ".p12"];
const defaultSearchSkippedDirectories = new Set([".git", ".venv", "coverage", "dist", "node_modules"]);
const maxSearchFileBytes = 1024 * 1024;
const maxSearchVisitedFiles = 10_000;
const secretPatterns = [
  /(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*([^\s'"`]+)/gi,
  /bearer\s+[a-z0-9._~+/=-]{12,}/gi,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g
];

export const toolManifest = {
  name: "graphview-agent-context",
  version: "1.0.0",
  tools: [
    "start_session",
    "read_file",
    "search",
    "run_shell",
    "report_prompt",
    "report_model_call",
    "report_edit",
    "get_diff",
    "end_session"
  ].map((name) => ({ name, mutatesGraph: false, capturesContext: true }))
};

const commandToToolName = new Map([
  ["start-session", "start_session"],
  ["read-file", "read_file"],
  ["search", "search"],
  ["run-shell", "run_shell"],
  ["report-prompt", "report_prompt"],
  ["report-model-call", "report_model_call"],
  ["report-edit", "report_edit"],
  ["get-diff", "get_diff"],
  ["end-session", "end_session"]
]);

class GraphviewRequestError extends Error {
  constructor(message, { retryable }) {
    super(message);
    this.name = "GraphviewRequestError";
    this.retryable = retryable;
  }
}

export function createMcpServer(env = process.env) {
  const server = new Server(
    { name: toolManifest.name, version: toolManifest.version },
    { capabilities: { tools: { listChanged: false } } }
  );
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: toolManifest.tools.map((tool) => ({
      name: tool.name,
      title: tool.name.replaceAll("_", " "),
      description: `Graphview active context capture helper for ${tool.name}.`,
      inputSchema: {
        type: "object",
        additionalProperties: true
      },
      annotations: {
        readOnlyHint: tool.name !== "run_shell" && tool.name !== "report_edit",
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: tool.name === "run_shell"
      },
      _meta: { capturesContext: true, mutatesGraph: false }
    }))
  }));
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const result = await executeGatewayTool(request.params.name, request.params.arguments || {}, env);
    return mcpToolResponse(result);
  });
  return server;
}

function mcpToolResponse(result) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result, null, 2)
      }
    ]
  };
}

function toolMetadata(toolName) {
  return toolManifest.tools.find((tool) => tool.name === toolName);
}

function sessionIdFor(payload, env) {
  return payload.session_id || env.GRAPHVIEW_AGENT_CONTEXT_SESSION_ID;
}

export async function executeGatewayTool(toolName, payload = {}, env = process.env) {
  if (!toolMetadata(toolName)) throw new Error(`Unknown Graphview MCP tool: ${toolName}`);
  if (toolName === "start_session") return postWithOutbox("/agent-context/sessions", payload, env);
  if (toolName === "end_session") {
    const sessionId = sessionIdFor(payload, env);
    return postWithOutbox(`/agent-context/sessions/${encodeURIComponent(sessionId)}`, { status: "completed" }, env, "PATCH");
  }
  if (toolName === "read_file") {
    const result = await readFileRange(payload);
    const event = eventFromArtifact({
      sequence: payload.sequence || Date.now(),
      eventKind: "file_read",
      artifact: {
        kind: "file",
        path: result.path,
        title: result.title,
        content_type: payload.content_type || "text/plain",
        checksum: result.checksum,
        metadata: { locator: result.locator }
      },
      text: result.text,
      payload: { path: result.path, locator: result.locator }
    });
    return postWithOutbox("/agent-context/events/batch", { session_id: sessionIdFor(payload, env), events: [event] }, env);
  }
  if (toolName === "search") {
    const results = await searchWorkspace(payload);
    const text = results.map((result) => `${result.path}:${result.lineNumber}: ${result.text}`).join("\n");
    const event = eventFromArtifact({
      sequence: payload.sequence || Date.now(),
      eventKind: "search_performed",
      artifact: {
        kind: "search_result",
        title: `Search: ${payload.query || ""}`.trim(),
        content_type: "text/plain",
        metadata: { query: payload.query, result_count: results.length }
      },
      text,
      payload: { query: payload.query, result_count: results.length }
    });
    return postWithOutbox("/agent-context/events/batch", { session_id: sessionIdFor(payload, env), events: [event] }, env);
  }
  if (toolName === "run_shell") {
    const result = await runShellCapture(payload);
    const text = [`$ ${[result.command, ...(result.args || [])].join(" ")}`, result.stdout, result.stderr].filter(Boolean).join("\n");
    const event = eventFromArtifact({
      sequence: payload.sequence || Date.now(),
      eventKind: "shell_command",
      artifact: {
        kind: "shell",
        title: result.command,
        content_type: "text/plain",
        metadata: { exit_code: result.exitCode, status: result.status }
      },
      text,
      payload: {
        command: result.command,
        args: result.args,
        exit_code: result.exitCode,
        status: result.status,
        started_at: result.startedAt,
        finished_at: result.finishedAt
      }
    });
    return postWithOutbox("/agent-context/events/batch", { session_id: sessionIdFor(payload, env), events: [event] }, env);
  }
  if (toolName === "report_prompt") {
    const event = eventFromArtifact({
      sequence: payload.sequence || Date.now(),
      eventKind: "prompt_built",
      authority: payload.authority || "adapter_reported",
      artifact: { kind: "prompt", title: payload.title || "Prompt context", content_type: "text/plain" },
      text: redactedText(payload.text || ""),
      payload: { summary: payload.summary || "Built prompt context." }
    });
    return postWithOutbox("/agent-context/events/batch", { session_id: sessionIdFor(payload, env), events: [event] }, env);
  }
  if (toolName === "report_model_call") {
    const eventKind = payload.event_kind || (payload.response_text ? "model_response" : "model_request");
    const text = redactedText(payload.text || payload.prompt_text || payload.response_text || "");
    const event = eventFromArtifact({
      sequence: payload.sequence || Date.now(),
      eventKind,
      authority: payload.authority || "adapter_reported",
      artifact: { kind: "model", title: payload.title || eventKind.replace("_", " "), content_type: "text/plain" },
      text,
      payload: {
        provider: payload.provider,
        model: payload.model,
        trace_id: payload.trace_id,
        summary: payload.summary || `Reported ${eventKind.replace("_", " ")}.`
      }
    });
    return postWithOutbox("/agent-context/events/batch", { session_id: sessionIdFor(payload, env), events: [event] }, env);
  }
  if (toolName === "report_edit") {
    const event = eventFromArtifact({
      sequence: payload.sequence || Date.now(),
      eventKind: "edit_applied",
      artifact: {
        kind: "diff",
        path: payload.path,
        title: payload.title || payload.path || "Edit",
        content_type: payload.content_type || "text/plain"
      },
      text: redactedText(payload.diff || payload.text || ""),
      payload: { path: payload.path, summary: payload.summary || "Reported edit." }
    });
    return postWithOutbox("/agent-context/events/batch", { session_id: sessionIdFor(payload, env), events: [event] }, env);
  }
  if (toolName === "get_diff") {
    const args = payload.path ? ["diff", "--", payload.path] : ["diff"];
    const result = await runShellCapture({ ...payload, command: "git", args });
    const event = eventFromArtifact({
      sequence: payload.sequence || Date.now(),
      eventKind: "diff_observed",
      artifact: { kind: "diff", path: payload.path, title: payload.path || "Git diff", content_type: "text/x-diff" },
      text: result.stdout,
      payload: { path: payload.path, exit_code: result.exitCode, status: result.status }
    });
    return postWithOutbox("/agent-context/events/batch", { session_id: sessionIdFor(payload, env), events: [event] }, env);
  }
  throw new Error(`Unhandled Graphview MCP tool: ${toolName}`);
}

export async function runMcpServer(env = process.env) {
  const server = createMcpServer(env);
  await server.connect(new StdioServerTransport());
  return server;
}

export function redactedText(value) {
  let output = String(value ?? "");
  for (const pattern of secretPatterns) {
    output = output.replace(pattern, (...replaceArgs) => {
      const key = replaceArgs.length > 3 ? replaceArgs[1] : undefined;
      return typeof key === "string" && key ? `${key}=[redacted]` : "[redacted]";
    });
  }
  return output;
}

export function checksum(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function assertAllowedPath(path, workspaceRoot = process.cwd()) {
  const absolutePath = resolve(workspaceRoot, path);
  const relativePath = relative(resolve(workspaceRoot), absolutePath);
  if (relativePath.startsWith("..") || relativePath === "") {
    throw new Error(`Path is outside workspace: ${path}`);
  }
  if (defaultDeniedFragments.some((fragment) => relativePath.includes(fragment))) {
    throw new Error(`Path is denied by default capture policy: ${relativePath}`);
  }
  return { absolutePath, relativePath };
}

export async function readFileRange({ path, startLine = 1, endLine, workspaceRoot = process.cwd() }) {
  const { absolutePath, relativePath } = assertAllowedPath(path, workspaceRoot);
  const text = await readFile(absolutePath, "utf8");
  const lines = text.split(/\r?\n/);
  const start = Math.max(1, Number(startLine) || 1);
  const end = Math.min(lines.length, Number(endLine) || lines.length);
  const selected = lines.slice(start - 1, end).join("\n");
  return {
    path: relativePath,
    title: relativePath.split("/").pop() || relativePath,
    text: redactedText(selected),
    checksum: checksum(selected),
    byteCount: Buffer.byteLength(selected),
    locator: `${relativePath}#L${start}-L${end}`
  };
}

export async function searchWorkspace({ query, workspaceRoot = process.cwd(), maxResults = 20 }) {
  const normalizedQuery = String(query ?? "");
  const limit = Math.max(1, Math.min(100, Number(maxResults) || 20));
  if (!normalizedQuery) return [];

  const root = resolve(workspaceRoot);
  const pendingDirectories = [root];
  const results = [];
  let visitedFiles = 0;

  while (pendingDirectories.length > 0 && results.length < limit && visitedFiles < maxSearchVisitedFiles) {
    const directory = pendingDirectories.pop();
    const entries = await readdir(directory, { withFileTypes: true }).catch(() => []);
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      if (results.length >= limit || visitedFiles >= maxSearchVisitedFiles) break;
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory() && defaultSearchSkippedDirectories.has(entry.name)) continue;

      const absolutePath = join(directory, entry.name);
      const relativePath = relative(root, absolutePath);
      try {
        assertAllowedPath(relativePath, root);
      } catch {
        continue;
      }
      if (entry.isDirectory()) {
        pendingDirectories.push(absolutePath);
        continue;
      }
      if (!entry.isFile()) continue;

      visitedFiles += 1;
      const metadata = await stat(absolutePath).catch(() => undefined);
      if (!metadata || metadata.size > maxSearchFileBytes) continue;
      const content = await readFile(absolutePath, "utf8").catch(() => undefined);
      if (content === undefined || content.includes("\u0000")) continue;
      const lines = content.split(/\r?\n/);
      for (let index = 0; index < lines.length && results.length < limit; index += 1) {
        if (!lines[index].includes(normalizedQuery)) continue;
        results.push({ path: relativePath, lineNumber: index + 1, text: redactedText(lines[index]) });
      }
    }
  }
  return results;
}

export async function runShellCapture({ command, args = [], workspaceRoot = process.cwd(), timeoutMs = 30_000 }) {
  const startedAt = new Date().toISOString();
  const result = await execFileAsync(command, args, { cwd: workspaceRoot, timeout: timeoutMs, maxBuffer: 1024 * 1024 })
    .then(({ stdout, stderr }) => ({ status: "succeeded", stdout, stderr, exitCode: 0 }))
    .catch((error) => ({
      status: "failed",
      stdout: error.stdout || "",
      stderr: error.stderr || error.message,
      exitCode: Number.isInteger(error.code) ? error.code : 1
    }));
  return {
    ...result,
    command: redactedText(command),
    args: args.map((arg) => redactedText(arg)),
    startedAt,
    finishedAt: new Date().toISOString(),
    stdout: redactedText(result.stdout),
    stderr: redactedText(result.stderr)
  };
}

export function eventFromArtifact({ sequence, eventKind, authority = "gateway", artifact, text, payload = {} }) {
  return {
    client_event_id: `${eventKind}-${sequence}`,
    sequence,
    event_kind: eventKind,
    authority,
    summary: payload.summary,
    payload,
    artifact,
    content: text
      ? {
          content_kind: "text",
          media_type: artifact?.content_type || "text/plain",
          text,
          byte_count: Buffer.byteLength(text),
          checksum: checksum(text)
        }
      : undefined,
    occurred_at: new Date().toISOString()
  };
}

export async function postGraphview(path, body, env = process.env, method = "POST") {
  const baseUrl = env.GRAPHVIEW_API_BASE_URL || "http://127.0.0.1:8000";
  const token = env.GRAPHVIEW_AGENT_CONTEXT_TOKEN;
  if (!token) throw new Error("GRAPHVIEW_AGENT_CONTEXT_TOKEN is required");
  const canonicalPath = path.startsWith("/api/v1/") ? path : `/api/v1${path.startsWith("/") ? path : `/${path}`}`;
  const response = await fetch(`${baseUrl}${canonicalPath}`, {
    method,
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new GraphviewRequestError(`Graphview request failed ${response.status}: ${await response.text()}`, {
      retryable: response.status === 408 || response.status === 409 || response.status === 425 || response.status === 429 || response.status >= 500
    });
  }
  return response.json();
}

export async function postWithOutbox(path, body, env = process.env, method = "POST") {
  const canonicalPath = path.startsWith("/api/v1/") ? path : `/api/v1${path.startsWith("/") ? path : `/${path}`}`;
  try {
    return await postGraphview(canonicalPath, body, env, method);
  } catch (error) {
    if (error instanceof GraphviewRequestError && !error.retryable) throw error;
    const outboxPath = env.GRAPHVIEW_AGENT_CONTEXT_OUTBOX || ".graphview/agent-context-outbox.jsonl";
    await mkdir(dirname(outboxPath), { recursive: true });
    await appendFile(outboxPath, `${JSON.stringify({ method, path: canonicalPath, body, error: error.message, queued_at: new Date().toISOString() })}\n`);
    return { queued: true, outboxPath, error: error.message };
  }
}

export async function flushOutbox(env = process.env) {
  const outboxPath = env.GRAPHVIEW_AGENT_CONTEXT_OUTBOX || ".graphview/agent-context-outbox.jsonl";
  const flushedPath = `${outboxPath}.flushed`;
  const text = await readFile(outboxPath, "utf8").catch(() => "");
  if (!text.trim()) return { flushed: 0 };
  const lines = text.split("\n").filter(Boolean);
  let flushed = 0;
  for (const line of lines) {
    const item = JSON.parse(line);
    await postGraphview(item.path, item.body, env, item.method || "POST");
    flushed += 1;
  }
  await rename(outboxPath, flushedPath).catch(async () => {
    await writeFile(outboxPath, "");
  });
  return { flushed };
}

async function main(argv = process.argv.slice(2), env = process.env) {
  const [command, payloadJson = "{}"] = argv;
  const payload = JSON.parse(payloadJson);
  if (!command || command === "manifest") return toolManifest;
  if (command === "mcp-server") {
    await runMcpServer(env);
    return new Promise(() => {});
  }
  if (command === "flush-outbox") return flushOutbox(env);
  if (commandToToolName.has(command)) return executeGatewayTool(commandToToolName.get(command), payload, env);
  throw new Error(`Unknown graphview agent gateway command: ${command}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main()
    .then((result) => {
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    })
    .catch((error) => {
      process.stderr.write(`${error.stack || error.message}\n`);
      process.exitCode = 1;
    });
}
