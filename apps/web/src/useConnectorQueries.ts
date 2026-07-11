import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./apiClient";
import type {
  ApiConnectorAccount, ApiConnectorDescriptor, ApiConnectorSyncRun, ApiConnectorTarget,
  ApiGraphSettings, ApiProviderDescriptor
} from "./workspaceTypes";

export function useConnectorQueries() {
  const connectors = useQuery({
    queryKey: ["connectors"],
    queryFn: () => fetchJson<{ connectors: ApiConnectorDescriptor[] }>("/connectors"),
    retry: false
  });
  const connectorAccounts = useQuery({
    queryKey: ["connector-accounts"],
    queryFn: () => fetchJson<{ connector_accounts: ApiConnectorAccount[] }>("/connector-accounts"),
    retry: false
  });
  const connectorTargets = useQuery({
    queryKey: ["connector-targets"],
    queryFn: () => fetchJson<{ connector_targets: ApiConnectorTarget[] }>("/connector-targets"),
    retry: false
  });
  const connectorSyncRuns = useQuery({
    queryKey: ["connector-sync-runs"],
    queryFn: () => fetchJson<{ connector_sync_runs: ApiConnectorSyncRun[] }>("/connector-sync-runs"),
    retry: false
  });
  const graphSettings = useQuery({
    queryKey: ["graph-settings"],
    queryFn: () => fetchJson<ApiGraphSettings>("/graph/settings"),
    retry: false
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => fetchJson<{ providers: ApiProviderDescriptor[] }>("/providers"),
    retry: false
  });

  return {
    connectors,
    connectorAccounts,
    connectorTargets,
    connectorSyncRuns,
    graphSettings,
    providers
  };
}
