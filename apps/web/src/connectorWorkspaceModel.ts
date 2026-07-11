import type {
  ApiConnectorDescriptor,
  ApiConnectorTarget,
  ApiProviderId
} from "./workspaceTypes";

export const fallbackConnectors: ApiConnectorDescriptor[] = [
  { kind: "upload", label: "Upload", summary: "Import local text, markdown, JSON, CSV, PDF text, and office exports.", target_types: ["upload", "file"], requires_account: false },
  { kind: "url", label: "URL", summary: "Fetch webpages and extract headings, body text, and links.", target_types: ["url"], requires_account: false },
  { kind: "repository", label: "Repository", summary: "Extract repository files, imports, dependencies, and symbols.", target_types: ["repository"], requires_account: false },
  { kind: "google-workspace", label: "Google Workspace", summary: "Sync Drive, Docs, Sheets, Slides, PDFs, and office exports.", target_types: ["folder", "file"], requires_account: true },
  { kind: "notion", label: "Notion", summary: "Sync pages, databases, blocks, mentions, and relations.", target_types: ["page", "database"], requires_account: true }
];

export function asApiProviderId(value: unknown): ApiProviderId | undefined {
  if (value === "graphview-local" || value === "openai" || value === "anthropic" || value === "gemini") {
    return value;
  }
  return undefined;
}

export function connectorLabel(kind: ApiConnectorDescriptor["kind"]) {
  return fallbackConnectors.find((connector) => connector.kind === kind)?.label ?? kind;
}

export function targetTypeForConnector(kind: ApiConnectorDescriptor["kind"]): ApiConnectorTarget["target_type"] {
  if (kind === "url") return "url";
  if (kind === "repository") return "repository";
  if (kind === "google-workspace") return "folder";
  if (kind === "notion") return "page";
  return "upload";
}

export function connectorSyncSettings(
  kind: ApiConnectorDescriptor["kind"],
  title: string,
  content: string,
  remoteId: string,
  llmEnabled: boolean,
  autoCommitThreshold: number
) {
  const base = { llm_enabled: llmEnabled, auto_commit_threshold: autoCommitThreshold };
  if (kind === "url") return { ...base, uri: remoteId, content, title };
  if (kind === "repository") return { ...base, content, path: remoteId };
  if (kind === "google-workspace") return { ...base, documents: [{ id: remoteId, title, content }] };
  if (kind === "notion") return { ...base, pages: [{ id: remoteId, title, content }] };
  return { ...base, files: [{ id: remoteId, title, content }] };
}
