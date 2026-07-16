import { useQuery } from "@tanstack/react-query";
import type { GraphLensId } from "@graphview/shared-types";
import { fetchHealth } from "./apiClient";
import { useAgentContextQueries } from "./useAgentContextQueries";
import { useAttentionQueries } from "./useAttentionQueries";
import { useConnectorQueries } from "./useConnectorQueries";
import { useGraphQueries } from "./useGraphQueries";
import { usePlanningQueries } from "./usePlanningQueries";
import type { WorkspaceMode } from "./workspaceTypes";

interface WorkspaceQueryOptions {
  workspaceMode: WorkspaceMode;
  selectedGraphId: string;
  selectedGraphLensId: GraphLensId;
  searchText: string;
  activeAgentRunId?: string;
  selectedAgentContextSessionId?: string;
  selectedAgentContextArtifactId?: string;
  selectedSourceId?: string;
  showContents: boolean;
}

export function useWorkspaceQueries(options: WorkspaceQueryOptions) {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: false });
  const graphQueries = useGraphQueries(options);
  const attentionQueries = useAttentionQueries(options.selectedGraphId);
  const connectorQueries = useConnectorQueries();
  const planningQueries = usePlanningQueries(options.selectedGraphId, options.activeAgentRunId);
  const agentContextQueries = useAgentContextQueries(options);

  return {
    health,
    ...graphQueries,
    ...attentionQueries,
    ...connectorQueries,
    ...planningQueries,
    ...agentContextQueries
  };
}
