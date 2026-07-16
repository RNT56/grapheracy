import type { GraphLensId } from "@graphview/shared-types";

const apiBaseUrl = import.meta.env.VITE_GRAPHVIEW_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

export function apiUrl(path: string) {
  return `${apiBaseUrl}${canonicalApiPath(path)}`;
}

function canonicalApiPath(path: string) {
  if (path.startsWith("/api/v1") || path === "/health" || path === "/version") return path;
  return `/api/v1${path}`;
}

let identitySessionPromise: Promise<void> | undefined;

async function ensureBrowserSession() {
  if (import.meta.env.DEV || window.sessionStorage.getItem("graphview.csrf-token")) return;
  identitySessionPromise ??= fetch(`${apiBaseUrl}/api/v1/auth/session`, { credentials: "include" }).then(async (response) => {
    if (response.status === 401) {
      const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      window.location.assign(`${apiBaseUrl}/api/v1/auth/login?return_to=${encodeURIComponent(returnTo)}`);
      throw new Error("Authentication required");
    }
    if (!response.ok) throw new Error(`Identity session returned ${response.status}`);
    const session = (await response.json()) as { csrf_token: string };
    window.sessionStorage.setItem("graphview.csrf-token", session.csrf_token);
  });
  return identitySessionPromise;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureBrowserSession();
  const csrfToken = window.sessionStorage.getItem("graphview.csrf-token");
  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(import.meta.env.DEV ? { "X-Graphview-User": "maintainer" } : {}),
      ...(csrfToken && !["GET", "HEAD", "OPTIONS"].includes((init?.method ?? "GET").toUpperCase())
        ? { "X-CSRF-Token": csrfToken }
        : {}),
      ...init?.headers
    }
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function waitForJob<T>(jobId: string, timeoutMs = 15 * 60_000): Promise<T> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const job = await fetchJson<{ status: string; result: T; error?: string | null }>(`/jobs/${encodeURIComponent(jobId)}`);
    if (job.status === "succeeded") return job.result;
    if (job.status === "failed" || job.status === "cancelled") throw new Error(job.error || `Job ${job.status}`);
    await new Promise((resolve) => window.setTimeout(resolve, 750));
  }
  throw new Error("Durable job timed out");
}

export function fetchHealth() {
  return fetchJson<{ status: string; service: string }>("/health");
}

export function graphScopedPath(path: string, graphId: string) {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}graph_id=${encodeURIComponent(graphId)}`;
}

export function graphLensScopedPath(path: string, graphId: string, lens: GraphLensId) {
  const scoped = graphScopedPath(path, graphId);
  const separator = scoped.includes("?") ? "&" : "?";
  return `${scoped}${separator}lens=${encodeURIComponent(lens)}`;
}

export function agentRunActivityPath(agentRunId: string) {
  return `/agent-runs/${encodeURIComponent(agentRunId)}/activity`;
}
