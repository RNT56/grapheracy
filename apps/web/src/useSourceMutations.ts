import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { SourceKind } from "@graphview/shared-types";

import { fetchJson, graphScopedPath } from "./apiClient";
import { connectorLabel, connectorSyncSettings, targetTypeForConnector } from "./connectorWorkspaceModel";
import type {
  ApiConnectorAccount,
  ApiConnectorDescriptor,
  ApiConnectorTarget,
  ApiSource
} from "./workspaceTypes";

export function useSourceMutations({
  selectedGraphId,
  sourceKind,
  extractionLensIds,
  connectorKind,
  connectorTitle,
  connectorRemoteId,
  connectorContent,
  connectorAccounts,
  llmEnabled,
  autoCommitThreshold,
  onSourceCreated,
  onIngested,
  onGraphChanged
}: {
  selectedGraphId: string;
  sourceKind: SourceKind;
  extractionLensIds: string[];
  connectorKind: ApiConnectorDescriptor["kind"];
  connectorTitle: string;
  connectorRemoteId: string;
  connectorContent: string;
  connectorAccounts: ApiConnectorAccount[];
  llmEnabled: boolean;
  autoCommitThreshold: number;
  onSourceCreated: () => void;
  onIngested: () => void;
  onGraphChanged: () => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const invalidateSourceViews = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["sources"] }),
    queryClient.invalidateQueries({ queryKey: ["review-queue"] }),
    queryClient.invalidateQueries({ queryKey: ["review-dashboard"] }),
    queryClient.invalidateQueries({ queryKey: ["review-sources"] }),
    queryClient.invalidateQueries({ queryKey: ["insights"] }),
    queryClient.invalidateQueries({ queryKey: ["neighborhood"] }),
    queryClient.invalidateQueries({ queryKey: ["path"] })
  ]);
  const createSource = useMutation({
    mutationFn: (title: string) =>
      fetchJson<ApiSource>(graphScopedPath("/sources", selectedGraphId), {
        method: "POST",
        body: JSON.stringify({
          kind: sourceKind,
          title,
          uri: `local://${sourceKind}/${title.toLowerCase().replaceAll(" ", "-")}`
        })
      }),
    onSuccess: async () => {
      await invalidateSourceViews();
      onSourceCreated();
    }
  });
  const ingestText = useMutation({
    mutationFn: (payload: { title: string; content: string }) =>
      fetchJson(graphScopedPath("/ingestion-runs", selectedGraphId), {
        method: "POST",
        body: JSON.stringify({
          kind: sourceKind,
          title: payload.title,
          content: payload.content,
          extraction_lenses: extractionLensIds
        })
      }),
    onSuccess: async () => {
      await Promise.all([invalidateSourceViews(), queryClient.invalidateQueries({ queryKey: ["proposals"] })]);
      onIngested();
    }
  });
  const syncConnector = useMutation({
    mutationFn: async () => {
      const existingAccount = connectorAccounts.find((account) => account.kind === connectorKind);
      const account = existingAccount ?? await fetchJson<ApiConnectorAccount>("/connector-accounts", {
        method: "POST",
        body: JSON.stringify({
          kind: connectorKind,
          display_name: `${connectorLabel(connectorKind)} connector`,
          scopes: connectorKind === "google-workspace"
            ? ["drive.readonly", "documents.readonly"]
            : connectorKind === "notion"
              ? ["read_content"]
              : [],
          settings: {}
        })
      });
      const target = await fetchJson<ApiConnectorTarget>("/connector-targets", {
        method: "POST",
        body: JSON.stringify({
          account_id: account.id,
          target_type: targetTypeForConnector(connectorKind),
          remote_id: connectorRemoteId.trim() || `${connectorKind}-${Date.now()}`,
          title: connectorTitle.trim() || connectorLabel(connectorKind),
          sync_settings: connectorSyncSettings(
            connectorKind,
            connectorTitle,
            connectorContent,
            connectorRemoteId,
            llmEnabled,
            autoCommitThreshold
          )
        })
      });
      return fetchJson("/connector-sync-runs", {
        method: "POST",
        body: JSON.stringify({ target_id: target.id })
      });
    },
    onSuccess: onGraphChanged
  });
  const resyncConnectorTarget = useMutation({
    mutationFn: (targetId: string) =>
      fetchJson("/connector-sync-runs", {
        method: "POST",
        body: JSON.stringify({ target_id: targetId, force: true })
      }),
    onSuccess: onGraphChanged
  });
  return { createSource, ingestText, syncConnector, resyncConnectorTarget };
}
