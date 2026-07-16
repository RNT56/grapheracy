import { useMutation, useQueryClient } from "@tanstack/react-query";

import { fetchJson } from "./apiClient";
import type {
  ApiActionCredentialKind,
  ApiGraphSettings,
  ApiProviderDescriptor,
  ApiProviderId
} from "./workspaceTypes";

export function useSettingsMutations({
  activeProviderId,
  selectedProviderId,
  providerApiKey,
  llmEnabled,
  autoCommitThreshold,
  onClearProviderApiKey
}: {
  activeProviderId: ApiProviderId;
  selectedProviderId: ApiProviderId;
  providerApiKey: string;
  llmEnabled: boolean;
  autoCommitThreshold: number;
  onClearProviderApiKey: () => void;
}) {
  const queryClient = useQueryClient();
  const invalidateSettings = () => queryClient.invalidateQueries({ queryKey: ["graph-settings"] });
  const updateGraphSettings = useMutation({
    mutationFn: () =>
      fetchJson<ApiGraphSettings>("/graph/settings", {
        method: "PATCH",
        body: JSON.stringify({
          llm_enabled: llmEnabled,
          auto_commit_threshold: autoCommitThreshold,
          settings: { ai_default_provider: activeProviderId }
        })
      }),
    onSuccess: invalidateSettings
  });
  const invalidateProviderSettings = async () => {
    onClearProviderApiKey();
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["providers"] }),
      queryClient.invalidateQueries({ queryKey: ["graph-settings"] })
    ]);
  };
  const saveProviderCredential = useMutation({
    mutationFn: () =>
      fetchJson<{ providers: ApiProviderDescriptor[] }>(`/providers/${encodeURIComponent(selectedProviderId)}/credentials`, {
        method: "PATCH",
        body: JSON.stringify({ api_key: providerApiKey.trim(), make_default: true })
      }),
    onSuccess: invalidateProviderSettings
  });
  const clearProviderCredential = useMutation({
    mutationFn: () =>
      fetchJson<{ providers: ApiProviderDescriptor[] }>(`/providers/${encodeURIComponent(selectedProviderId)}/credentials`, {
        method: "DELETE"
      }),
    onSuccess: invalidateProviderSettings
  });
  const saveActionCredential = useMutation({
    mutationFn: ({ kind, credentials }: { kind: ApiActionCredentialKind; credentials: Record<string, string> }) =>
      fetchJson(`/action-credentials/${encodeURIComponent(kind)}`, {
        method: "PUT",
        body: JSON.stringify({ credentials })
      }),
    onSuccess: invalidateSettings
  });
  const clearActionCredential = useMutation({
    mutationFn: (kind: ApiActionCredentialKind) =>
      fetchJson(`/action-credentials/${encodeURIComponent(kind)}`, { method: "DELETE" }),
    onSuccess: invalidateSettings
  });
  return {
    updateGraphSettings,
    saveProviderCredential,
    clearProviderCredential,
    saveActionCredential,
    clearActionCredential
  };
}
