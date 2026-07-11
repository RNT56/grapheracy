import { useMutation, useQueryClient } from "@tanstack/react-query";

import { fetchJson } from "./apiClient";
import type { ApiActionCredentialKind } from "./workspaceTypes";

export function useActionCredentialMutations() {
  const queryClient = useQueryClient();
  const invalidateSettings = () => queryClient.invalidateQueries({ queryKey: ["graph-settings"] });
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
  return { saveActionCredential, clearActionCredential };
}
