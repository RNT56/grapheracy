import { useQuery } from "@tanstack/react-query";
import type { GraphLensId } from "@graphview/shared-types";
import { agentRunActivityPath, fetchHealth, fetchJson, graphLensScopedPath, graphScopedPath } from "./apiClient";
import type {
  ApiAgentContextBlobContent,
  ApiAgentContextGraph,
  ApiAgentContextSession,
  ApiConnectorAccount,
  ApiConnectorDescriptor,
  ApiConnectorSyncRun,
  ApiConnectorTarget,
  ApiDecisionRecord,
  ApiExtractionLens,
  ApiFeedbackEvent,
  ApiGraph,
  ApiGraphActivityResponse,
  ApiGraphLens,
  ApiGraphSettings,
  ApiGraphView,
  ApiInsights,
  ApiOperationalActionProposal,
  ApiOperationalActionRun,
  ApiOperationalAttentionResponse,
  ApiOperationalOutcome,
  ApiOwner,
  ApiPlanningSession,
  ApiProposal,
  ApiProviderDescriptor,
  ApiReviewActivity,
  ApiReviewDashboard,
  ApiReviewQueue,
  ApiRoutingPolicy,
  ApiSignal,
  ApiSource,
  ApiSourceChunk,
  ApiSourceReviewCoverage,
  WorkspaceMode
} from "./workspaceTypes";

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

export function useWorkspaceQueries({
  workspaceMode,
  selectedGraphId,
  selectedGraphLensId,
  searchText,
  activeAgentRunId,
  selectedAgentContextSessionId,
  selectedAgentContextArtifactId,
  selectedSourceId,
  showContents
}: WorkspaceQueryOptions) {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: false });
  const graphViews = useQuery({
    queryKey: ["graphs"],
    queryFn: () => fetchJson<ApiGraphView[]>("/graphs"),
    retry: false
  });
  const graph = useQuery({
    queryKey: ["graph", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<ApiGraph>(graphLensScopedPath("/graph", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const sources = useQuery({
    queryKey: ["sources", selectedGraphId, searchText],
    queryFn: () =>
      fetchJson<{ sources: ApiSource[] }>(
        graphScopedPath(`/sources${searchText ? `?q=${encodeURIComponent(searchText)}` : ""}`, selectedGraphId)
      ),
    retry: false
  });
  const proposals = useQuery({
    queryKey: ["proposals", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<{ proposals: ApiProposal[] }>(graphLensScopedPath("/proposals", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const reviewQueue = useQuery({
    queryKey: ["review-queue", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<ApiReviewQueue>(graphLensScopedPath("/review-queue?limit=6", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const reviewDashboard = useQuery({
    queryKey: ["review-dashboard", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<ApiReviewDashboard>(graphLensScopedPath("/review-dashboard", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const reviewActivity = useQuery({
    queryKey: ["review-activity", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<ApiReviewActivity>(graphLensScopedPath("/review-activity?limit=4", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const graphActivity = useQuery({
    queryKey: ["graph-activity", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<ApiGraphActivityResponse>(graphLensScopedPath("/graph/activity?limit=16", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const signals = useQuery({
    queryKey: ["signals", selectedGraphId],
    queryFn: () => fetchJson<{ signals: ApiSignal[] }>("/signals?limit=8"),
    retry: false
  });
  const observations = useQuery({
    queryKey: ["observations", selectedGraphId],
    queryFn: () => fetchJson<{ observations: unknown[] }>("/observations?limit=8"),
    retry: false
  });
  const alerts = useQuery({
    queryKey: ["alerts", selectedGraphId],
    queryFn: () => fetchJson<{ alerts: unknown[] }>("/alerts?limit=8"),
    retry: false
  });
  const operationalAttention = useQuery({
    queryKey: ["attention", selectedGraphId],
    queryFn: () => fetchJson<ApiOperationalAttentionResponse>("/attention?limit=8"),
    retry: false
  });
  const owners = useQuery({
    queryKey: ["owners"],
    queryFn: () => fetchJson<{ owners: ApiOwner[] }>("/owners?limit=20"),
    retry: false
  });
  const routingPolicies = useQuery({
    queryKey: ["routing-policies"],
    queryFn: () => fetchJson<{ routing_policies: ApiRoutingPolicy[] }>("/routing-policies?limit=20"),
    retry: false
  });
  const decisionRecords = useQuery({
    queryKey: ["decision-records", selectedGraphId],
    queryFn: () => fetchJson<{ decision_records: ApiDecisionRecord[] }>("/decision-records?limit=8"),
    retry: false
  });
  const operationalActionProposals = useQuery({
    queryKey: ["action-proposals", selectedGraphId],
    queryFn: () => fetchJson<{ action_proposals: ApiOperationalActionProposal[] }>("/action-proposals?limit=8"),
    retry: false
  });
  const operationalActionRuns = useQuery({
    queryKey: ["action-runs", selectedGraphId],
    queryFn: () => fetchJson<{ action_runs: ApiOperationalActionRun[] }>("/action-runs?limit=8"),
    retry: false
  });
  const outcomes = useQuery({
    queryKey: ["outcomes", selectedGraphId],
    queryFn: () => fetchJson<{ outcomes: ApiOperationalOutcome[] }>("/outcomes?limit=8"),
    retry: false
  });
  const feedbackEvents = useQuery({
    queryKey: ["feedback-events", selectedGraphId],
    queryFn: () => fetchJson<{ feedback_events: ApiFeedbackEvent[] }>("/feedback-events?limit=8"),
    retry: false
  });
  const agentRunActivity = useQuery({
    queryKey: ["agent-run-activity", activeAgentRunId],
    queryFn: () => fetchJson<ApiGraphActivityResponse>(agentRunActivityPath(activeAgentRunId ?? "")),
    enabled: Boolean(activeAgentRunId),
    retry: false
  });
  const sourceReviewCoverage = useQuery({
    queryKey: ["review-sources", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<ApiSourceReviewCoverage>(graphLensScopedPath("/review-sources?limit=4", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const reviewDecisions = useQuery({
    queryKey: ["review-decisions", selectedGraphId],
    queryFn: () => fetchJson<{ review_decisions: unknown[] }>(graphScopedPath("/review-decisions", selectedGraphId)),
    retry: false
  });
  const insights = useQuery({
    queryKey: ["insights", selectedGraphId, selectedGraphLensId],
    queryFn: () => fetchJson<ApiInsights>(graphLensScopedPath("/insights", selectedGraphId, selectedGraphLensId)),
    retry: false
  });
  const extractionLenses = useQuery({
    queryKey: ["extraction-lenses"],
    queryFn: () => fetchJson<{ extraction_lenses: ApiExtractionLens[] }>("/extraction-lenses"),
    retry: false
  });
  const graphLenses = useQuery({
    queryKey: ["graph-lenses"],
    queryFn: () => fetchJson<{ graph_lenses: ApiGraphLens[] }>("/graph-lenses"),
    retry: false
  });
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
  const planningSessions = useQuery({
    queryKey: ["planning-sessions", selectedGraphId],
    queryFn: () => fetchJson<{ planning_sessions: ApiPlanningSession[] }>(graphScopedPath("/planning-sessions", selectedGraphId)),
    retry: false
  });
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
  const selectedSourceChunks = useQuery({
    queryKey: ["source-chunks", selectedGraphId, selectedSourceId],
    queryFn: () =>
      fetchJson<{ source_chunks: ApiSourceChunk[] }>(
        graphScopedPath(`/source-chunks?source_id=${encodeURIComponent(selectedSourceId ?? "")}`, selectedGraphId)
      ),
    enabled: Boolean(selectedSourceId),
    retry: false
  });
  const contentExpansionChunks = useQuery({
    queryKey: ["source-chunks", selectedGraphId, "content-expansion"],
    queryFn: () => fetchJson<{ source_chunks: ApiSourceChunk[] }>(graphScopedPath("/source-chunks", selectedGraphId)),
    enabled: showContents && !selectedSourceId,
    retry: false
  });


  return {
    health,
    graphViews,
    graph,
    sources,
    proposals,
    reviewQueue,
    reviewDashboard,
    reviewActivity,
    graphActivity,
    signals,
    observations,
    alerts,
    operationalAttention,
    owners,
    routingPolicies,
    decisionRecords,
    operationalActionProposals,
    operationalActionRuns,
    outcomes,
    feedbackEvents,
    agentRunActivity,
    sourceReviewCoverage,
    reviewDecisions,
    insights,
    extractionLenses,
    graphLenses,
    connectors,
    connectorAccounts,
    connectorTargets,
    connectorSyncRuns,
    graphSettings,
    providers,
    planningSessions,
    agentContextSessions,
    agentContextGraph,
    agentContextArtifactContent,
    selectedSourceChunks,
    contentExpansionChunks
  };
}
