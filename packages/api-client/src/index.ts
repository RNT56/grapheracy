import type { paths } from "./schema";

export type ApiPaths = paths;

export interface GraphviewClientOptions {
  baseUrl: string;
  fetch?: typeof globalThis.fetch;
  csrfToken?: () => string | undefined;
}

export function createGraphviewClient(options: GraphviewClientOptions) {
  const request = options.fetch ?? globalThis.fetch;
  return async function graphviewRequest<Path extends keyof paths, Method extends keyof paths[Path]>(
    path: Path,
    method: Method,
    init: RequestInit = {}
  ): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    const csrfToken = options.csrfToken?.();
    if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(String(method).toUpperCase())) {
      headers.set("X-CSRF-Token", csrfToken);
    }
    return request(`${options.baseUrl}${String(path)}`, {
      ...init,
      method: String(method).toUpperCase(),
      headers,
      credentials: "include"
    });
  };
}
