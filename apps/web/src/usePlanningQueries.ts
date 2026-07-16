import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentRunActivityPath, fetchJson, graphScopedPath, waitForJob } from "./apiClient";
import type {
  ApiAgentActionProposal,
  ApiGraphActivityResponse,
  ApiGraphQueryAnswer,
  ApiGraphResearchResult,
  ApiPlanningSession,
  ApiProviderId
} from "./workspaceTypes";

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

export function usePlanningMutations({
  selectedGraphId,
  selectedGraphLensId,
  activeProviderId,
  selectedGraphNodeId,
  selectedSourceId,
  planningGoal,
  planningMessage,
  selectedSession,
  onSelectSession,
  onClearMessage,
  onAnswer,
  onResearch,
  onGraphChanged
}: {
  selectedGraphId: string;
  selectedGraphLensId: string;
  activeProviderId: ApiProviderId;
  selectedGraphNodeId?: string;
  selectedSourceId?: string;
  planningGoal: string;
  planningMessage: string;
  selectedSession?: ApiPlanningSession;
  onSelectSession: (sessionId: string) => void;
  onClearMessage: () => void;
  onAnswer: (answer: ApiGraphQueryAnswer) => void;
  onResearch: (result: ApiGraphResearchResult) => void;
  onGraphChanged: () => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const createPlanningSession = useMutation({
    mutationFn: () =>
      fetchJson<ApiPlanningSession>(graphScopedPath("/planning-sessions", selectedGraphId), {
        method: "POST",
        body: JSON.stringify({
          title: planningGoal.split(/[.?!]/)[0]?.slice(0, 96) || "AI planning session",
          goal: planningGoal,
          graph_id: selectedGraphId,
          lens: selectedGraphLensId,
          provider: activeProviderId
        })
      }),
    onSuccess: async (session) => {
      onSelectSession(session.id);
      await queryClient.invalidateQueries({ queryKey: ["planning-sessions"] });
    }
  });
  const sendPlanningMessage = useMutation({
    mutationFn: async () => {
      const session = selectedSession ?? await createPlanningSession.mutateAsync();
      const job = await fetchJson<{ id: string }>(`/ai/planning-sessions/${encodeURIComponent(session.id)}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: planningMessage, provider: activeProviderId })
      });
      return waitForJob<ApiPlanningSession>(job.id);
    },
    onSuccess: async (session) => {
      onSelectSession(session.id);
      onClearMessage();
      await queryClient.invalidateQueries({ queryKey: ["planning-sessions"] });
    }
  });
  const askGraphAgent = useMutation({
    mutationFn: async (question: string) => {
      const job = await fetchJson<{ id: string }>("/ai/query", {
        method: "POST",
        body: JSON.stringify({
          question,
          graph_id: selectedGraphId,
          lens: selectedGraphLensId,
          node_id: selectedGraphNodeId,
          source_id: selectedSourceId,
          provider: activeProviderId
        })
      });
      return waitForJob<ApiGraphQueryAnswer>(job.id);
    },
    onSuccess: onAnswer
  });
  const runGraphResearch = useMutation({
    mutationFn: async (query: string) => {
      const job = await fetchJson<{ id: string }>("/ai/research", {
        method: "POST",
        body: JSON.stringify({
          query,
          graph_id: selectedGraphId,
          lens: selectedGraphLensId,
          source_policy: "mixed",
          provider: activeProviderId
        })
      });
      return waitForJob<ApiGraphResearchResult>(job.id);
    },
    onSuccess: async (result) => {
      onResearch(result);
      await onGraphChanged();
    }
  });
  const approveAgentAction = useMutation({
    mutationFn: (action: ApiAgentActionProposal) =>
      fetchJson<ApiAgentActionProposal>(`/agent-runs/${encodeURIComponent(action.agent_run_id)}/approve-action`, {
        method: "POST",
        body: JSON.stringify({
          action_proposal_id: action.id,
          decision: "approve",
          rationale: "Approved from Graphview AI review."
        })
      }),
    onSuccess: onGraphChanged
  });
  return { createPlanningSession, sendPlanningMessage, askGraphAgent, runGraphResearch, approveAgentAction };
}
