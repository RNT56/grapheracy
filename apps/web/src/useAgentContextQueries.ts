import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./apiClient";
import type {
  ApiAgentContextBlobContent, ApiAgentContextGraph, ApiAgentContextSession, WorkspaceMode
} from "./workspaceTypes";

export function useAgentContextQueries({
  workspaceMode,
  selectedAgentContextSessionId,
  selectedAgentContextArtifactId
}: {
  workspaceMode: WorkspaceMode;
  selectedAgentContextSessionId?: string;
  selectedAgentContextArtifactId?: string;
}) {
  const agentContextSessions = useQuery({
    queryKey: ["agent-context-sessions"],
    queryFn: () => fetchJson<{ sessions: ApiAgentContextSession[] }>("/agent-context/sessions?limit=25"),
    retry: false,
    refetchInterval: workspaceMode === "context" ? 5000 : false
  });
  const agentContextGraph = useQuery({
    queryKey: ["agent-context-graph", selectedAgentContextSessionId],
    queryFn: () => fetchJson<ApiAgentContextGraph>(`/agent-context/sessions/${encodeURIComponent(selectedAgentContextSessionId ?? "")}/graph`),
    enabled: Boolean(selectedAgentContextSessionId),
    retry: false,
    refetchInterval: workspaceMode === "context" ? 5000 : false
  });
  const agentContextArtifactContent = useQuery({
    queryKey: ["agent-context-artifact-content", selectedAgentContextArtifactId],
    queryFn: () => fetchJson<ApiAgentContextBlobContent>(`/agent-context/artifacts/${encodeURIComponent(selectedAgentContextArtifactId ?? "")}/content`),
    enabled: workspaceMode === "context" && Boolean(selectedAgentContextArtifactId),
    retry: false
  });

  return {
    agentContextSessions,
    agentContextGraph,
    agentContextArtifactContent
  };
}
