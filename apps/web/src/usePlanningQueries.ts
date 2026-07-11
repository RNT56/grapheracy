import { useQuery } from "@tanstack/react-query";
import { agentRunActivityPath, fetchJson, graphScopedPath } from "./apiClient";
import type { ApiGraphActivityResponse, ApiPlanningSession } from "./workspaceTypes";

export function usePlanningQueries(selectedGraphId: string, activeAgentRunId?: string) {
  const planningSessions = useQuery({
    queryKey: ["planning-sessions", selectedGraphId],
    queryFn: () => fetchJson<{ planning_sessions: ApiPlanningSession[] }>(graphScopedPath("/planning-sessions", selectedGraphId)),
    retry: false
  });
  const agentRunActivity = useQuery({
    queryKey: ["agent-run-activity", activeAgentRunId],
    queryFn: () => fetchJson<ApiGraphActivityResponse>(agentRunActivityPath(activeAgentRunId ?? "")),
    enabled: Boolean(activeAgentRunId),
    retry: false
  });

  return {
    planningSessions,
    agentRunActivity
  };
}
