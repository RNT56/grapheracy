import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import net from "node:net";

const root = process.cwd();
const tempDir = await mkdtemp(path.join(tmpdir(), "graphview-phase27-smoke-"));
const apiPort = await freePort();
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
const outboxPath = path.join(tempDir, "agent-context-outbox.jsonl");
const smokeSecretKey = `phase27-${randomUUID()}`;
let apiProcess;

try {
  apiProcess = startApi(apiPort, tempDir);
  await waitForHealth(apiBaseUrl);

  const clientResponse = await fetchJson(`${apiBaseUrl}/agent-context/clients`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-graphview-user": "maintainer" },
    body: JSON.stringify({
      display_name: "Phase 27 smoke gateway",
      runtime_kind: "codex",
      scopes: ["context:read", "context:capture"],
      settings: { workspace_roots: [root] }
    })
  });
  assert(clientResponse.token?.startsWith("gvctx_"), "adapter token was not returned once");
  assert(!JSON.stringify(clientResponse).includes("token_hash"), "client response leaked token hash");
  assert(
    JSON.stringify(clientResponse.client.scopes) === JSON.stringify(["context:capture"]),
    "adapter client scopes were not normalized to capture-only"
  );

  const gatewayEnv = {
    ...process.env,
    GRAPHVIEW_API_BASE_URL: apiBaseUrl,
    GRAPHVIEW_AGENT_CONTEXT_TOKEN: clientResponse.token,
    GRAPHVIEW_AGENT_CONTEXT_OUTBOX: outboxPath
  };
  const session = await gateway("start-session", {
    title: "Phase 27 smoke session",
    runtime_kind: "codex",
    authority: "gateway",
    workspace_root: root,
    repository_uri: "local://graphview",
    branch: "phase27-smoke"
  }, gatewayEnv);
  assert(session.id?.startsWith("ctxsession_"), "gateway did not create a context session");

  const eventEnv = { ...gatewayEnv, GRAPHVIEW_AGENT_CONTEXT_SESSION_ID: session.id };
  await gateway("read-file", { sequence: 1, path: "README.md", startLine: 1, endLine: 20, workspaceRoot: root }, eventEnv);
  await gateway("search", { sequence: 2, query: "Phase 27", workspaceRoot: root, maxResults: 5 }, eventEnv);
  await gateway("run-shell", {
    sequence: 3,
    command: process.execPath,
    args: ["-e", "console.log('phase27 smoke shell output')"],
    workspaceRoot: root
  }, eventEnv);
  await gateway("report-prompt", {
    sequence: 4,
    title: "Smoke prompt",
    text: "Use README context and redact token=secret-value",
    summary: "Built smoke prompt."
  }, eventEnv);
  await gateway("report-model-call", {
    sequence: 5,
    provider: "openai-compatible",
    model: "smoke-model",
    response_text: "Smoke model response with api_key=secret-value",
    summary: "Reported smoke model response."
  }, eventEnv);
  await gateway("report-edit", {
    sequence: 6,
    path: "README.md",
    diff: "+OPENAI_API_KEY=sk-smoke\n+Phase 27 smoke edit",
    summary: "Reported smoke edit."
  }, eventEnv);
  await gateway("get-diff", { sequence: 7, path: "README.md", workspaceRoot: root }, eventEnv);
  await gateway("end-session", { session_id: session.id }, eventEnv);

  const events = await fetchJson(`${apiBaseUrl}/agent-context/sessions/${session.id}/events?limit=25`, {
    headers: { "x-graphview-user": "reader" }
  });
  const eventKinds = new Set(events.events.map((event) => event.event_kind));
  for (const kind of ["file_read", "search_performed", "shell_command", "prompt_built", "model_response", "edit_applied", "diff_observed"]) {
    assert(eventKinds.has(kind), `missing captured event kind ${kind}`);
  }
  assert(events.events.every((event) => typeof event.checksum === "string" && event.checksum.length === 64), "event checksum missing");
  assert(!JSON.stringify(events).includes("secret-value"), "event payload leaked secret-value");
  assert(!JSON.stringify(events).includes("sk-smoke"), "event payload leaked API key text");

  const graph = await fetchJson(`${apiBaseUrl}/agent-context/sessions/${session.id}/graph`, {
    headers: { "x-graphview-user": "reader" }
  });
  assert(graph.nodes.length >= 2, "context graph did not include session/artifact nodes");
  assert(graph.edges.some((edge) => edge.relation === "read"), "context graph did not include read edge");
  assert(graph.events.length >= 7, "context graph did not include captured events");

  const fileArtifact = graph.artifacts.find((artifact) => artifact.kind === "file");
  assert(fileArtifact?.id, "file artifact missing from graph projection");
  const readerContent = await fetch(`${apiBaseUrl}/agent-context/artifacts/${fileArtifact.id}/content`, {
    headers: { "x-graphview-user": "reader" }
  });
  assert(readerContent.status === 403, "reader unexpectedly read context artifact content");
  const maintainerContent = await fetchJson(`${apiBaseUrl}/agent-context/artifacts/${fileArtifact.id}/content`, {
    headers: { "x-graphview-user": "maintainer" }
  });
  assert(
    maintainerContent.text?.includes("Graphview") && maintainerContent.text?.includes("Phase 27"),
    "maintainer content read did not return captured README text"
  );

  const completed = await fetchJson(`${apiBaseUrl}/agent-context/sessions/${session.id}`, {
    headers: { "x-graphview-user": "reader" }
  });
  assert(completed.status === "completed", "end-session did not mark session completed");

  const outbox = await readFile(outboxPath, "utf8").catch(() => "");
  assert(outbox.trim() === "", "gateway wrote retry outbox while API was healthy");

  console.log(`Phase 27 smoke passed against ${apiBaseUrl}`);
} finally {
  if (apiProcess) {
    apiProcess.kill("SIGTERM");
    await new Promise((resolve) => {
      apiProcess.once("exit", resolve);
      setTimeout(resolve, 2000);
    });
  }
  await rm(tempDir, { recursive: true, force: true });
}

function startApi(port, workingDir) {
  const child = spawn(
    "uv",
    ["run", "--project", "services/api", "uvicorn", "graphview_api.main:app", "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: root,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: path.join(root, "services/api/src"),
        GRAPHVIEW_DATABASE_URL: `sqlite:///${path.join(workingDir, "graphview.sqlite")}`,
        GRAPHVIEW_SECRET_KEY: smokeSecretKey,
        GRAPHVIEW_AGENT_CONTEXT_MAX_BLOB_BYTES: "200000",
        GRAPHVIEW_AGENT_CONTEXT_RETENTION_DAYS: "1"
      }
    }
  );
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  child.stdout.on("data", () => {});
  child.once("exit", (code) => {
    if (code !== 0 && code !== null) {
      console.error(stderr.trim());
    }
  });
  return child;
}

async function waitForHealth(baseUrl) {
  const deadline = Date.now() + 20_000;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) return;
      lastError = new Error(`health returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`API did not become healthy: ${lastError?.message || "unknown error"}`);
}

async function gateway(command, payload, env) {
  const output = await execNode(["services/agent-gateway/src/index.mjs", command, JSON.stringify(payload)], env);
  return JSON.parse(output);
}

async function execNode(args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve(stdout);
      else reject(new Error(`${args.join(" ")} failed with ${code}: ${stderr || stdout}`));
    });
  });
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${init?.method || "GET"} ${url} failed ${response.status}: ${text}`);
  }
  return JSON.parse(text);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}
