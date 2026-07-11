import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";
import { applyGraphLens, deriveGraphActivityEvents } from "@graphview/graph-core";
import {
  NODE_KIND_DEFINITIONS,
  normalizeContentNodeKind,
  type AgentCitation,
  type AgentRun as SharedAgentRun,
  type AgentToolCall as SharedAgentToolCall,
  type ContentNode,
  type ContentNodeKind,
  type ContentNodeId,
  type ExtractionProposal,
  type GraphActivityEvent,
  type ExtractionLensDescriptor,
  type GraphLensDescriptor,
  type GraphLensId,
  type GraphProject,
  type GraphProjectId,
  type ReviewDecision,
  type SemanticEdge,
  type Source,
  type SourceKind
} from "@graphview/shared-types";
import { GraphCanvas, type GraphCanvasEdge, type GraphDimensionMode, type GraphLayoutMode } from "./GraphCanvas";
import { useGraphWorkspaceStore } from "./graphWorkspaceStore";
import { useViewportProjection } from "./useViewportProjection";
import { agentRunActivityPath, apiUrl, fetchHealth, fetchJson, graphLensScopedPath, graphScopedPath, waitForJob } from "./apiClient";
import {
  SETTINGS_PAGES,
  providerCredentialCopy,
  withFallbackProviders,
  type AgentToolKind,
  type ApiAgentActionProposal,
  type ApiAgentCitation,
  type ApiAgentContextArtifact,
  type ApiAgentContextBlobContent,
  type ApiAgentContextEvent,
  type ApiAgentContextGraph,
  type ApiAgentContextSession,
  type ApiAgentRun,
  type ApiAgentToolCall,
  type ApiConnectorAccount,
  type ApiConnectorDescriptor,
  type ApiConnectorSyncRun,
  type ApiConnectorTarget,
  type ApiDecisionRecord,
  type ApiExtractionLens,
  type ApiFeedbackEvent,
  type ApiGraph,
  type ApiGraphActivityEvent,
  type ApiGraphActivityResponse,
  type ApiGraphLens,
  type ApiGraphQueryAnswer,
  type ApiGraphResearchResult,
  type ApiGraphSettings,
  type ApiGraphView,
  type ApiInsights,
  type ApiLineage,
  type ApiNeighborhood,
  type ApiOperationalActionProposal,
  type ApiOperationalActionRun,
  type ApiOperationalAttentionItem,
  type ApiOperationalAttentionResponse,
  type ApiOperationalOutcome,
  type ApiOwner,
  type ApiPath,
  type ApiPlanningMessage,
  type ApiPlanningSession,
  type ApiProposal,
  type ApiProviderDescriptor,
  type ApiProviderId,
  type ApiReviewActivity,
  type ApiReviewDashboard,
  type ApiReviewQueue,
  type ApiRoutingPolicy,
  type ApiSignal,
  type ApiSource,
  type ApiSourceChunk,
  type ApiSourceReviewCoverage,
  type AttentionItem,
  type CaptureAuthority,
  type ContentExpansionRole,
  type ContextPaneTab,
  type GraphViewMode,
  type MobileSection,
  type ReviewWorkItemKind,
  type SettingsPageId,
  type SourceContentBlock,
  type WorkspaceMode
} from "./workspaceTypes";
import {
  demoDefaultSourceText,
  demoGraph,
  demoExtractionLenses,
  demoGraphLenses,
  demoInsights,
  demoLineage,
  demoNeighborhood,
  demoPath,
  demoProposals,
  demoReviewActivity,
  demoReviewDashboard,
  demoReviewQueue,
  demoSourceReviewCoverage,
  demoSources
} from "./demo/ios26SwiftDemoGraph";
import "./styles.css";

const queryClient = new QueryClient();
const GENERAL_GRAPH_VIEW_ID = "project-default";
const NODE_KIND_COMPACT_COUNT = 3;
type NodeKindDefinition = (typeof NODE_KIND_DEFINITIONS)[number];

const NODE_KIND_DEFINITION_BY_ID: ReadonlyMap<ContentNodeKind, NodeKindDefinition> = new Map(
  NODE_KIND_DEFINITIONS.map((definition) => [definition.id, definition])
);

const LENS_SUPPORT_NODE_KINDS: Record<ExtractionLensDescriptor["id"], ContentNodeKind[]> = {
  research: ["topic", "source", "dataset", "person", "team", "organization", "decision", "metric", "product", "feature"],
  engineering: ["api", "system", "component", "service", "task", "source", "markdown", "text", "url"],
  ops: ["ops_document", "document", "workflow", "decision", "requirement", "risk", "team", "organization", "markdown", "text"]
};

const fallbackConnectors: ApiConnectorDescriptor[] = [
  { kind: "upload", label: "Upload", summary: "Import local text, markdown, JSON, CSV, PDF text, and office exports.", target_types: ["upload", "file"], requires_account: false },
  { kind: "url", label: "URL", summary: "Fetch webpages and extract headings, body text, and links.", target_types: ["url"], requires_account: false },
  { kind: "repository", label: "Repository", summary: "Extract repository files, imports, dependencies, and symbols.", target_types: ["repository"], requires_account: false },
  { kind: "google-workspace", label: "Google Workspace", summary: "Sync Drive, Docs, Sheets, Slides, PDFs, and office exports.", target_types: ["folder", "file"], requires_account: true },
  { kind: "notion", label: "Notion", summary: "Sync pages, databases, blocks, mentions, and relations.", target_types: ["page", "database"], requires_account: true }
];


type ContentExpansionAction =
  | { type: "source"; sourceId: string; label: string }
  | { type: "proposal"; proposalId: string; label: string }
  | { type: "planning"; sessionId: string; label: string };

interface ContentExpansionGraph {
  nodes: ContentNode[];
  edges: GraphCanvasEdge[];
  actions: Map<string, ContentExpansionAction>;
  chunkCount: number;
  proposalCount: number;
  planningCount: number;
}

function normalizeSourceKind(value: string | null | undefined): SourceKind {
  if (
    value === "text" ||
    value === "markdown" ||
    value === "url" ||
    value === "pdf" ||
    value === "repository" ||
    value === "ops-document"
  ) {
    return value;
  }
  return "text";
}

function extractionLensIdForSourceKind(kind: SourceKind): ExtractionLensDescriptor["id"] {
  if (kind === "repository") return "engineering";
  if (kind === "ops-document") return "ops";
  return "research";
}

function extractionLensIdForGraphLens(lensId: GraphLensId, sourceKindContext: SourceKind): ExtractionLensDescriptor["id"] {
  return lensId === "all" ? extractionLensIdForSourceKind(sourceKindContext) : lensId;
}

function sourceKindLabel(kind: SourceKind) {
  if (kind === "ops-document") return "Ops document";
  if (kind === "pdf") return "PDF";
  if (kind === "url") return "URL";
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

function uniqueNodeKinds(kinds: ContentNodeKind[]) {
  const seen = new Set<ContentNodeKind>();
  return kinds.filter((kind) => {
    if (seen.has(kind)) return false;
    seen.add(kind);
    return true;
  });
}

function nodeKindDefinitionsForLens(lens: ExtractionLensDescriptor, pinnedKind?: ContentNodeKind) {
  const lensKinds = uniqueNodeKinds([
    ...lens.primaryNodeKinds,
    ...lens.sourceKinds.map(normalizeContentNodeKind),
    ...LENS_SUPPORT_NODE_KINDS[lens.id]
  ]);
  const definitions = lensKinds.flatMap((kind) => {
    const definition = NODE_KIND_DEFINITION_BY_ID.get(kind);
    return definition ? [definition] : [];
  });
  if (!pinnedKind || definitions.some((definition) => definition.id === pinnedKind)) {
    return definitions.length > 0 ? definitions : NODE_KIND_DEFINITIONS.slice(0, NODE_KIND_COMPACT_COUNT);
  }
  const pinnedDefinition = NODE_KIND_DEFINITION_BY_ID.get(pinnedKind);
  return pinnedDefinition ? [pinnedDefinition, ...definitions] : definitions;
}

async function invalidateConnectorAndGraphQueries(graphId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["sources"] }),
    queryClient.invalidateQueries({ queryKey: ["proposals"] }),
    queryClient.invalidateQueries({ queryKey: ["review-queue"] }),
    queryClient.invalidateQueries({ queryKey: ["review-dashboard"] }),
    queryClient.invalidateQueries({ queryKey: ["review-activity"] }),
    queryClient.invalidateQueries({ queryKey: ["graph-activity"] }),
    queryClient.invalidateQueries({ queryKey: ["review-sources"] }),
    queryClient.invalidateQueries({ queryKey: ["review-decisions"] }),
    queryClient.invalidateQueries({ queryKey: ["graph", graphId] }),
    queryClient.invalidateQueries({ queryKey: ["insights"] }),
    queryClient.invalidateQueries({ queryKey: ["neighborhood"] }),
    queryClient.invalidateQueries({ queryKey: ["path"] }),
    queryClient.invalidateQueries({ queryKey: ["connector-accounts"] }),
    queryClient.invalidateQueries({ queryKey: ["connector-targets"] }),
    queryClient.invalidateQueries({ queryKey: ["connector-sync-runs"] }),
    queryClient.invalidateQueries({ queryKey: ["source-chunks"] }),
    queryClient.invalidateQueries({ queryKey: ["signals"] }),
    queryClient.invalidateQueries({ queryKey: ["observations"] }),
    queryClient.invalidateQueries({ queryKey: ["alerts"] }),
    queryClient.invalidateQueries({ queryKey: ["attention"] }),
    queryClient.invalidateQueries({ queryKey: ["owners"] }),
    queryClient.invalidateQueries({ queryKey: ["routing-policies"] }),
    queryClient.invalidateQueries({ queryKey: ["decision-records"] }),
    queryClient.invalidateQueries({ queryKey: ["action-proposals"] }),
    queryClient.invalidateQueries({ queryKey: ["action-runs"] }),
    queryClient.invalidateQueries({ queryKey: ["outcomes"] }),
    queryClient.invalidateQueries({ queryKey: ["feedback-events"] })
  ]);
}

function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const workspaceMode: WorkspaceMode = location.pathname.startsWith("/planning")
    ? "planning"
    : location.pathname.startsWith("/context")
      ? "context"
      : location.pathname.startsWith("/settings")
        ? "settings"
        : "graph";
  const setWorkspaceMode = (mode: WorkspaceMode) => navigate(`/${mode}`);
  useEffect(() => {
    if (location.pathname === "/") navigate("/graph", { replace: true });
  }, [location.pathname, navigate]);
  const [selectedGraphId, setSelectedGraphId] = useState("project-ios26-swift-demo");
  const selectedGraphLensId = useGraphWorkspaceStore((state) => state.selectedGraphLensId);
  const setSelectedGraphLensId = useGraphWorkspaceStore((state) => state.setSelectedGraphLensId);
  const [sourceKind, setSourceKind] = useState<SourceKind>("markdown");
  const [sourceTitle, setSourceTitle] = useState("iOS 26 Swift app blueprint");
  const [ingestionText, setIngestionText] = useState(demoDefaultSourceText);
  const [connectorKind, setConnectorKind] = useState<ApiConnectorDescriptor["kind"]>("upload");
  const [connectorTitle, setConnectorTitle] = useState("Imported knowledge source");
  const [connectorRemoteId, setConnectorRemoteId] = useState("local-upload");
  const [connectorContent, setConnectorContent] = useState("# Architecture\nSwiftUI references https://developer.apple.com/documentation/swiftui");
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [autoCommitThreshold, setAutoCommitThreshold] = useState(0.92);
  const [selectedAiProviderId, setSelectedAiProviderId] = useState<ApiProviderId>("graphview-local");
  const [providerApiKey, setProviderApiKey] = useState("");
  const searchText = useGraphWorkspaceStore((state) => state.searchText);
  const setSearchText = useGraphWorkspaceStore((state) => state.setSearchText);
  const graphLayout = useGraphWorkspaceStore((state) => state.graphLayout);
  const setGraphLayout = useGraphWorkspaceStore((state) => state.setGraphLayout);
  const graphDimension = useGraphWorkspaceStore((state) => state.graphDimension);
  const setGraphDimension = useGraphWorkspaceStore((state) => state.setGraphDimension);
  const graphViewMode = useGraphWorkspaceStore((state) => state.graphViewMode);
  const setGraphViewMode = useGraphWorkspaceStore((state) => state.setGraphViewMode);
  const showContents = useGraphWorkspaceStore((state) => state.showContents);
  const toggleContents = useGraphWorkspaceStore((state) => state.toggleContents);
  const [graphQuery, setGraphQuery] = useState("");
  const fitSequence = useGraphWorkspaceStore((state) => state.fitSequence);
  const fitGraph = useGraphWorkspaceStore((state) => state.fitGraph);
  const viewportZoom = useGraphWorkspaceStore((state) => state.viewportZoom);
  const viewportBounds = useGraphWorkspaceStore((state) => state.viewportBounds);
  const setViewportProjection = useGraphWorkspaceStore((state) => state.setViewportProjection);
  const selectedGraphNodeId = useGraphWorkspaceStore((state) => state.selectedGraphNodeId);
  const setSelectedGraphNodeId = useGraphWorkspaceStore((state) => state.setSelectedGraphNodeId);
  const selectedSourceId = useGraphWorkspaceStore((state) => state.selectedSourceId);
  const setSelectedSourceId = useGraphWorkspaceStore((state) => state.setSelectedSourceId);
  const [outlineCollapsed, setOutlineCollapsed] = useState(true);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [ingestComposerOpen, setIngestComposerOpen] = useState(false);
  const [ingestMode, setIngestMode] = useState<"source" | "connector">("source");
  const [nodeKindExpanded, setNodeKindExpanded] = useState(false);
  const [sourceModalOpen, setSourceModalOpen] = useState(false);
  const [contextPaneTab, setContextPaneTab] = useState<ContextPaneTab>("data");
  const [mobileSection, setMobileSection] = useState<MobileSection>("graph");
  const [contentActionStatus, setContentActionStatus] = useState("");
  const [planningGoal, setPlanningGoal] = useState("Plan an AI-native research graph with review-gated sources, citations, and embedded graph Q&A.");
  const [planningMessage, setPlanningMessage] = useState("What are the main open questions and seed sources?");
  const [selectedPlanningSessionId, setSelectedPlanningSessionId] = useState<string | undefined>();
  const [selectedAgentContextSessionId, setSelectedAgentContextSessionId] = useState<string | undefined>();
  const [selectedAgentContextArtifactId, setSelectedAgentContextArtifactId] = useState<string | undefined>();
  const [aiCommand, setAiCommand] = useState("");
  const [graphAnswer, setGraphAnswer] = useState<ApiGraphQueryAnswer | undefined>();
  const [researchResult, setResearchResult] = useState<ApiGraphResearchResult | undefined>();
  const activeAgentRunId = graphAnswer?.agent_run.id ?? researchResult?.agent_run.id;
  const [citationDrawerOpen, setCitationDrawerOpen] = useState(false);
  const [graphMenuOpen, setGraphMenuOpen] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);
  const inspectorContentRef = useRef<HTMLDivElement>(null);
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

  const extractionLensList = extractionLenses.data?.extraction_lenses.map(normalizeExtractionLens) ?? demoExtractionLenses;
  const graphLensList = graphLenses.data?.graph_lenses.map(normalizeGraphLens) ?? demoGraphLenses;
  const connectorList = connectors.data?.connectors ?? fallbackConnectors;
  const connectorAccountList = connectorAccounts.data?.connector_accounts ?? [];
  const connectorTargetList = connectorTargets.data?.connector_targets ?? [];
  const latestSyncRun = connectorSyncRuns.data?.connector_sync_runs[0];
  const providerList = withFallbackProviders(providers.data?.providers);
  const selectedAiProvider = providerList.find((provider) => provider.id === selectedAiProviderId) ?? providerList[0];
  const activeAiProviderId: ApiProviderId = selectedAiProvider?.enabled ? selectedAiProvider.id : "graphview-local";
  const savedProviderCredentials = graphSettings.data?.settings.ai_provider_credentials as Record<string, { configured?: boolean }> | undefined;
  const selectedProviderHasSavedKey = Boolean(savedProviderCredentials?.[selectedAiProviderId]?.configured);
  const selectedProviderStatus =
    selectedAiProviderId === "graphview-local"
      ? "Local"
      : selectedProviderHasSavedKey
        ? "Saved"
        : selectedAiProvider?.configured
          ? "Env"
          : "Needs key";
  const handleAiProviderChange = (providerId: ApiProviderId) => {
    setSelectedAiProviderId(providerId);
    setProviderApiKey("");
  };
  const planningSessionList = planningSessions.data?.planning_sessions ?? [];
  const agentContextSessionList = agentContextSessions.data?.sessions ?? [];
  const operationalSignals = signals.data?.signals ?? [];
  const operationalObservationCount = observations.data?.observations?.length ?? 0;
  const operationalAlertCount = alerts.data?.alerts?.length ?? 0;
  const operationalAttentionItems = operationalAttention.data?.items ?? [];
  const operationalOwnerList = owners.data?.owners ?? [];
  const routingPolicyList = routingPolicies.data?.routing_policies ?? [];
  const decisionRecordList = decisionRecords.data?.decision_records ?? [];
  const operationalActionProposalList = operationalActionProposals.data?.action_proposals ?? [];
  const operationalActionRunList = operationalActionRuns.data?.action_runs ?? [];
  const operationalOutcomeList = outcomes.data?.outcomes ?? [];
  const feedbackEventList = feedbackEvents.data?.feedback_events ?? [];
  const ownerNameById = new Map(operationalOwnerList.map((owner) => [owner.id, owner.display_name]));
  const openOperationalAttention = operationalAttentionItems.filter((item) => !["resolved", "dismissed"].includes(item.status));
  const slaRiskCount = operationalAttentionItems.filter((item) => ["at_risk", "overdue"].includes(item.sla_status)).length;
  const pendingOperationalActionCount = operationalActionProposalList.filter((item) => ["pending_review", "proposed"].includes(item.status)).length;
  const latestOperationalOutcome = operationalOutcomeList[0];
  const selectedPlanningSession = selectedPlanningSessionId
    ? planningSessionList.find((session) => session.id === selectedPlanningSessionId)
    : planningSessionList[0];
  const selectedGraphLens = graphLensList.find((lens) => lens.id === selectedGraphLensId) ?? demoGraphLenses[0];
  const selectedConnector = connectorList.find((connector) => connector.kind === connectorKind) ?? connectorList[0];
  const offlineDemoGraphView: ApiGraphView = {
    id: demoGraph.project.id,
    project_id: demoGraph.project.id,
    label: demoGraph.project.name,
    description: demoGraph.project.description,
    kind: "project",
    source_ids: demoSources.map((source) => source.id),
    node_count: demoGraph.nodes.length,
    edge_count: demoGraph.edges.length,
    source_count: demoSources.length,
    pending_proposal_count: demoProposals.filter((proposal) => proposal.status === "pending_review").length
  };
  const graphViewList = ensureGeneralGraphView(graphViews.data ?? [], graphViews.data ? undefined : offlineDemoGraphView);
  const selectedGraphView = graphViewList.find((view) => view.id === selectedGraphId);

  useEffect(() => {
    if (graphViewList.length === 0) return;
    if (!graphViewList.some((view) => view.id === selectedGraphId)) {
      setSelectedGraphId(graphViewList[0].id);
    }
  }, [graphViewList, selectedGraphId]);

  useEffect(() => {
    setSelectedGraphNodeId(undefined);
    setSelectedSourceId(undefined);
    setGraphQuery("");
  }, [selectedGraphId, selectedGraphLensId]);

  useEffect(() => {
    if (!planningSessionList.length) {
      setSelectedPlanningSessionId(undefined);
      return;
    }
    if (!selectedPlanningSessionId || !planningSessionList.some((session) => session.id === selectedPlanningSessionId)) {
      setSelectedPlanningSessionId(planningSessionList[0].id);
    }
  }, [planningSessionList, selectedPlanningSessionId]);

  useEffect(() => {
    if (!agentContextSessionList.length) {
      setSelectedAgentContextSessionId(undefined);
      return;
    }
    if (!selectedAgentContextSessionId || !agentContextSessionList.some((session) => session.id === selectedAgentContextSessionId)) {
      setSelectedAgentContextSessionId(agentContextSessionList[0].id);
    }
  }, [agentContextSessionList, selectedAgentContextSessionId]);

  useEffect(() => {
    setSelectedAgentContextArtifactId(undefined);
  }, [selectedAgentContextSessionId]);

  useEffect(() => {
    if (!selectedAgentContextArtifactId || !agentContextGraph.data) return;
    if (!agentContextGraph.data.artifacts.some((artifact) => artifact.id === selectedAgentContextArtifactId)) {
      setSelectedAgentContextArtifactId(undefined);
    }
  }, [agentContextGraph.data, selectedAgentContextArtifactId]);

  useEffect(() => {
    if (workspaceMode !== "context" || !selectedAgentContextSessionId || typeof EventSource === "undefined") return;
    const stream = new EventSource(
      apiUrl(`/agent-context/sessions/${encodeURIComponent(selectedAgentContextSessionId)}/stream?limit=25`)
    );
    const refreshContext = () => {
      queryClient.invalidateQueries({ queryKey: ["agent-context-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["agent-context-graph", selectedAgentContextSessionId] });
      if (selectedAgentContextArtifactId) {
        queryClient.invalidateQueries({ queryKey: ["agent-context-artifact-content", selectedAgentContextArtifactId] });
      }
    };
    stream.addEventListener("agent-context.event", refreshContext);
    stream.onerror = () => {
      stream.close();
    };
    return () => {
      stream.removeEventListener("agent-context.event", refreshContext);
      stream.close();
    };
  }, [selectedAgentContextArtifactId, selectedAgentContextSessionId, workspaceMode]);

  useEffect(() => {
    window.localStorage.setItem("graphview.graphLens", selectedGraphLensId);
    const url = new URL(window.location.href);
    if (selectedGraphLensId === "all") {
      url.searchParams.delete("lens");
    } else {
      url.searchParams.set("lens", selectedGraphLensId);
    }
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, [selectedGraphLensId]);

  useEffect(() => {
    if (!graphSettings.data) return;
    setLlmEnabled(graphSettings.data.llm_enabled);
    setAutoCommitThreshold(graphSettings.data.auto_commit_threshold);
    setSelectedAiProviderId(asApiProviderId(graphSettings.data.settings.ai_default_provider) ?? "graphview-local");
  }, [graphSettings.data]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select")) return;
      const key = event.key.toLowerCase();
      if (key === "f") setGraphLayout("force");
      if (key === "r") setGraphLayout("radial");
      if (key === "a") setGraphLayout("arc");
      if (key === "2") setGraphDimension("2d");
      if (key === "3" && graphLayout !== "arc") setGraphDimension("3d");
      if (key === "c") toggleContents();
      if (key === "/") {
        event.preventDefault();
        document.querySelector<HTMLInputElement>(".dock-search input")?.focus();
      }
      if (key === "escape") {
        setGraphQuery("");
        setSelectedGraphNodeId(undefined);
        setSourceModalOpen(false);
        setIngestComposerOpen(false);
        setGraphMenuOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [graphLayout]);

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
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      await queryClient.invalidateQueries({ queryKey: ["review-dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["review-sources"] });
      await queryClient.invalidateQueries({ queryKey: ["insights"] });
      await queryClient.invalidateQueries({ queryKey: ["neighborhood"] });
      await queryClient.invalidateQueries({ queryKey: ["path"] });
      setSourceTitle("");
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
          extraction_lenses: extractionLensList.map((lens) => lens.id)
        })
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
      await queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      await queryClient.invalidateQueries({ queryKey: ["review-dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["review-sources"] });
      await queryClient.invalidateQueries({ queryKey: ["insights"] });
      await queryClient.invalidateQueries({ queryKey: ["neighborhood"] });
      await queryClient.invalidateQueries({ queryKey: ["path"] });
      setIngestionText("");
    }
  });

  const syncConnector = useMutation({
    mutationFn: async () => {
      const existingAccount = connectorAccountList.find((account) => account.kind === connectorKind);
      const account =
        existingAccount ??
        await fetchJson<ApiConnectorAccount>("/connector-accounts", {
          method: "POST",
          body: JSON.stringify({
            kind: connectorKind,
            display_name: `${connectorLabel(connectorKind)} connector`,
            scopes: connectorKind === "google-workspace" ? ["drive.readonly", "documents.readonly"] : connectorKind === "notion" ? ["read_content"] : [],
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
          sync_settings: connectorSyncSettings(connectorKind, connectorTitle, connectorContent, connectorRemoteId, llmEnabled, autoCommitThreshold)
        })
      });
      return fetchJson("/connector-sync-runs", {
        method: "POST",
        body: JSON.stringify({ target_id: target.id })
      });
    },
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const resyncConnectorTarget = useMutation({
    mutationFn: (targetId: string) =>
      fetchJson("/connector-sync-runs", {
        method: "POST",
        body: JSON.stringify({ target_id: targetId, force: true })
      }),
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const updateGraphSettings = useMutation({
    mutationFn: () =>
      fetchJson<ApiGraphSettings>("/graph/settings", {
        method: "PATCH",
        body: JSON.stringify({
          llm_enabled: llmEnabled,
          auto_commit_threshold: autoCommitThreshold,
          settings: {
            ai_default_provider: activeAiProviderId
          }
        })
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["graph-settings"] });
    }
  });

  const saveProviderCredential = useMutation({
    mutationFn: () =>
      fetchJson<{ providers: ApiProviderDescriptor[] }>(`/providers/${encodeURIComponent(selectedAiProviderId)}/credentials`, {
        method: "PATCH",
        body: JSON.stringify({
          api_key: providerApiKey.trim(),
          make_default: true
        })
      }),
    onSuccess: async () => {
      setProviderApiKey("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["providers"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-settings"] })
      ]);
    }
  });

  const clearProviderCredential = useMutation({
    mutationFn: () =>
      fetchJson<{ providers: ApiProviderDescriptor[] }>(`/providers/${encodeURIComponent(selectedAiProviderId)}/credentials`, {
        method: "DELETE"
      }),
    onSuccess: async () => {
      setProviderApiKey("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["providers"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-settings"] })
      ]);
    }
  });

  const createProposal = useMutation({
    mutationFn: (payload: string | { sourceId: string; label?: string; summary?: string; locator?: string }) => {
      const sourceId = typeof payload === "string" ? payload : payload.sourceId;
      const label = typeof payload === "string" ? "Reviewed concept" : payload.label ?? "Reviewed concept";
      const summary =
        typeof payload === "string"
          ? "Candidate concept created from the Graphview evidence workspace."
          : payload.summary ?? "Candidate concept created from the selected evidence passage.";
      const locator = typeof payload === "string" ? "web shell" : payload.locator ?? "evidence reader";
      return fetchJson<ApiProposal>("/proposals", {
        method: "POST",
        body: JSON.stringify({
          source_id: sourceId,
          kind: "content_node",
          confidence: 0.82,
          locator,
          proposed_value: {
            label,
            kind: "concept",
            summary
          }
        })
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
      await queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      await queryClient.invalidateQueries({ queryKey: ["review-dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["review-activity"] });
      await queryClient.invalidateQueries({ queryKey: ["graph-activity"] });
      await queryClient.invalidateQueries({ queryKey: ["review-sources"] });
      await queryClient.invalidateQueries({ queryKey: ["review-decisions"] });
      await queryClient.invalidateQueries({ queryKey: ["insights"] });
      await queryClient.invalidateQueries({ queryKey: ["neighborhood"] });
      await queryClient.invalidateQueries({ queryKey: ["path"] });
    }
  });

  const reviewProposal = useMutation({
    mutationFn: (payload: { proposalId: string; decision: "accept" | "reject" | "edit" | "defer"; rationale?: string }) =>
      fetchJson("/review-decisions", {
        method: "POST",
        body: JSON.stringify({
          proposal_id: payload.proposalId,
          decision: payload.decision,
          rationale: payload.rationale ?? `${payload.decision} from Graphview review queue`
        })
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
      await queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      await queryClient.invalidateQueries({ queryKey: ["review-dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["review-activity"] });
      await queryClient.invalidateQueries({ queryKey: ["graph-activity"] });
      await queryClient.invalidateQueries({ queryKey: ["review-sources"] });
      await queryClient.invalidateQueries({ queryKey: ["review-decisions"] });
      await queryClient.invalidateQueries({ queryKey: ["graph"] });
      await queryClient.invalidateQueries({ queryKey: ["insights"] });
      await queryClient.invalidateQueries({ queryKey: ["neighborhood"] });
      await queryClient.invalidateQueries({ queryKey: ["path"] });
    }
  });

  const createPlanningSession = useMutation({
    mutationFn: () =>
      fetchJson<ApiPlanningSession>(graphScopedPath("/planning-sessions", selectedGraphId), {
        method: "POST",
        body: JSON.stringify({
          title: planningGoal.split(/[.?!]/)[0]?.slice(0, 96) || "AI planning session",
          goal: planningGoal,
          graph_id: selectedGraphId,
          lens: selectedGraphLensId,
          provider: activeAiProviderId
        })
      }),
    onSuccess: async (session) => {
      setSelectedPlanningSessionId(session.id);
      await queryClient.invalidateQueries({ queryKey: ["planning-sessions"] });
    }
  });

  const sendPlanningMessage = useMutation({
    mutationFn: async () => {
      const session = selectedPlanningSession ?? await createPlanningSession.mutateAsync();
      const job = await fetchJson<{ id: string }>(`/ai/planning-sessions/${encodeURIComponent(session.id)}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: planningMessage, provider: activeAiProviderId })
      });
      return waitForJob<ApiPlanningSession>(job.id);
    },
    onSuccess: async (session) => {
      setSelectedPlanningSessionId(session.id);
      setPlanningMessage("");
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
          provider: activeAiProviderId
        })
      });
      return waitForJob<ApiGraphQueryAnswer>(job.id);
    },
    onSuccess: (answer) => {
      setGraphAnswer(answer);
      setCitationDrawerOpen(true);
    }
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
          provider: activeAiProviderId
        })
      });
      return waitForJob<ApiGraphResearchResult>(job.id);
    },
    onSuccess: async (result) => {
      setResearchResult(result);
      setCitationDrawerOpen(true);
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const approveAgentAction = useMutation({
    mutationFn: (action: ApiAgentActionProposal) =>
      fetchJson<ApiAgentActionProposal>(`/agent-runs/${encodeURIComponent(action.agent_run_id)}/approve-action`, {
        method: "POST",
        body: JSON.stringify({ action_proposal_id: action.id, decision: "approve", rationale: "Approved from Graphview AI review." })
      }),
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const createOperationalSignal = useMutation({
    mutationFn: () => {
      const candidateSource = selectedSourceId ?? sources.data?.sources[0]?.id;
      return fetchJson<ApiSignal>("/signals", {
        method: "POST",
        body: JSON.stringify({
          kind: "source_changed",
          severity: "medium",
          source_kind: "manual",
          source_id: candidateSource,
          title: candidateSource ? "Source needs attention" : "Graph workspace signal",
          summary: candidateSource
            ? "A graph source was flagged from the Attention workspace for owner routing."
            : "The graph workspace was manually flagged for attention routing.",
          payload: {
            graph_id: selectedGraphId,
            lens: selectedGraphLensId,
            selected_source_id: candidateSource
          }
        })
      });
    },
    onSuccess: async () => {
      setGraphViewMode("attention");
      setContextPaneTab("review");
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const createOperationalDecision = useMutation({
    mutationFn: (item: ApiOperationalAttentionItem) =>
      fetchJson<ApiDecisionRecord>("/decision-records", {
        method: "POST",
        body: JSON.stringify({
          attention_item_id: item.id,
          alert_id: item.alert_id,
          decision: "approve",
          rationale: "Approved from the graph-centered Attention loop."
        })
      }),
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const createOperationalAction = useMutation({
    mutationFn: (item: ApiOperationalAttentionItem) => {
      const actionType =
        item.suggested_actions.find((action) => action !== "mark_source_stale" || Boolean(item.source_id)) ??
        (item.source_id ? "mark_source_stale" : "create_notification");
      return fetchJson<ApiOperationalActionProposal>("/action-proposals", {
        method: "POST",
        body: JSON.stringify({
          decision_record_id: item.decision_record_id,
          alert_id: item.alert_id,
          attention_item_id: item.id,
          action_type: actionType,
          title: actionType === "mark_source_stale" ? "Mark source stale" : "Notify owner",
          summary:
            actionType === "mark_source_stale"
              ? "Flag the linked source as stale until it is refreshed."
              : "Notify the responsible owner that the graph needs attention.",
          payload:
            actionType === "mark_source_stale"
              ? { source_id: item.source_id }
              : { target: item.owner_id ?? "graph-owner", attention_item_id: item.id }
        })
      });
    },
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const approveOperationalAction = useMutation({
    mutationFn: (action: ApiOperationalActionProposal) =>
      fetchJson<ApiOperationalActionProposal>(`/action-proposals/${encodeURIComponent(action.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({ rationale: "Approved from the graph-centered Attention loop." })
      }),
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const runOperationalAction = useMutation({
    mutationFn: (action: ApiOperationalActionProposal) =>
      fetchJson<ApiOperationalActionRun>("/action-runs", {
        method: "POST",
        body: JSON.stringify({ action_proposal_id: action.id })
      }),
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const recordOperationalOutcome = useMutation({
    mutationFn: (run: ApiOperationalActionRun) => {
      const action = operationalActionProposalList.find((proposal) => proposal.id === run.action_proposal_id);
      return fetchJson<ApiOperationalOutcome>(`/action-runs/${encodeURIComponent(run.id)}/outcome`, {
        method: "POST",
        body: JSON.stringify({
          attention_item_id: action?.attention_item_id,
          status: run.status === "succeeded" ? "resolved" : "failed",
          title: run.status === "succeeded" ? "Action outcome resolved" : "Action outcome failed",
          summary:
            run.status === "succeeded"
              ? "The approved operational action completed and the attention item can be resolved."
              : "The approved operational action failed and needs follow-up.",
          result: {
            action_run_id: run.id,
            action_type: run.action_type,
            target: run.target
          }
        })
      });
    },
    onSuccess: async () => {
      await invalidateConnectorAndGraphQueries(selectedGraphId);
    }
  });

  const usingDemoGraph = !graph.data;
  const rawGraphData = usingDemoGraph ? demoGraph : normalizeGraph(graph.data);
  const demoLensPlan = useMemo(
    () => (usingDemoGraph ? applyGraphLens(rawGraphData, selectedGraphLensId) : undefined),
    [rawGraphData, selectedGraphLensId, usingDemoGraph]
  );
  const graphData = usingDemoGraph && demoLensPlan
    ? { ...rawGraphData, nodes: demoLensPlan.nodes, edges: demoLensPlan.edges }
    : rawGraphData;
  const effectiveInsights = usingDemoGraph ? demoInsights : insights.data;
  const effectiveReviewDashboard = usingDemoGraph ? demoReviewDashboard : reviewDashboard.data;
  const effectiveReviewQueue: ApiReviewQueue | undefined = usingDemoGraph ? demoReviewQueue as ApiReviewQueue : reviewQueue.data;
  const effectiveReviewActivity = usingDemoGraph ? demoReviewActivity : reviewActivity.data;
  const effectiveSourceReviewCoverage = usingDemoGraph ? demoSourceReviewCoverage : sourceReviewCoverage.data;
  const neighborhoodTargetId = graphData.nodes[0]?.id ?? effectiveInsights?.top_nodes[0]?.id ?? null;
  const pathSourceId = graphData.nodes[0]?.id ?? effectiveInsights?.top_nodes[0]?.id ?? null;
  const pathTargetId =
    graphData.nodes.find((node) => node.id !== pathSourceId)?.id ??
    effectiveInsights?.top_nodes.find((node) => node.id !== pathSourceId)?.id ??
    null;
  const lineageTarget = graphData.edges[0]
    ? { kind: "edge", id: graphData.edges[0].id }
    : graphData.nodes[0]
      ? { kind: "node", id: graphData.nodes[0].id }
      : null;
  const lineage = useQuery({
    queryKey: ["lineage", selectedGraphId, selectedGraphLensId, lineageTarget?.kind, lineageTarget?.id],
    queryFn: () => {
      if (!lineageTarget) throw new Error("No lineage target");
      return fetchJson<ApiLineage>(graphScopedPath(`/lineage/${lineageTarget.kind}/${lineageTarget.id}`, selectedGraphId));
    },
    enabled: !usingDemoGraph && Boolean(lineageTarget),
    retry: false
  });
  const neighborhood = useQuery({
    queryKey: ["neighborhood", selectedGraphId, selectedGraphLensId, neighborhoodTargetId],
    queryFn: () => {
      if (!neighborhoodTargetId) throw new Error("No neighborhood target");
      return fetchJson<ApiNeighborhood>(
        graphLensScopedPath(`/graph/neighborhood/${encodeURIComponent(neighborhoodTargetId)}?depth=1&limit=12`, selectedGraphId, selectedGraphLensId)
      );
    },
    enabled: !usingDemoGraph && Boolean(neighborhoodTargetId),
    retry: false
  });
  const path = useQuery({
    queryKey: ["path", selectedGraphId, selectedGraphLensId, pathSourceId, pathTargetId],
    queryFn: () => {
      if (!pathSourceId || !pathTargetId) throw new Error("No path target pair");
      const params = new URLSearchParams({
        source_node_id: pathSourceId,
        target_node_id: pathTargetId,
        max_depth: "4"
      });
      return fetchJson<ApiPath>(graphLensScopedPath(`/graph/path?${params.toString()}`, selectedGraphId, selectedGraphLensId));
    },
    enabled: !usingDemoGraph && Boolean(pathSourceId && pathTargetId && pathSourceId !== pathTargetId),
    retry: false
  });
  const effectiveLineage = usingDemoGraph ? demoLineage : lineage.data;
  const effectiveNeighborhood = usingDemoGraph ? demoNeighborhood : neighborhood.data;
  const effectivePath = usingDemoGraph ? demoPath : path.data;
  const sourceList = usingDemoGraph ? demoSources : sources.data?.sources ?? [];
  const selectedSource = selectedSourceId ? sourceList.find((source) => source.id === selectedSourceId) : undefined;
  const sourceChunks = selectedSourceChunks.data?.source_chunks ?? [];
  const proposalList = usingDemoGraph ? demoProposals : proposals.data?.proposals ?? [];
  const pendingContentNode = proposalList.find(
    (proposal) => proposal.status === "pending_review" && proposal.kind === "content_node"
  );
  const pendingProposal = pendingContentNode ?? proposalList.find((proposal) => proposal.status === "pending_review");
  const pendingRelationshipCount = proposalList.filter(
    (proposal) => proposal.status === "pending_review" && proposal.kind === "semantic_edge"
  ).length;
  const topSourceReview = effectiveSourceReviewCoverage?.sources[0];
  const activeQueueItem = effectiveReviewQueue?.items[0];
  const selectedGraphNode = selectedGraphNodeId
    ? graphData.nodes.find((node) => node.id === selectedGraphNodeId)
    : undefined;
  const activeKind = selectedGraphNode?.kind ?? (selectedSource ? normalizeContentNodeKind(selectedSource.kind) : undefined);
  const activeKindDefinition = activeKind
    ? NODE_KIND_DEFINITIONS.find((definition) => definition.id === activeKind)
    : undefined;
  const kindLibrarySourceKind = normalizeSourceKind(selectedSource?.kind ?? sourceKind);
  const activeExtractionLensId = extractionLensIdForGraphLens(selectedGraphLensId, kindLibrarySourceKind);
  const activeExtractionLens =
    extractionLensList.find((lens) => lens.id === activeExtractionLensId) ??
    demoExtractionLenses.find((lens) => lens.id === activeExtractionLensId) ??
    demoExtractionLenses[0];
  const kindLibraryDefinitions = nodeKindDefinitionsForLens(activeExtractionLens, activeKind);
  const baseNodeKindDefinitions = kindLibraryDefinitions.slice(0, NODE_KIND_COMPACT_COUNT);
  const compactNodeKindDefinitions = activeKindDefinition
    ? baseNodeKindDefinitions.some((definition) => definition.id === activeKindDefinition.id)
      ? baseNodeKindDefinitions
      : [
        activeKindDefinition,
        ...kindLibraryDefinitions.filter((definition) => definition.id !== activeKindDefinition.id)
      ].slice(0, NODE_KIND_COMPACT_COUNT)
    : baseNodeKindDefinitions;
  const displayedNodeKindDefinitions = nodeKindExpanded ? kindLibraryDefinitions : compactNodeKindDefinitions;
  const hiddenNodeKindCount = Math.max(0, kindLibraryDefinitions.length - compactNodeKindDefinitions.length);
  const canExpandNodeKinds = kindLibraryDefinitions.length > compactNodeKindDefinitions.length;
  const kindLibraryTitle = `${activeExtractionLens.label} kinds`;
  const kindLibraryContext =
    selectedGraphLensId === "all" ? `${sourceKindLabel(kindLibrarySourceKind)} context` : "active lens";
  const focusNode =
    selectedGraphNode ??
    graphData.nodes.find((node) => node.id === neighborhoodTargetId) ??
    graphData.nodes[0] ??
    demoGraph.nodes[0];
  const graphNodes = graphData.nodes.length > 0 ? graphData.nodes : demoGraph.nodes;
  const reviewedGraphEdges: GraphCanvasEdge[] = (graphData.edges.length > 0 ? graphData.edges : demoGraph.edges).map((edge) => ({
    ...edge,
    reviewStatus: "accepted"
  }));
  const pendingGraphEdges = proposalList.flatMap((proposal) =>
    proposalToGraphEdge(proposal, graphData.project.id, graphNodes)
  );
  const graphEdges = [...reviewedGraphEdges, ...pendingGraphEdges];
  const outlineSources = effectiveSourceReviewCoverage?.sources ?? sourceList.map((source) => ({
    source,
    status: "no_proposals" as const,
    proposal_count: 0,
    pending_count: 0,
    reviewed_count: 0,
    decision_count: 0,
    accepted_count: 0,
    rejected_count: 0,
    edited_count: 0,
    deferred_count: 0,
    last_reviewed_at: null
  }));
  const focusSourceId = focusNode.provenance[0]?.sourceId as string | undefined;
  const focusSource = focusSourceId ? sourceList.find((source) => source.id === focusSourceId) : undefined;
  const contextSource = selectedGraphNode ? focusSource ?? selectedSource : selectedSource ?? focusSource ?? topSourceReview?.source ?? sourceList[0];
  const contextEdges = graphEdges
    .filter((edge) => edge.sourceNodeId === focusNode.id || edge.targetNodeId === focusNode.id)
    .slice(0, 6);
  const contextNeighborNodes = contextEdges.flatMap((edge) => {
    const neighborId = edge.sourceNodeId === focusNode.id ? edge.targetNodeId : edge.sourceNodeId;
    const neighbor = graphNodes.find((node) => node.id === neighborId);
    return neighbor ? [{ node: neighbor, relation: edge.relation, direction: edge.sourceNodeId === focusNode.id ? "out" : "in" }] : [];
  });
  const contextBlocks =
    contextSource?.id === selectedSourceId && sourceChunks.length > 0
      ? sourceChunks
      : buildContextSourceBlocks(contextSource, focusNode, graphNodes, graphEdges);
  const fanOutSourceChunks = selectedSourceId ? sourceChunks : contentExpansionChunks.data?.source_chunks ?? [];
  const contentExpansion = useMemo(
    () =>
      showContents
        ? buildContentExpansionGraph({
            projectId: graphData.project.id,
            graphNodes,
            graphEdges,
            selectedGraphNode,
            selectedSource,
            contextSource,
            contextBlocks,
            sourceChunks: fanOutSourceChunks,
            sources: sourceList,
            proposals: proposalList,
            reviewActivity: effectiveReviewActivity,
            reviewQueue: effectiveReviewQueue,
            planningSessions: planningSessionList
          })
        : emptyContentExpansionGraph(),
    [
      contextBlocks,
      contextSource,
      effectiveReviewActivity,
      effectiveReviewQueue,
      fanOutSourceChunks,
      graphData.project.id,
      graphEdges,
      graphNodes,
      planningSessionList,
      proposalList,
      selectedGraphNode,
      selectedSource,
      showContents,
      sourceList
    ]
  );
  const contentGraphNodes = showContents ? [...graphNodes, ...contentExpansion.nodes] : graphNodes;
  const contentGraphEdges = showContents ? [...graphEdges, ...contentExpansion.edges] : graphEdges;
  const canvasGraph = useViewportProjection(
    selectedGraphId,
    viewportZoom,
    viewportBounds,
    contentGraphNodes,
    contentGraphEdges,
    fetchJson
  );
  const sourceContentText = buildSourceContentText(contextSource, contextBlocks);
  const contextPulse = selectedGraphNode
    ? "Focus"
    : selectedSource
      ? "Source"
      : pendingProposal
        ? "Review"
        : "Overview";
  const contextStatus = `${contextBlocks.length} blocks / ${contextNeighborNodes.length} related / ${
    effectiveLineage?.proposals.length ?? 0
  } proposals`;
  const activeScopeLabel = selectedGraphNode
    ? focusNode.label
    : contextSource
      ? contextSource.title
      : selectedGraphView?.label ?? graphData.project.name;
  const contextDataMode: GraphViewMode =
    graphViewMode === "review" || graphViewMode === "attention" ? (selectedSource ? "evidence" : "focus") : graphViewMode;
  const graphAgentToolCalls = [
    ...(graphAnswer ? agentRunToolCalls(graphAnswer.agent_run) : []),
    ...(researchResult ? agentRunToolCalls(researchResult.agent_run) : [])
  ].filter(uniqueById);
  const overviewTopNodes = (
    effectiveInsights?.top_nodes ??
    graphNodes.slice(0, 5).map((node) => ({
      id: node.id,
      label: node.label,
      kind: node.kind,
      degree: graphEdges.filter((edge) => edge.sourceNodeId === node.id || edge.targetNodeId === node.id).length
    }))
  ).slice(0, 5);
  const evidenceSources = outlineSources.slice(0, 5);
  const evidenceCitations = [
    ...(graphAnswer?.citations ?? []),
    ...((effectiveReviewQueue?.items ?? []).flatMap((item) => item.citations ?? [])),
    ...((researchResult?.agent_run.action_proposals ?? []).flatMap((action) => action.citations ?? []))
  ].filter(uniqueById).slice(0, 5);
  const canvasCitations = [
    ...(graphAnswer?.citations ?? []),
    ...((effectiveReviewQueue?.items ?? []).flatMap((item) => item.citations ?? [])),
    ...((researchResult?.agent_run.action_proposals ?? []).flatMap((action) => action.citations ?? []))
  ].filter(uniqueById).map(apiCitationToShared);
  const persistedGraphActivity = [
    ...apiGraphActivityEvents(graphActivity.data),
    ...apiGraphActivityEvents(agentRunActivity.data)
  ].filter(uniqueById).map(apiGraphActivityEventToShared);
  const derivedGraphActivity = deriveGraphActivityEvents({
    projectId: graphData.project.id,
    graphId: selectedGraphId,
    sources: sourceList.map(apiSourceToShared),
    proposals: proposalList.map(apiProposalToShared),
    reviewDecisions: (effectiveReviewActivity?.items ?? []).map((item) => apiReviewDecisionToShared(item.decision)),
    agentRuns: [graphAnswer?.agent_run, researchResult?.agent_run].filter((run): run is ApiAgentRun => Boolean(run)).map(apiAgentRunToShared),
    toolCalls: graphAgentToolCalls.map(apiAgentToolCallToShared),
    citations: canvasCitations
  }).slice(0, 16);
  const graphActivityEvents = persistedGraphActivity.length > 0 ? persistedGraphActivity : derivedGraphActivity;
  const evidencePreviewBlocks = contextBlocks.slice(0, 5);
  const attentionItems: AttentionItem[] = [
    openOperationalAttention[0]
      ? {
          id: `operation-${openOperationalAttention[0].id}`,
          title: openOperationalAttention[0].title,
          meta: `${openOperationalAttention[0].severity} / ${openOperationalAttention[0].sla_status.replaceAll("_", " ")}`,
          detail: openOperationalAttention[0].summary,
          tone: "operation",
          actionLabel: "Attention"
        }
      : undefined,
    pendingProposal
      ? {
          id: `proposal-${pendingProposal.id}`,
          title: pendingProposal.proposed_value.label ?? pendingProposal.proposed_value.relation ?? "Pending proposal",
          meta: activeQueueItem?.action.replaceAll("_", " ") ?? "review",
          detail: activeQueueItem?.reason ?? "Review the next graph change before it becomes durable knowledge.",
          tone: "review",
          actionLabel: "Focus"
        }
      : undefined,
    topSourceReview && topSourceReview.pending_count > 0
      ? {
          id: `source-${topSourceReview.source.id}`,
          title: topSourceReview.source.title,
          meta: `${topSourceReview.pending_count} pending`,
          detail: "This source still has proposal work that should be resolved before the graph is trusted.",
          tone: "source",
          actionLabel: "Open source"
        }
      : undefined,
    researchResult
      ? {
          id: `research-${researchResult.research_task.id}`,
          title: researchResult.research_task.query,
          meta: `${researchResult.proposals.length} proposals`,
          detail: `Research is ${researchResult.research_task.status.replaceAll("_", " ")} and ready to inspect with citations.`,
          tone: "research",
          actionLabel: "Citations"
        }
      : undefined,
    latestSyncRun
      ? {
          id: `sync-${latestSyncRun.id}`,
          title: `${latestSyncRun.status} connector sync`,
          meta: `${latestSyncRun.source_count} sources`,
          detail: `${latestSyncRun.proposal_count} proposals, ${latestSyncRun.chunk_count} chunks, ${latestSyncRun.auto_committed_count} auto-committed.`,
          tone: "sync",
          actionLabel: "Details"
        }
      : {
          id: "sync-empty",
          title: "No connector sync yet",
          meta: `${connectorList.length} connectors`,
          detail: "Connect uploads, URLs, repositories, Google Workspace, or Notion when the graph needs fresh source material.",
          tone: "sync",
          actionLabel: "Ingest"
        },
    effectivePath
      ? {
          id: "path-focus",
          title: effectivePath.path_found ? `${effectivePath.distance} hop path` : "No reviewed path",
          meta: `${effectivePath.source_node.label} to ${effectivePath.target_node.label}`,
          detail: "Use path context to understand how two reviewed concepts are connected.",
          tone: "lineage",
          actionLabel: "Trace"
        }
      : undefined
  ].filter((item): item is AttentionItem => Boolean(item));

  const handleSelectGraphNode = (nodeId: ContentNode["id"]) => {
    const expansionAction = contentExpansion.actions.get(nodeId);
    if (expansionAction?.type === "source") {
      const source = sourceList.find((item) => item.id === expansionAction.sourceId);
      if (source) selectSource(source);
      return;
    }
    if (expansionAction?.type === "proposal") {
      setGraphQuery(expansionAction.label);
      setContextPaneTab("review");
      setGraphViewMode("review");
      setMobileSection("review");
      setSelectedGraphNodeId(undefined);
      setInspectorCollapsed(false);
      setIngestComposerOpen(false);
      return;
    }
    if (expansionAction?.type === "planning") {
      setSelectedPlanningSessionId(expansionAction.sessionId);
      setWorkspaceMode("planning");
      setMobileSection("plan");
      return;
    }
    setSelectedGraphNodeId(nodeId);
    setGraphViewMode("focus");
    setContextPaneTab("data");
    setMobileSection("focus");
    const node = graphNodes.find((item) => item.id === nodeId);
    const sourceId = node?.provenance[0]?.sourceId as string | undefined;
    if (sourceId && sourceList.some((source) => source.id === sourceId)) {
      setSelectedSourceId(sourceId);
    }
    setInspectorCollapsed(false);
  };

  const copySourceContent = async () => {
    if (!sourceContentText.trim()) return;
    try {
      await writeClipboardText(sourceContentText);
      setContentActionStatus("Copied");
    } catch {
      setContentActionStatus("Copy unavailable");
    }
  };

  const exportSourceContent = () => {
    const blob = new Blob([sourceContentText], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${slugify(contextSource?.title ?? focusNode.label)}.md`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    setContentActionStatus("Exported");
  };

  const shareSourceContent = async () => {
    const shareNavigator = navigator as Navigator & {
      share?: (data: { title?: string; text?: string; url?: string }) => Promise<void>;
    };
    if (shareNavigator.share) {
      try {
        await shareNavigator.share({
          title: contextSource?.title ?? focusNode.label,
          text: sourceContentText
        });
        setContentActionStatus("Shared");
        return;
      } catch {
        setContentActionStatus("Share cancelled");
        return;
      }
    }
    await copySourceContent();
  };

  const openIngestComposer = () => {
    setIngestComposerOpen(true);
    setIngestMode("source");
    setInspectorCollapsed(false);
    setMobileSection("focus");
    window.requestAnimationFrame(() => {
      inspectorContentRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  const handleAddSource = () => {
    const title = sourceTitle.trim() || defaultTitleForSourceKind(sourceKind, sourceList.length + 1);
    createSource.mutate(title);
    setSourceTitle(title);
    setInspectorCollapsed(false);
    setIngestComposerOpen(false);
  };

  const handleExportGraph = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      project: graphData.project,
      nodes: graphNodes,
      edges: graphEdges,
      sources: sourceList,
      proposals: proposalList
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${graphData.project.name.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "graphview"}-export.json`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const handleImportGraph = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = undefined;
      }
      const imported = parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
      const project = imported.project && typeof imported.project === "object" ? imported.project as Record<string, unknown> : {};
      const title =
        typeof imported.title === "string"
          ? imported.title
          : typeof project.name === "string"
            ? project.name
            : file.name.replace(/\.[^.]+$/, "") || defaultTitleForSourceKind(inferSourceKind(file.name), sourceList.length + 1);
      const content = typeof imported.content === "string" ? imported.content : text;
      setSourceKind(inferSourceKind(file.name));
      setSourceTitle(title);
      setIngestionText(content);
      setInspectorCollapsed(false);
      setIngestComposerOpen(false);
      ingestText.mutate({ title, content });
    } catch (error) {
      setIngestionText(`Import failed: ${error instanceof Error ? error.message : "unknown error"}`);
    } finally {
      event.currentTarget.value = "";
    }
  };

  const selectSource = (source: ApiSource | Source) => {
    setSelectedSourceId(source.id);
    setSelectedGraphNodeId(undefined);
    setGraphViewMode("evidence");
    setContextPaneTab("data");
    setMobileSection("focus");
    setSourceTitle(source.title);
    setGraphQuery(source.title);
    setInspectorCollapsed(false);
    setIngestComposerOpen(false);
  };

  const activateGraphViewMode = (mode: GraphViewMode) => {
    setGraphViewMode(mode);
    if (mode === "overview") {
      setContextPaneTab("data");
      setMobileSection("graph");
      setSelectedGraphNodeId(undefined);
      setGraphQuery("");
      setInspectorCollapsed(false);
      return;
    }
    if (mode === "focus") {
      setContextPaneTab("data");
      setMobileSection("focus");
      setInspectorCollapsed(false);
      return;
    }
    if (mode === "evidence") {
      setContextPaneTab("data");
      setMobileSection("focus");
      setInspectorCollapsed(false);
      return;
    }
    setContextPaneTab("review");
    setMobileSection("review");
    setInspectorCollapsed(false);
  };

  const submitAiCommand = (mode: "ask" | "research") => {
    const command = aiCommand.trim();
    if (!command) return;
    if (mode === "research") {
      runGraphResearch.mutate(command);
    } else {
      askGraphAgent.mutate(command);
    }
  };

  return (
    <main
      className={[
        "graph-builder",
        `workspace-mode-${workspaceMode}`,
        `mobile-section-${mobileSection}`,
        `graph-view-${graphViewMode}`,
        outlineCollapsed ? "outline-compact" : "",
        inspectorCollapsed ? "context-compact" : ""
      ].join(" ")}
      aria-label="Knowledge Graph Builder"
    >
      <header className="mark" aria-label="Project identity">
        <p>Graphview</p>
        <h1>{selectedGraphView?.label ?? graphData.project.name}</h1>
        <span>{selectedGraphView?.description ?? graphData.project.description ?? "Reviewed, cited, AI-ready knowledge."}</span>
      </header>

      <nav className="app-top-chrome" aria-label="Graph workspace controls">
        <GraphPicker
          graphViews={graphViewList}
          open={graphMenuOpen}
          selectedGraphId={selectedGraphId}
          onOpenChange={setGraphMenuOpen}
          onSelect={(graphId) => {
            setSelectedGraphId(graphId);
            setGraphMenuOpen(false);
          }}
        />
        <div className="workspace-switcher" aria-label="Workspace mode">
          <button
            type="button"
            aria-pressed={workspaceMode === "graph"}
            onClick={() => {
              setWorkspaceMode("graph");
              setMobileSection("graph");
            }}
          >
            Graph
          </button>
          <button
            type="button"
            aria-pressed={workspaceMode === "planning"}
            onClick={() => {
              setWorkspaceMode("planning");
              setMobileSection("plan");
            }}
          >
            Planning
          </button>
          <button
            type="button"
            aria-pressed={workspaceMode === "context"}
            onClick={() => {
              setWorkspaceMode("context");
              setMobileSection("context");
            }}
          >
            Active context
          </button>
          <button
            type="button"
            aria-pressed={workspaceMode === "settings"}
            onClick={() => {
              setWorkspaceMode("settings");
              setMobileSection("plan");
            }}
          >
            Settings
          </button>
        </div>
        <span
          className={[
            "api-status-chip",
            health.data?.status === "ok" ? "is-online" : health.isError ? "is-offline" : "is-checking"
          ].join(" ")}
          title={`API ${health.data?.status ?? (health.isError ? "offline" : "checking")}`}
        >
          <i aria-hidden="true" />
          {health.data?.status === "ok" ? "Live" : health.isError ? "Offline" : "Checking"}
        </span>
      </nav>
      <input
        ref={importInputRef}
        className="import-file-input"
        type="file"
        accept="application/json,.json,.md,.txt"
        onChange={handleImportGraph}
      />

      {workspaceMode === "settings" ? (
        <SettingsWorkspace
          providerList={providerList}
          selectedAiProvider={selectedAiProvider}
          selectedAiProviderId={selectedAiProviderId}
          selectedProviderStatus={selectedProviderStatus}
          selectedProviderHasSavedKey={selectedProviderHasSavedKey}
          providerApiKey={providerApiKey}
          saveProviderPending={saveProviderCredential.isPending}
          clearProviderPending={clearProviderCredential.isPending}
          llmEnabled={llmEnabled}
          autoCommitThreshold={autoCommitThreshold}
          updateSettingsPending={updateGraphSettings.isPending}
          onProviderChange={handleAiProviderChange}
          onProviderApiKeyChange={setProviderApiKey}
          onSaveProviderKey={() => saveProviderCredential.mutate()}
          onClearProviderKey={() => clearProviderCredential.mutate()}
          onLlmEnabledChange={setLlmEnabled}
          onAutoCommitThresholdChange={setAutoCommitThreshold}
          onSaveSettings={() => updateGraphSettings.mutate()}
        />
      ) : workspaceMode === "context" ? (
        <AgentContextWorkspace
          sessions={agentContextSessionList}
          selectedSessionId={selectedAgentContextSessionId}
          selectedArtifactId={selectedAgentContextArtifactId}
          graph={agentContextGraph.data}
          artifactContent={agentContextArtifactContent.data}
          artifactContentLoading={agentContextArtifactContent.isLoading}
          artifactContentError={agentContextArtifactContent.isError}
          loading={agentContextSessions.isLoading || agentContextGraph.isLoading}
          onSelectSession={setSelectedAgentContextSessionId}
          onSelectArtifact={setSelectedAgentContextArtifactId}
          onRefresh={() => {
            agentContextSessions.refetch();
            agentContextGraph.refetch();
            agentContextArtifactContent.refetch();
          }}
        />
      ) : workspaceMode === "planning" ? (
        <PlanningWorkspace
          goal={planningGoal}
          message={planningMessage}
          providerList={providerList}
          selectedSession={selectedPlanningSession}
          sessions={planningSessionList}
          createPending={createPlanningSession.isPending}
          sendPending={sendPlanningMessage.isPending}
          onGoalChange={setPlanningGoal}
          onMessageChange={setPlanningMessage}
          onCreateSession={() => createPlanningSession.mutate()}
          onSendMessage={() => sendPlanningMessage.mutate()}
          onSelectSession={setSelectedPlanningSessionId}
          onOpenSettings={() => setWorkspaceMode("settings")}
          onRunResearch={(query) => {
            setAiCommand(query);
            setWorkspaceMode("graph");
            setMobileSection("ask");
            runGraphResearch.mutate(query);
          }}
        />
      ) : (
        <>

      <aside className={`panel outline-panel ${outlineCollapsed ? "is-collapsed" : ""}`} aria-label="Outline">
        <div className="panel-head outline-head">
          <button
            className="icon-button panel-collapse"
            type="button"
            aria-label={outlineCollapsed ? "Expand outline" : "Collapse outline"}
            onClick={() => setOutlineCollapsed((current) => !current)}
          >
            {outlineCollapsed ? "»" : "«"}
          </button>
          <span>
            Outline
            <small>{sourceList.length}.{graphNodes.length}.{proposalList.length}</small>
          </span>
          <div className="icon-row" aria-label="Graph actions">
            <button type="button" title="Add source" disabled={createSource.isPending} onClick={handleAddSource}>+</button>
            <button type="button" title="Import graph" disabled={ingestText.isPending} onClick={() => importInputRef.current?.click()}>Import</button>
            <button type="button" title="Export graph" onClick={handleExportGraph}>Export</button>
          </div>
        </div>
        <div className="outline-body">
          <div className="mode-control" aria-label="Graph lens">
            {graphLensList.map((lens) => (
              <button
                key={lens.id}
                type="button"
                aria-label={lens.label}
                aria-pressed={lens.id === selectedGraphLens.id}
                title={lens.summary}
                onClick={() => {
                  setSelectedGraphLensId(lens.id === selectedGraphLensId ? "all" : lens.id);
                }}
              >
                <GraphLensIcon lensId={lens.id} />
              </button>
            ))}
          </div>
          <label className="search-field">
            Search sources
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} />
          </label>
          <div className="outline-list" aria-label="Source outline">
            {outlineSources.slice(0, 8).map((item) => (
              <button
                className="outline-row"
                key={item.source.id}
                type="button"
                aria-pressed={item.source.id === selectedSourceId}
                onClick={() => selectSource(item.source)}
              >
                <span className={`source-dot source-${item.source.kind}`} />
                <div>
                  <strong>{item.source.title}</strong>
                  <span>
                    {sourceOriginPrefix(item.source)}
                    {item.status.replace("_", " ")} / {item.pending_count} pending / {item.reviewed_count} reviewed
                  </span>
                </div>
                <small>{item.proposal_count}</small>
              </button>
            ))}
            {outlineSources.length === 0 && (
              <div className="outline-empty">No sources yet. Ingest text or add a source to begin.</div>
            )}
          </div>
          <div className="kind-library-head" aria-label="Active node kind lens">
            <span>{kindLibraryTitle}</span>
            <small>{kindLibraryContext}</small>
          </div>
          <div className="legend node-kind-legend" aria-label="Node kind legend">
            {displayedNodeKindDefinitions.map((definition) => (
              <span
                aria-current={activeKind === definition.id ? "true" : undefined}
                className={[
                  "node-kind-token",
                  `graph-kind-${definition.id}`,
                  activeKind === definition.id ? "is-active" : ""
                ].join(" ")}
                key={definition.id}
                title={definition.description}
              >
                <i className="node-kind-dot" />
                <span className="node-kind-label">{definition.label}</span>
              </span>
            ))}
            {canExpandNodeKinds && (
              <button
                className="node-kind-toggle"
                type="button"
                aria-expanded={nodeKindExpanded}
                onClick={() => setNodeKindExpanded((current) => !current)}
              >
                {nodeKindExpanded ? "Show less" : `Show more (${hiddenNodeKindCount})`}
              </button>
            )}
          </div>
        </div>
      </aside>

      <section className={`graph-stage graph-stage-${graphLayout}`} aria-label="Reviewed knowledge graph">
        <GraphCanvas
          nodes={canvasGraph.nodes}
          edges={canvasGraph.edges}
          sources={sourceList}
          citations={canvasCitations}
          activityEvents={graphActivityEvents}
          layout={graphLayout}
          dimension={graphDimension}
          showContents={showContents}
          query={graphQuery}
          selectedNodeId={selectedGraphNodeId}
          fitSequence={fitSequence}
          graphVersion={canvasGraph.graphVersion}
          projectionLevel={canvasGraph.level}
          serverOmittedNodeCount={canvasGraph.omittedNodes}
          serverOmittedEdgeCount={canvasGraph.omittedEdges}
          onSelectNode={handleSelectGraphNode}
          onViewportProjection={setViewportProjection}
        />
        <div className="stage-metrics" aria-label="Current project metrics">
          <span><strong>{graphData.nodes.length}</strong> nodes</span>
          <span><strong>{graphEdges.length}</strong> links</span>
          <span><strong>{sourceList.length}</strong> sources</span>
          <span><strong>{proposalList.filter((proposal) => proposal.status === "pending_review").length}</strong> pending</span>
          {showContents && <span><strong>{contentExpansion.nodes.length}</strong> evidence</span>}
        </div>
      </section>

      <aside className={`panel inspector-panel context-panel ${inspectorCollapsed ? "is-collapsed" : ""}`} aria-label="Context pane">
        <div className="panel-head context-head">
          <span>
            Context
            <small>{contextPulse}</small>
          </span>
          <div className="panel-head-actions">
            <button
              className="icon-button"
              type="button"
              aria-label="Ingest document"
              title="Ingest document"
              onClick={openIngestComposer}
            >
              +
            </button>
            <button
              className="icon-button panel-collapse"
              type="button"
              aria-label={inspectorCollapsed ? "Expand context pane" : "Collapse context pane"}
              onClick={() => setInspectorCollapsed((current) => !current)}
            >
              {inspectorCollapsed ? "‹" : "›"}
            </button>
          </div>
        </div>
        <div className="inspector-content context-pane" ref={inspectorContentRef}>
          {ingestComposerOpen && (
            <form
              className="ingest-tool ingest-drawer"
              aria-label="Ingest document"
              onSubmit={(event) => {
                event.preventDefault();
                if (ingestMode !== "source") return;
                if (sourceTitle.trim() && ingestionText.trim()) {
                  ingestText.mutate({ title: sourceTitle.trim(), content: ingestionText.trim() });
                } else if (sourceTitle.trim()) {
                  createSource.mutate(sourceTitle.trim());
                }
              }}
            >
              <div className="drawer-head">
                <div>
                  <p className="eyebrow">Ingest document</p>
                  <strong>{extractionLensList.map((lens) => lens.label).join(" + ")}</strong>
                </div>
                <button className="icon-button" type="button" aria-label="Close ingest document" onClick={() => setIngestComposerOpen(false)}>
                  ×
                </button>
              </div>
              <div className="ingest-mode-tabs" role="tablist" aria-label="Source input mode">
                <button type="button" role="tab" aria-selected={ingestMode === "source"} onClick={() => setIngestMode("source")}>
                  Add source
                </button>
                <button type="button" role="tab" aria-selected={ingestMode === "connector"} onClick={() => setIngestMode("connector")}>
                  Connect sources
                </button>
              </div>
              {ingestMode === "source" && (
                <>
                  <label>
                    Source title
                    <input value={sourceTitle} onChange={(event) => setSourceTitle(event.target.value)} />
                  </label>
                  <label>
                    Source kind
                    <select
                      value={sourceKind}
                      onChange={(event) => {
                        const nextKind = event.target.value as SourceKind;
                        setSourceKind(nextKind);
                        setSourceTitle((current) => current || defaultTitleForSourceKind(nextKind, sourceList.length + 1));
                        setIngestionText((current) => current || sampleContentForSourceKind(nextKind));
                      }}
                    >
                      <option value="text">Text</option>
                      <option value="markdown">Markdown</option>
                      <option value="url">URL</option>
                      <option value="pdf">PDF text</option>
                      <option value="repository">Repository</option>
                      <option value="ops-document">Ops document</option>
                    </select>
                  </label>
                  <label>
                    Source text
                    <textarea value={ingestionText} onChange={(event) => setIngestionText(event.target.value)} />
                  </label>
                  <button type="submit" disabled={(createSource.isPending || ingestText.isPending) || !sourceTitle.trim()}>
                    {ingestionText.trim() ? "Analyze source" : "Add source"}
                  </button>
                </>
              )}
              {ingestMode === "connector" && (
                <div className="connector-tool" aria-label="Connector setup">
                <p className="eyebrow">Connect sources</p>
                <div className="mode-control connector-picker" aria-label="Connector picker">
                  {connectorList.map((connector) => (
                    <button
                      key={connector.kind}
                      type="button"
                      aria-pressed={connector.kind === connectorKind}
                      title={connector.summary}
                      onClick={() => {
                        setConnectorKind(connector.kind);
                        setConnectorTitle(`${connector.label} source`);
                        setConnectorRemoteId(`${connector.kind}-target`);
                      }}
                    >
                      {connector.label}
                    </button>
                  ))}
                </div>
                <label>
                  Target title
                  <input value={connectorTitle} onChange={(event) => setConnectorTitle(event.target.value)} />
                </label>
                <label>
                  Remote ID or URL
                  <input value={connectorRemoteId} onChange={(event) => setConnectorRemoteId(event.target.value)} />
                </label>
                <label>
                  Connector content
                  <textarea value={connectorContent} onChange={(event) => setConnectorContent(event.target.value)} />
                </label>
                <ProviderSettingsPanel
                  providerList={providerList}
                  selectedAiProvider={selectedAiProvider}
                  selectedAiProviderId={selectedAiProviderId}
                  selectedProviderStatus={selectedProviderStatus}
                  selectedProviderHasSavedKey={selectedProviderHasSavedKey}
                  providerApiKey={providerApiKey}
                  saveProviderPending={saveProviderCredential.isPending}
                  clearProviderPending={clearProviderCredential.isPending}
                  llmEnabled={llmEnabled}
                  autoCommitThreshold={autoCommitThreshold}
                  updateSettingsPending={updateGraphSettings.isPending}
                  onProviderChange={handleAiProviderChange}
                  onProviderApiKeyChange={setProviderApiKey}
                  onSaveProviderKey={() => saveProviderCredential.mutate()}
                  onClearProviderKey={() => clearProviderCredential.mutate()}
                  onLlmEnabledChange={setLlmEnabled}
                  onAutoCommitThresholdChange={setAutoCommitThreshold}
                  onSaveSettings={() => updateGraphSettings.mutate()}
                />
                <div className="connector-actions">
                  <button type="button" disabled={syncConnector.isPending || !connectorTitle.trim()} onClick={() => syncConnector.mutate()}>
                    Sync connector
                  </button>
                  <button
                    type="button"
                    disabled={resyncConnectorTarget.isPending || connectorTargetList.length === 0}
                    onClick={() => connectorTargetList[0] && resyncConnectorTarget.mutate(connectorTargetList[0].id)}
                  >
                    Resync
                  </button>
                </div>
                <span>
                  {selectedConnector?.requires_account ? "OAuth-ready read-only adapter" : "Local read-only adapter"} / {connectorAccountList.length} accounts / {connectorTargetList.length} targets
                </span>
              </div>
              )}
            </form>
          )}

          <div className="context-tabs" role="tablist" aria-label="Context tabs">
            <button
              type="button"
              role="tab"
              aria-selected={contextPaneTab === "data"}
              aria-controls="context-data-panel"
              onClick={() => activateGraphViewMode(contextDataMode)}
            >
              {viewModeLabel(contextDataMode)}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={contextPaneTab === "review"}
              aria-controls="context-review-panel"
              onClick={() => activateGraphViewMode("review")}
            >
              Needs attention
            </button>
          </div>

          {contextPaneTab === "data" ? (
            <div className="context-tab-panel" id="context-data-panel" role="tabpanel" aria-label={`${viewModeLabel(graphViewMode)} mode`}>
              {graphViewMode === "overview" && (
                <div className="mode-panel overview-mode-panel" aria-label="Overview mode">
                  <section className="inspector-section overview-summary">
                    <p className="eyebrow">Overview</p>
                    <h2>{selectedGraphView?.label ?? graphData.project.name}</h2>
                    <p>{selectedGraphView?.description ?? graphData.project.description ?? "Reviewed, cited, AI-ready knowledge."}</p>
                    <div className="overview-action-row" aria-label="Overview actions">
                      <button type="button" onClick={() => activateGraphViewMode("focus")}>Open focus</button>
                      <button type="button" onClick={() => activateGraphViewMode("evidence")}>Open evidence</button>
                      <button type="button" onClick={() => activateGraphViewMode("review")}>Open review</button>
                      <button type="button" onClick={() => activateGraphViewMode("attention")}>Open attention</button>
                    </div>
                  </section>

                  <section className="overview-metric-grid" aria-label="Graph overview metrics">
                    <span><strong>{graphData.nodes.length}</strong> nodes</span>
                    <span><strong>{graphEdges.length}</strong> links</span>
                    <span><strong>{sourceList.length}</strong> sources</span>
                    <span><strong>{effectiveReviewQueue?.pending_count ?? 0}</strong> pending</span>
                    <span><strong>{effectiveInsights?.provenance_coverage.coverage_percent ?? 0}%</strong> traced</span>
                    <span><strong>{effectiveReviewDashboard?.acceptance_rate ?? 0}%</strong> accepted</span>
                  </section>

                  <section className="overview-lane" aria-label="Top graph items">
                    <div className="context-section-head">
                      <p className="eyebrow">Top connected</p>
                      <strong>{overviewTopNodes.length}</strong>
                    </div>
                    <div className="overview-row-list">
                      {overviewTopNodes.map((node, index) => (
                        <button
                          aria-label={`Open top connected item ${index + 1}`}
                          className="overview-row"
                          type="button"
                          key={node.id}
                          onClick={() => handleSelectGraphNode(node.id as ContentNode["id"])}
                        >
                          <span>{node.kind}</span>
                          <strong>{node.label}</strong>
                          <small>{node.degree} links</small>
                        </button>
                      ))}
                    </div>
                  </section>

                  <section className="overview-lane" aria-label="Source overview">
                    <div className="context-section-head">
                      <p className="eyebrow">Sources</p>
                      <strong>{sourceList.length}</strong>
                    </div>
                    <div className="overview-row-list">
                      {evidenceSources.slice(0, 4).map((item, index) => (
                        <button
                          aria-label={`Open source overview item ${index + 1}`}
                          className="overview-row"
                          type="button"
                          key={item.source.id}
                          onClick={() => selectSource(item.source)}
                        >
                          <span>{item.status.replace("_", " ")}</span>
                          <strong>{item.source.title}</strong>
                          <small>{item.pending_count} pending</small>
                        </button>
                      ))}
                      {evidenceSources.length === 0 && <span className="source-content-empty">No sources available.</span>}
                    </div>
                  </section>
                </div>
              )}

              {graphViewMode === "focus" && (
                <div className="mode-panel focus-mode-panel" aria-label="Focus mode">
                  <section className="inspector-section context-signal" aria-label="Focus context">
                    <p className="eyebrow">Focus</p>
                    <h2>{focusNode.label}</h2>
                    <p>{focusNode.summary ?? "Selected graph item."}</p>
                    <div className="context-source-chip">
                      <span>{contextSource?.title ?? "No source selected"}</span>
                      <small>{contextStatus}</small>
                    </div>
                    <div className="context-ai-actions" aria-label="AI context actions">
                      <button
                        type="button"
                        onClick={() => {
                          const question = `Explain ${focusNode.label} using graph citations.`;
                          setAiCommand(question);
                          askGraphAgent.mutate(question);
                        }}
                      >
                        Explain
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const query = `Extend research around ${focusNode.label}`;
                          setAiCommand(query);
                          runGraphResearch.mutate(query);
                        }}
                      >
                        Research related
                      </button>
                    </div>
                  </section>

                  <section className="focus-path-card" aria-label="Focus path context">
                    <div className="context-section-head">
                      <p className="eyebrow">Path</p>
                      <strong>{effectivePath?.path_found ? `${effectivePath.distance} hop${effectivePath.distance === 1 ? "" : "s"}` : "No path"}</strong>
                    </div>
                    {effectivePath?.path_found ? (
                      <div className="focus-path-list">
                        {effectivePath.nodes.map((node, index) => (
                          <button type="button" key={node.id} onClick={() => handleSelectGraphNode(node.id as ContentNode["id"])}>
                            <span>{String(index + 1).padStart(2, "0")}</span>
                            <strong>{node.label}</strong>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <span className="source-content-empty">No bounded reviewed path is available for this focus.</span>
                    )}
                  </section>

                  <section className="context-synapses" aria-label="Related graph items">
                    <div className="context-section-head">
                      <p className="eyebrow">Related</p>
                      <strong>{contextNeighborNodes.length}</strong>
                    </div>
                    <div className="synapse-list">
                      {contextNeighborNodes.map(({ node, relation, direction }) => (
                        <button
                          className="synapse-row"
                          key={`${node.id}-${relation}-${direction}`}
                          type="button"
                          onClick={() => handleSelectGraphNode(node.id)}
                        >
                          <span>{direction === "out" ? "→" : "←"} {relation}</span>
                          <strong>{node.label}</strong>
                        </button>
                      ))}
                      {contextNeighborNodes.length === 0 && <span className="source-content-empty">No reviewed related items for this focus.</span>}
                    </div>
                  </section>
                </div>
              )}

              {graphViewMode === "evidence" && (
                <div className="mode-panel evidence-mode-panel" aria-label="Evidence mode">
                  <section className="source-content-reader source-content-card evidence-reader-card" aria-label="Evidence preview">
                    <div className="source-content-head source-content-head-row">
                      <div>
                        <p className="eyebrow">Evidence</p>
                        <strong>{contextSource?.title ?? "Select a source"}</strong>
                        <span>
                          {contextSource
                            ? `${contextBlocks.length} blocks / ${contextSource.kind}${sourceConnectorKind(contextSource) ? ` / ${sourceConnectorKind(contextSource)}` : ""}`
                            : "No source context"}
                        </span>
                      </div>
                      <div className="source-action-row" aria-label="Evidence actions">
                        <button className="icon-button" type="button" aria-label="Open source in full view" title="Open full view" onClick={() => setSourceModalOpen(true)}>
                          ↗
                        </button>
                        <button className="icon-button" type="button" aria-label="Copy source content" title="Copy" onClick={copySourceContent}>
                          ⧉
                        </button>
                        <button className="icon-button" type="button" aria-label="Export source content" title="Export" onClick={exportSourceContent}>
                          ↓
                        </button>
                        <button className="icon-button" type="button" aria-label="Share source content" title="Share" onClick={shareSourceContent}>
                          ↪
                        </button>
                      </div>
                    </div>
                    {contentActionStatus && <small className="content-action-status">{contentActionStatus}</small>}
                    {evidencePreviewBlocks.length > 0 ? (
                      <div className="source-content-scroll source-content-preview evidence-block-list">
                        {evidencePreviewBlocks.map((chunk) => (
                          <article className={`source-block source-block-${chunk.block_type}`} key={chunk.id}>
                            <header>
                              <span>{chunk.heading_path.join(" / ") || contextSource?.title || focusNode.label}</span>
                              <small>{chunk.locator}</small>
                            </header>
                            <p>{chunk.text}</p>
                            <div className="reader-inline-actions evidence-inline-actions" aria-label="Evidence block actions">
                              <button
                                type="button"
                                onClick={() => {
                                  const question = `Explain the source passage at ${chunk.locator} using graph citations.`;
                                  setAiCommand(question);
                                  askGraphAgent.mutate(question);
                                }}
                              >
                                Ask
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  const query = `Research follow-up evidence for ${chunk.text.split("\n")[0] || chunk.locator}`;
                                  setAiCommand(query);
                                  runGraphResearch.mutate(query);
                                }}
                              >
                                Research
                              </button>
                              <button
                                type="button"
                                disabled={!contextSource || createProposal.isPending}
                                onClick={() => {
                                  if (!contextSource) return;
                                  createProposal.mutate({
                                    sourceId: contextSource.id,
                                    label: firstLine(chunk.text) ?? contextSource.title,
                                    summary: truncatePlainLabel(chunk.text, 360),
                                    locator: chunk.locator
                                  });
                                }}
                              >
                                Add to graph
                              </button>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="source-content-empty">No stored source content blocks are available for this source.</div>
                    )}
                  </section>

                  <section className="evidence-source-list" aria-label="Available sources">
                    <div className="context-section-head">
                      <p className="eyebrow">Sources</p>
                      <strong>{sourceList.length}</strong>
                    </div>
                    <div className="overview-row-list">
                      {evidenceSources.map((item) => (
                        <button className="overview-row" type="button" key={item.source.id} onClick={() => selectSource(item.source)}>
                          <span>{sourceOriginPrefix(item.source) || item.source.kind}</span>
                          <strong>{item.source.title}</strong>
                          <small>{item.proposal_count} proposals</small>
                        </button>
                      ))}
                      {evidenceSources.length === 0 && <span className="source-content-empty">No sources available.</span>}
                    </div>
                  </section>

                  <section className="evidence-citation-list" aria-label="Citation-backed claims">
                    <div className="context-section-head">
                      <p className="eyebrow">Citations</p>
                      <strong>{evidenceCitations.length}</strong>
                    </div>
                    <div className="citation-list compact-citation-list">
                      {evidenceCitations.map((citation) => (
                        <article className="citation-row" key={citation.id}>
                          <strong>{citation.label}</strong>
                          <span>{citation.quote ?? citation.locator ?? citation.source_title ?? "Graph citation"}</span>
                        </article>
                      ))}
                      {evidenceCitations.length === 0 && <span className="source-content-empty">Ask the graph or open review work to collect citations.</span>}
                    </div>
                  </section>
                </div>
              )}
            </div>
          ) : (
            <div className="context-tab-panel" id="context-review-panel" role="tabpanel" aria-label="Needs attention">
              {graphViewMode === "attention" && (
                <section className="nervous-system-panel" aria-label="Digital nervous system">
                  <div className="context-section-head">
                    <div>
                      <p className="eyebrow">Graph-centered Attention</p>
                      <strong>Digital nervous system</strong>
                    </div>
                    <button type="button" disabled={createOperationalSignal.isPending} onClick={() => createOperationalSignal.mutate()}>
                      Sense change
                    </button>
                  </div>
                  <div className="operating-loop-strip" aria-label="Operating loop">
                    {["Sense", "Interpret", "Remember", "Prioritize", "Decide", "Act", "Observe", "Learn"].map((step) => (
                      <span key={step}>{step}</span>
                    ))}
                  </div>
                  <div className="metric-grid attention-metrics nervous-metrics" aria-label="Digital nervous system metrics">
                    <span><strong>{operationalSignals.length}</strong> signals</span>
                    <span><strong>{openOperationalAttention.length}</strong> open</span>
                    <span><strong>{slaRiskCount}</strong> SLA risk</span>
                    <span><strong>{pendingOperationalActionCount}</strong> actions</span>
                    <span><strong>{operationalObservationCount}</strong> observations</span>
                    <span><strong>{operationalAlertCount}</strong> alerts</span>
                    <span><strong>{routingPolicyList.length}</strong> policies</span>
                    <span><strong>{feedbackEventList.length}</strong> learned</span>
                  </div>
                  <div className="nervous-system-list" aria-label="Attention operating items">
                    {operationalAttentionItems.slice(0, 4).map((item) => (
                      <article className={`nervous-item is-${item.sla_status}`} key={item.id}>
                        <header>
                          <div>
                            <p className="eyebrow">{item.severity} / {item.sla_status.replaceAll("_", " ")}</p>
                            <strong>{item.title}</strong>
                          </div>
                          <span>{item.status.replaceAll("_", " ")}</span>
                        </header>
                        <p>{item.summary}</p>
                        <div className="nervous-link-strip">
                          <span>{ownerNameById.get(item.owner_id ?? "") ?? "Unassigned"}</span>
                          <span>{item.suggested_actions[0] ?? "review"}</span>
                          <span>{item.due_at ? new Date(item.due_at).toLocaleDateString() : "No SLA"}</span>
                        </div>
                        <div className="review-item-actions">
                          <button
                            type="button"
                            disabled={Boolean(item.decision_record_id) || createOperationalDecision.isPending}
                            onClick={() => createOperationalDecision.mutate(item)}
                          >
                            {item.decision_record_id ? "Decided" : "Decide"}
                          </button>
                          <button
                            type="button"
                            disabled={Boolean(item.action_proposal_id) || createOperationalAction.isPending}
                            onClick={() => createOperationalAction.mutate(item)}
                          >
                            {item.action_proposal_id ? "Proposed" : "Propose action"}
                          </button>
                        </div>
                      </article>
                    ))}
                    {operationalAttentionItems.length === 0 && (
                      <article className="nervous-item is-empty">
                        <header>
                          <div>
                            <p className="eyebrow">No persisted Attention</p>
                            <strong>Digital nervous system idle</strong>
                          </div>
                          <span>{routingPolicyList.length} policies</span>
                        </header>
                        <p>New signals will route into this graph workspace when owners and policies match.</p>
                      </article>
                    )}
                  </div>
                  <div className="nervous-action-list" aria-label="Gated action proposals">
                    {operationalActionProposalList.slice(0, 4).map((action) => {
                      const run = operationalActionRunList.find((item) => item.action_proposal_id === action.id);
                      return (
                        <article className="nervous-action" key={action.id}>
                          <div>
                            <p className="eyebrow">{action.action_type.replaceAll("_", " ")}</p>
                            <strong>{action.title}</strong>
                            <span>{action.status.replaceAll("_", " ")}</span>
                          </div>
                          <div className="review-item-actions">
                            <button
                              type="button"
                              disabled={!["pending_review", "proposed"].includes(action.status) || approveOperationalAction.isPending}
                              onClick={() => approveOperationalAction.mutate(action)}
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              disabled={action.status !== "approved" || runOperationalAction.isPending}
                              onClick={() => runOperationalAction.mutate(action)}
                            >
                              Run
                            </button>
                            <button
                              type="button"
                              disabled={!run || Boolean(operationalOutcomeList.find((outcome) => outcome.action_run_id === run.id)) || recordOperationalOutcome.isPending}
                              onClick={() => run && recordOperationalOutcome.mutate(run)}
                            >
                              Observe
                            </button>
                          </div>
                        </article>
                      );
                    })}
                    {operationalActionProposalList.length === 0 && latestOperationalOutcome && (
                      <article className="nervous-action">
                        <div>
                          <p className="eyebrow">Latest outcome</p>
                          <strong>{latestOperationalOutcome.title}</strong>
                          <span>{latestOperationalOutcome.status}</span>
                        </div>
                      </article>
                    )}
                  </div>
                </section>
              )}
              <section className="review-stack attention-stack" aria-label="Needs attention">
                <div className="context-section-head">
                  <div>
                    <p className="eyebrow">Needs attention</p>
                    <strong>{attentionItems.length} work items</strong>
                  </div>
                  <span>{pendingRelationshipCount} edge proposals</span>
                </div>
                <div className="metric-grid attention-metrics" aria-label="Trust and review summary">
                  <span><strong>{effectiveInsights?.provenance_coverage.coverage_percent ?? 0}%</strong> traced</span>
                  <span><strong>{effectiveReviewQueue?.ready_count ?? 0}</strong> ready</span>
                  <span><strong>{effectiveReviewQueue?.blocked_count ?? 0}</strong> blocked</span>
                  <span><strong>{effectiveReviewDashboard?.acceptance_rate ?? 0}%</strong> accepted</span>
                </div>
                <div className="attention-list">
                  {attentionItems.map((item) => (
                    <article className={`attention-item attention-${item.tone}`} key={item.id}>
                      <div>
                        <p className="eyebrow">{item.meta}</p>
                        <strong>{item.title}</strong>
                        <span>{item.detail}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          if (item.tone === "review" && pendingProposal) {
                            setGraphQuery(item.title);
                          } else if (item.tone === "source" && topSourceReview) {
                            selectSource(topSourceReview.source);
                          } else if (item.tone === "research") {
                            setCitationDrawerOpen(true);
                          } else if (item.tone === "sync") {
                            openIngestComposer();
                            setIngestMode("connector");
                          } else if (item.tone === "operation") {
                            activateGraphViewMode("attention");
                          } else {
                            setGraphQuery(item.title);
                          }
                        }}
                        disabled={item.tone === "review" && !pendingProposal}
                      >
                        {item.actionLabel}
                      </button>
                    </article>
                  ))}
                </div>
              </section>

              <div className="review-worklist" aria-label="Review work items">
                {(effectiveReviewQueue?.items ?? []).map((item) => {
                  const proposalLabel =
                    item.change_summary ??
                    item.proposal.proposed_value.label ??
                    item.proposal.proposed_value.relation ??
                    "Graph proposal";
                  return (
                    <article className={`review-work-item ${item.blocked ? "is-blocked" : ""}`} key={item.proposal.id}>
                      <header>
                        <div>
                          <p className="eyebrow">{reviewWorkItemLabel(item.work_item_kind, item.action)}</p>
                          <strong>{proposalLabel}</strong>
                        </div>
                        <span>{item.ready_to_commit ? "Ready" : "Blocked"}</span>
                      </header>
                      <p>{item.reason}</p>
                      <div className="review-evidence-strip" aria-label="Review evidence">
                        <span>{item.source?.title ?? item.evidence_summary ?? "No source linked"}</span>
                        <span>{item.citations?.length ?? 0} citations</span>
                        <span>{(item.affected_graph_ids ?? item.endpoint_node_ids).length} affected</span>
                      </div>
                      <div className="review-item-actions" aria-label={`Review ${proposalLabel}`}>
                        <button
                          type="button"
                          disabled={item.blocked || reviewProposal.isPending}
                          onClick={() =>
                            reviewProposal.mutate({
                              proposalId: item.proposal.id,
                              decision: "accept",
                              rationale: "Accepted from typed review queue"
                            })
                          }
                        >
                          Accept
                        </button>
                        <button
                          type="button"
                          disabled={reviewProposal.isPending}
                          onClick={() =>
                            reviewProposal.mutate({
                              proposalId: item.proposal.id,
                              decision: "reject",
                              rationale: "Rejected from typed review queue"
                            })
                          }
                        >
                          Reject
                        </button>
                        <button
                          type="button"
                          disabled={item.blocked || reviewProposal.isPending}
                          onClick={() =>
                            reviewProposal.mutate({
                              proposalId: item.proposal.id,
                              decision: "edit",
                              rationale: "Reviewed with edits from typed review queue"
                            })
                          }
                        >
                          Edit
                        </button>
                      </div>
                    </article>
                  );
                })}
                {!(effectiveReviewQueue?.items.length) && (
                  <div className="source-content-empty">No review work is waiting.</div>
                )}
              </div>
            </div>
          )}
        </div>
      </aside>

      {sourceModalOpen && (
        <div className="content-modal-backdrop" role="presentation" onMouseDown={() => setSourceModalOpen(false)}>
          <section
            className="content-modal source-reader-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Source reader"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="content-modal-head">
              <div>
                <p className="eyebrow">Source reader</p>
                <h2>{contextSource?.title ?? focusNode.label}</h2>
                <span>{contextStatus}</span>
                {contentActionStatus && <small className="content-action-status">{contentActionStatus}</small>}
              </div>
              <div className="source-action-row" aria-label="Full source actions">
                <button className="icon-button" type="button" aria-label="Copy source content" title="Copy" onClick={copySourceContent}>
                  ⧉
                </button>
                <button className="icon-button" type="button" aria-label="Export source content" title="Export" onClick={exportSourceContent}>
                  ↓
                </button>
                <button className="icon-button" type="button" aria-label="Share source content" title="Share" onClick={shareSourceContent}>
                  ↪
                </button>
                <button className="icon-button" type="button" aria-label="Close full source content" title="Close" onClick={() => setSourceModalOpen(false)}>
                  ×
                </button>
              </div>
            </header>
            <div className="content-modal-body source-reader-layout">
              <aside className="source-reader-outline" aria-label="Source outline">
                <p className="eyebrow">Outline</p>
                {contextBlocks.map((chunk, index) => (
                  <a href={`#reader-block-${chunk.id}`} key={chunk.id}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{chunk.text.split("\n")[0] || chunk.locator}</strong>
                  </a>
                ))}
              </aside>
              <div className="source-reader-document" aria-label="Readable source document">
                {contextBlocks.map((chunk, index) => (
                  <article
                    className={`source-block reader-block source-block-${chunk.block_type}`}
                    id={`reader-block-${chunk.id}`}
                    key={chunk.id}
                  >
                    <header>
                      <span>{chunk.heading_path.join(" / ") || contextSource?.title || focusNode.label}</span>
                      <small>{chunk.locator}</small>
                    </header>
                    <h3>{chunk.text.split("\n")[0] || `Block ${index + 1}`}</h3>
                    <p>{chunk.text.split("\n").slice(1).join("\n") || chunk.text}</p>
                    {(chunk.links.length > 0 || chunk.mentions.length > 0) && (
                      <footer>
                        {chunk.links.map((link) => (
                          <a href={link} key={link} rel="noreferrer" target="_blank">{link}</a>
                        ))}
                        {chunk.mentions.map((mention) => (
                          <span key={mention}>{mention}</span>
                        ))}
                      </footer>
                    )}
                    <div className="reader-inline-actions" aria-label="Reader actions">
                      <button
                        type="button"
                        onClick={() => {
                          const question = `Explain the source passage at ${chunk.locator} using graph citations.`;
                          setAiCommand(question);
                          setSourceModalOpen(false);
                          askGraphAgent.mutate(question);
                        }}
                      >
                        Ask about passage
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const query = `Research follow-up evidence for ${chunk.text.split("\n")[0] || chunk.locator}`;
                          setAiCommand(query);
                          setSourceModalOpen(false);
                          runGraphResearch.mutate(query);
                        }}
                      >
                        Research around passage
                      </button>
                      <button
                        type="button"
                        disabled={!contextSource || createProposal.isPending}
                        onClick={() => {
                          if (!contextSource) return;
                          createProposal.mutate({
                            sourceId: contextSource.id,
                            label: firstLine(chunk.text) ?? contextSource.title,
                            summary: truncatePlainLabel(chunk.text, 360),
                            locator: chunk.locator
                          });
                        }}
                      >
                        Add to graph
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </section>
        </div>
      )}

      <section className="panel ai-command-panel" aria-label="Graph AI agent">
        <div className="ai-command-head">
          <div>
            <p className="eyebrow">Graph AI</p>
            <strong>{askGraphAgent.isPending ? "Reading graph" : runGraphResearch.isPending ? "Researching" : "Ask, read, extend"}</strong>
          </div>
          <button className="icon-button" type="button" aria-label="Open citations" onClick={() => setCitationDrawerOpen((current) => !current)}>
            ◐
          </button>
        </div>
        <div className="ai-scope-strip" aria-label="AI scope">
          <span>{selectedGraphLens.label}</span>
          <strong>{activeScopeLabel}</strong>
          <button
            type="button"
            onClick={() => {
              const question = `Summarize ${activeScopeLabel} with graph citations and source evidence.`;
              setAiCommand(question);
              askGraphAgent.mutate(question);
            }}
          >
            Summarize
          </button>
          <button
            type="button"
            onClick={() => {
              const query = `Find missing evidence, sources, and relationships for ${activeScopeLabel}.`;
              setAiCommand(query);
              runGraphResearch.mutate(query);
            }}
          >
            Find gaps
          </button>
        </div>
        <form
          className="ai-command-form"
          onSubmit={(event) => {
            event.preventDefault();
            submitAiCommand("ask");
          }}
        >
          <input
            aria-label="Ask graph AI"
            value={aiCommand}
            onChange={(event) => setAiCommand(event.target.value)}
            placeholder="Ask this graph, source, or selection"
          />
          <button type="submit" disabled={!aiCommand.trim() || askGraphAgent.isPending}>Ask</button>
          <button type="button" disabled={!aiCommand.trim() || runGraphResearch.isPending} onClick={() => submitAiCommand("research")}>
            Research
          </button>
        </form>
        {graphAnswer && (
          <div className="ai-answer">
            <span>{Math.round(graphAnswer.confidence * 100)}% confidence / {graphAnswer.citations.length} citations</span>
            <p>{graphAnswer.answer}</p>
          </div>
        )}
        {researchResult && (
          <div className="ai-research-status">
            <strong>{researchResult.research_task.status.replace("_", " ")}</strong>
            <span>{researchResult.proposals.length} proposals from {researchResult.source?.title ?? "AI research"}</span>
          </div>
        )}
        {graphAgentToolCalls.length > 0 && (
          <div className="agent-tool-strip" aria-label="Graph agent activity">
            {graphAgentToolCalls.slice(0, 3).map((toolCall) => (
              <AgentToolCallCard toolCall={toolCall} key={toolCall.id} />
            ))}
          </div>
        )}
      </section>

      {citationDrawerOpen && (
        <section className="panel citation-drawer" aria-label="AI citations and actions">
          <div className="panel-head">
            <span>AI citations</span>
            <button className="icon-button" type="button" aria-label="Close citations" onClick={() => setCitationDrawerOpen(false)}>
              ×
            </button>
          </div>
          <div className="citation-list">
            {(graphAnswer?.citations ?? []).map((citation) => (
              <article className="citation-row" key={citation.id}>
                <strong>{citation.label}</strong>
                <span>{citation.quote ?? citation.locator ?? citation.source_title ?? "Graph citation"}</span>
              </article>
            ))}
            {researchResult?.agent_run.action_proposals.map((action) => (
              <article className="citation-row action-row-card" key={action.id}>
                <strong>{action.title}</strong>
                <span>{action.summary}</span>
                <button type="button" disabled={approveAgentAction.isPending || action.status !== "pending_review"} onClick={() => approveAgentAction.mutate(action)}>
                  {action.status === "pending_review" ? "Approve" : action.status}
                </button>
              </article>
            ))}
            {!graphAnswer && !researchResult && <span className="source-content-empty">Ask the graph or run research to collect citations.</span>}
          </div>
        </section>
      )}

      <nav className="panel dock graph-control-dock" aria-label="Graph controls">
        <div className="dock-group dock-view-group" aria-label="View mode">
          {(["overview", "focus", "evidence", "review", "attention"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              aria-label={`${viewModeLabel(mode)} view`}
              aria-pressed={graphViewMode === mode}
              title={`${viewModeLabel(mode)} view`}
              onClick={() => activateGraphViewMode(mode)}
            >
              <DockIcon kind={mode} />
              <span>{viewModeLabel(mode)}</span>
            </button>
          ))}
        </div>
        <div className="dock-group dock-layout-group" aria-label="Layout">
          <button type="button" aria-label="Force layout" aria-pressed={graphLayout === "force"} title="Force layout" onClick={() => setGraphLayout("force")}>
            <DockIcon kind="force" />
            <span>Force</span>
          </button>
          <button type="button" aria-label="Radial layout" aria-pressed={graphLayout === "radial"} title="Radial layout" onClick={() => setGraphLayout("radial")}>
            <DockIcon kind="radial" />
            <span>Radial</span>
          </button>
          <button type="button" aria-label="Arc layout" aria-pressed={graphLayout === "arc"} title="Arc layout" onClick={() => setGraphLayout("arc")}>
            <DockIcon kind="arc" />
            <span>Arc</span>
          </button>
        </div>
        <div className="dock-group dock-dimension-group" aria-label="Dimension">
          <button
            type="button"
            aria-label="2D graph"
            aria-pressed={graphLayout === "arc" || graphDimension === "2d"}
            disabled={graphLayout === "arc"}
            onClick={() => setGraphDimension("2d")}
          >
            2D
          </button>
          <button
            type="button"
            aria-label="3D graph"
            aria-pressed={graphLayout !== "arc" && graphDimension === "3d"}
            disabled={graphLayout === "arc"}
            onClick={() => setGraphDimension("3d")}
          >
            3D
          </button>
        </div>
        <div className="dock-group dock-utility-group" aria-label="Utilities">
          <button
            type="button"
            aria-label={showContents ? "Hide source graph" : "Show source graph"}
            aria-pressed={showContents}
            title={showContents ? "Hide source graph" : "Show source graph"}
            onClick={toggleContents}
          >
            <DockIcon kind="sources" />
            <span>Sources</span>
          </button>
          <button type="button" aria-label="Fit graph" title="Fit graph" onClick={fitGraph}>
            <DockIcon kind="fit" />
            <span>Fit</span>
          </button>
        </div>
        <label className="dock-search">
          <span>Search graph</span>
          <input
            aria-label="Search graph"
            value={graphQuery}
            onChange={(event) => setGraphQuery(event.target.value)}
            placeholder="search"
            autoComplete="off"
            spellCheck={false}
          />
          {graphQuery && (
            <button type="button" aria-label="Clear graph search" onClick={() => setGraphQuery("")}>
              ×
            </button>
          )}
        </label>
      </nav>

	        </>
	      )}
      <nav className="mobile-command-nav" aria-label="Mobile workspace shortcuts">
        <button
          type="button"
          aria-label="Open graph"
          title="Graph"
          aria-pressed={workspaceMode === "graph" && mobileSection === "graph"}
          onClick={() => {
            setWorkspaceMode("graph");
            setMobileSection("graph");
          }}
        >
          <MobileNavIcon kind="graph" />
          <span>Graph</span>
        </button>
        <button
          type="button"
          aria-label="Open sources"
          title="Sources"
          aria-pressed={workspaceMode === "graph" && mobileSection === "sources"}
          onClick={() => {
            setWorkspaceMode("graph");
            setMobileSection("sources");
            setOutlineCollapsed(false);
          }}
        >
          <MobileNavIcon kind="sources" />
          <span>Sources</span>
        </button>
        <button
          type="button"
          aria-label="Ask graph AI"
          title="Ask"
          aria-pressed={workspaceMode === "graph" && mobileSection === "ask"}
          onClick={() => {
            setWorkspaceMode("graph");
            setMobileSection("ask");
          }}
        >
          <MobileNavIcon kind="ask" />
          <span>Ask</span>
        </button>
        <button
          className="mobile-dimension-command"
          type="button"
          aria-label="2D graph"
          title="2D"
          aria-pressed={graphLayout === "arc" || graphDimension === "2d"}
          disabled={graphLayout === "arc"}
          onClick={() => setGraphDimension("2d")}
        >
          <strong aria-hidden="true">2D</strong>
          <span>2D</span>
        </button>
        <button
          className="mobile-dimension-command"
          type="button"
          aria-label="3D graph"
          title="3D"
          aria-pressed={graphLayout !== "arc" && graphDimension === "3d"}
          disabled={graphLayout === "arc"}
          onClick={() => setGraphDimension("3d")}
        >
          <strong aria-hidden="true">3D</strong>
          <span>3D</span>
        </button>
        <button
          type="button"
          aria-label="Open review queue"
          title="Review"
          aria-pressed={workspaceMode === "graph" && mobileSection === "review"}
          onClick={() => {
            setWorkspaceMode("graph");
            setContextPaneTab("review");
            setMobileSection("review");
            setInspectorCollapsed(false);
          }}
        >
          <MobileNavIcon kind="review" />
          <span>Review</span>
        </button>
      </nav>
    </main>
  );
}

function MobileNavIcon({ kind }: { kind: "graph" | "sources" | "ask" | "review" }) {
  if (kind === "sources") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M4 6.5h16" />
        <path d="M4 12h16" />
        <path d="M4 17.5h16" />
        <path d="M7 4.5v4" />
        <path d="M14 10v4" />
        <path d="M10 15.5v4" />
      </svg>
    );
  }
  if (kind === "ask") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M5 7.5a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v3.5a4 4 0 0 1-4 4h-3.5L7 19v-4a4 4 0 0 1-2-3.5Z" />
        <path d="M9 8h6" />
        <path d="M9 11h3.5" />
      </svg>
    );
  }
  if (kind === "review") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M8 5h8" />
        <path d="M6 8h12v12H6Z" />
        <path d="m8.5 14 2 2 5-5" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
      <circle cx="7" cy="7" r="3" />
      <circle cx="17" cy="7" r="3" />
      <circle cx="12" cy="17" r="3" />
      <path d="M9.5 8.5 11 14" />
      <path d="m14.5 8.5-1.5 5.5" />
      <path d="M10 7h4" />
    </svg>
  );
}

function BlueprintMap({
  topics,
  openQuestions,
  researchTasks
}: {
  topics: Array<{ name?: string; priority?: string }>;
  openQuestions: string[];
  researchTasks: Array<{ query?: string; source_policy?: string; priority?: string }>;
}) {
  const visibleTopics = topics.length > 0 ? topics.slice(0, 4) : [{ name: "Goal", priority: "seed" }];
  const visibleQuestions = openQuestions.slice(0, 3);
  const visibleTasks = researchTasks.length > 0 ? researchTasks.slice(0, 3) : [{ query: "Seed research", source_policy: "mixed" }];

  return (
    <div className="blueprint-map" aria-label="Graph build map">
      <div className="blueprint-cluster blueprint-cluster-topics">
        <p className="eyebrow">Topics</p>
        {visibleTopics.map((topic, index) => (
          <span key={`${topic.name}-${index}`}>{topic.name ?? "Topic"}</span>
        ))}
      </div>
      <div className="blueprint-core">
        <strong>Graph spec</strong>
        <span>citation-gated</span>
      </div>
      <div className="blueprint-cluster blueprint-cluster-questions">
        <p className="eyebrow">Questions</p>
        {visibleQuestions.length > 0
          ? visibleQuestions.map((question) => <span key={question}>{question}</span>)
          : <span>Clarify unknowns</span>}
      </div>
      <div className="blueprint-cluster blueprint-cluster-tasks">
        <p className="eyebrow">Research</p>
        {visibleTasks.map((task, index) => (
          <span key={`${task.query}-${index}`}>{task.query ?? "Research task"}</span>
        ))}
      </div>
    </div>
  );
}

function ProviderSettingsPanel({
  providerList,
  selectedAiProvider,
  selectedAiProviderId,
  selectedProviderStatus,
  selectedProviderHasSavedKey,
  providerApiKey,
  saveProviderPending,
  clearProviderPending,
  llmEnabled,
  autoCommitThreshold,
  updateSettingsPending,
  onProviderChange,
  onProviderApiKeyChange,
  onSaveProviderKey,
  onClearProviderKey,
  onLlmEnabledChange,
  onAutoCommitThresholdChange,
  onSaveSettings
}: {
  providerList: ApiProviderDescriptor[];
  selectedAiProvider?: ApiProviderDescriptor;
  selectedAiProviderId: ApiProviderId;
  selectedProviderStatus: string;
  selectedProviderHasSavedKey: boolean;
  providerApiKey: string;
  saveProviderPending: boolean;
  clearProviderPending: boolean;
  llmEnabled: boolean;
  autoCommitThreshold: number;
  updateSettingsPending: boolean;
  onProviderChange: (providerId: ApiProviderId) => void;
  onProviderApiKeyChange: (value: string) => void;
  onSaveProviderKey: () => void;
  onClearProviderKey: () => void;
  onLlmEnabledChange: (enabled: boolean) => void;
  onAutoCommitThresholdChange: (threshold: number) => void;
  onSaveSettings: () => void;
}) {
  return (
    <div className="provider-settings" aria-label="AI provider credentials">
      <div className="provider-settings-head">
        <span>AI provider</span>
        <strong>{selectedProviderStatus}</strong>
      </div>
      <label>
        Default provider
        <select value={selectedAiProviderId} onChange={(event) => onProviderChange(event.target.value as ApiProviderId)}>
          {providerList.map((provider) => (
            <option value={provider.id} key={provider.id}>
              {provider.label}
            </option>
          ))}
        </select>
      </label>
      {selectedAiProviderId !== "graphview-local" && (
        <>
          <label>
            API key
            <input
              type="password"
              value={providerApiKey}
              autoComplete="off"
              placeholder={selectedAiProvider?.configured ? "Configured" : "Provider key"}
              onChange={(event) => onProviderApiKeyChange(event.target.value)}
            />
          </label>
          <div className="provider-actions">
            <button type="button" disabled={saveProviderPending || !providerApiKey.trim()} onClick={onSaveProviderKey}>
              Save key
            </button>
            <button type="button" disabled={clearProviderPending || !selectedProviderHasSavedKey} onClick={onClearProviderKey}>
              Clear
            </button>
          </div>
        </>
      )}
      <div className="connector-settings" aria-label="Advanced connector settings">
        <label>
          <input type="checkbox" checked={llmEnabled} onChange={(event) => onLlmEnabledChange(event.target.checked)} />
          LLM extraction
        </label>
        <label>
          Auto-commit
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={autoCommitThreshold}
            onChange={(event) => onAutoCommitThresholdChange(Number(event.target.value))}
          />
        </label>
      </div>
      <button className="provider-save-settings" type="button" disabled={updateSettingsPending} onClick={onSaveSettings}>
        Save settings
      </button>
    </div>
  );
}

function AgentContextWorkspace({
  sessions,
  selectedSessionId,
  selectedArtifactId,
  graph,
  artifactContent,
  artifactContentLoading,
  artifactContentError,
  loading,
  onSelectSession,
  onSelectArtifact,
  onRefresh
}: {
  sessions: ApiAgentContextSession[];
  selectedSessionId?: string;
  selectedArtifactId?: string;
  graph?: ApiAgentContextGraph;
  artifactContent?: ApiAgentContextBlobContent;
  artifactContentLoading: boolean;
  artifactContentError: boolean;
  loading: boolean;
  onSelectSession: (sessionId: string) => void;
  onSelectArtifact: (artifactId: string | undefined) => void;
  onRefresh: () => void;
}) {
  const selectedSession = sessions.find((session) => session.id === selectedSessionId) ?? sessions[0];
  const events = graph?.events ?? [];
  const artifacts = graph?.artifacts ?? [];
  const selectedArtifact = artifacts.find((artifact) => artifact.id === selectedArtifactId);
  const gatewayCount = events.filter((event) => event.authority === "gateway").length;
  const adapterCount = events.filter((event) => event.authority === "adapter_reported").length;
  const passiveCount = events.filter((event) => event.authority === "passive_reconciled").length;
  const promptEvents = events.filter((event) => ["prompt_built", "model_request", "model_response"].includes(event.event_kind));
  const editEvents = events.filter((event) => ["edit_applied", "diff_observed", "commit_observed"].includes(event.event_kind));

  return (
    <section className="agent-context-workspace" aria-label="Active agent context">
      <header className="workspace-head compact">
        <div>
          <p>Active context</p>
          <h2>{selectedSession?.title ?? "No captured sessions"}</h2>
          <span>
            {selectedSession
              ? `${selectedSession.runtime_kind} / ${selectedSession.status} / ${selectedSession.authority.replaceAll("_", " ")}`
              : "Waiting for adapter sessions"}
          </span>
        </div>
        <button type="button" className="provider-save-settings" onClick={onRefresh}>
          Refresh
        </button>
      </header>

      <div className="agent-context-grid">
        <aside className="agent-context-sessions" aria-label="Captured sessions">
          <div className="context-section-head">
            <div>
              <span>Sessions</span>
              <strong>{sessions.length}</strong>
            </div>
          </div>
          <div className="agent-context-session-list">
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                aria-pressed={session.id === selectedSession?.id}
                onClick={() => onSelectSession(session.id)}
              >
                <strong>{session.title}</strong>
                <span>{session.runtime_kind} / {session.status}</span>
                <small>{formatShortDate(session.updated_at)}</small>
              </button>
            ))}
            {sessions.length === 0 && <div className="outline-empty">No agent context sessions captured.</div>}
          </div>
        </aside>

        <section className="agent-context-main" aria-label="Context graph and timeline">
          <div className="agent-context-metrics" aria-label="Active context metrics">
            <span><strong>{events.length}</strong> events</span>
            <span><strong>{artifacts.length}</strong> artifacts</span>
            <span><strong>{gatewayCount}</strong> gateway</span>
            <span><strong>{adapterCount + passiveCount}</strong> reconciled</span>
          </div>

          <div className="agent-context-panels">
            <article className="agent-context-card" aria-label="Context graph projection">
              <div className="context-section-head">
                <div>
                  <span>Context graph</span>
                  <strong>{graph?.nodes.length ?? 0}.{graph?.edges.length ?? 0}</strong>
                </div>
              </div>
              <div className="context-projection-list">
                {(graph?.edges ?? []).slice(0, 12).map((edge) => {
                  const source = graph?.nodes.find((node) => node.id === edge.source_id);
                  const target = graph?.nodes.find((node) => node.id === edge.target_id);
                  return (
                    <div key={edge.id} className={edge.observed ? "is-observed" : "is-inferred"}>
                      <span>{source?.label ?? edge.source_id}</span>
                      <strong>{edge.relation.replaceAll("_", " ")}</strong>
                      <span>{target?.label ?? edge.target_id}</span>
                    </div>
                  );
                })}
                {loading && <div className="outline-empty">Loading active context.</div>}
                {!loading && (graph?.edges.length ?? 0) === 0 && <div className="outline-empty">No context graph edges yet.</div>}
              </div>
            </article>

            <article className="agent-context-card" aria-label="Prompt and edit activity">
              <div className="context-section-head">
                <div>
                  <span>Prompt and edits</span>
                  <strong>{promptEvents.length}.{editEvents.length}</strong>
                </div>
              </div>
              <div className="agent-context-badge-row">
                {promptEvents.slice(0, 6).map((event) => (
                  <span key={event.id} className={`authority-${event.authority}`}>
                    {event.event_kind.replaceAll("_", " ")}
                  </span>
                ))}
                {editEvents.slice(0, 6).map((event) => (
                  <span key={event.id} className={`authority-${event.authority}`}>
                    {event.event_kind.replaceAll("_", " ")}
                  </span>
                ))}
                {promptEvents.length + editEvents.length === 0 && <span>No prompt or edit events.</span>}
              </div>
            </article>

            <article className="agent-context-card agent-context-inspector" aria-label="Content inspector">
              <div className="context-section-head">
                <div>
                  <span>Content inspector</span>
                  <strong>{selectedArtifact?.title ?? "None"}</strong>
                </div>
              </div>
              {selectedArtifact ? (
                <div className="agent-context-inspector-body">
                  <div className="agent-context-badge-row">
                    <span>{selectedArtifact.kind}</span>
                    <span>{selectedArtifact.content_type}</span>
                    {artifactContent?.blob && <span>{artifactContent.blob.redaction_status.replaceAll("_", " ")}</span>}
                    {artifactContent?.blob && <span>{artifactContent.blob.encryption_status.replaceAll("_", " ")}</span>}
                  </div>
                  <small>{selectedArtifact.path ?? selectedArtifact.uri ?? selectedArtifact.id}</small>
                  {artifactContentLoading && <div className="outline-empty">Loading artifact content.</div>}
                  {artifactContentError && (
                    <div className="outline-empty">Content requires maintainer access or is no longer retained.</div>
                  )}
                  {!artifactContentLoading && !artifactContentError && artifactContent?.text && (
                    <pre>{artifactContent.text}</pre>
                  )}
                  {!artifactContentLoading && !artifactContentError && artifactContent && !artifactContent.text && (
                    <div className="outline-empty">Metadata-only artifact. Text content was binary, oversized, or purged.</div>
                  )}
                </div>
              ) : (
                <div className="outline-empty">Select an event artifact to inspect retained content.</div>
              )}
            </article>
          </div>

          <div className="agent-context-timeline" aria-label="Active context timeline">
            {events.slice().reverse().slice(0, 20).map((event) => {
              const artifact = artifacts.find((item) => item.id === event.artifact_id);
              return (
                <article key={event.id} className={`agent-context-event authority-${event.authority}`}>
                  <span>{event.event_kind.replaceAll("_", " ")}</span>
                  <strong>{event.summary}</strong>
                  <small>
                    {event.authority.replaceAll("_", " ")}
                    {artifact ? ` / ${artifact.path ?? artifact.title}` : ""}
                  </small>
                  {artifact && (
                    <button
                      type="button"
                      className="agent-context-artifact-button"
                      aria-pressed={artifact.id === selectedArtifactId}
                      onClick={() => onSelectArtifact(artifact.id === selectedArtifactId ? undefined : artifact.id)}
                    >
                      Inspect artifact
                    </button>
                  )}
                </article>
              );
            })}
            {!loading && events.length === 0 && <div className="outline-empty">No active context events yet.</div>}
          </div>
        </section>
      </div>
    </section>
  );
}

function SettingsWorkspace({
  providerList,
  selectedAiProvider,
  selectedAiProviderId,
  selectedProviderStatus,
  selectedProviderHasSavedKey,
  providerApiKey,
  saveProviderPending,
  clearProviderPending,
  llmEnabled,
  autoCommitThreshold,
  updateSettingsPending,
  onProviderChange,
  onProviderApiKeyChange,
  onSaveProviderKey,
  onClearProviderKey,
  onLlmEnabledChange,
  onAutoCommitThresholdChange,
  onSaveSettings
}: {
  providerList: ApiProviderDescriptor[];
  selectedAiProvider?: ApiProviderDescriptor;
  selectedAiProviderId: ApiProviderId;
  selectedProviderStatus: string;
  selectedProviderHasSavedKey: boolean;
  providerApiKey: string;
  saveProviderPending: boolean;
  clearProviderPending: boolean;
  llmEnabled: boolean;
  autoCommitThreshold: number;
  updateSettingsPending: boolean;
  onProviderChange: (providerId: ApiProviderId) => void;
  onProviderApiKeyChange: (value: string) => void;
  onSaveProviderKey: () => void;
  onClearProviderKey: () => void;
  onLlmEnabledChange: (enabled: boolean) => void;
  onAutoCommitThresholdChange: (threshold: number) => void;
  onSaveSettings: () => void;
}) {
  const [activeSettingsPage, setActiveSettingsPage] = useState<SettingsPageId>("providers");
  const activePage = SETTINGS_PAGES.find((page) => page.id === activeSettingsPage) ?? SETTINGS_PAGES[0];
  const enabledProviders = providerList.filter((provider) => provider.enabled).length;
  const selectedModel = selectedAiProvider?.default_model ?? "graphview-local-deterministic-v1";
  const selectedCapabilities = selectedAiProvider?.capabilities ?? ["planning", "graph query", "research"];

  return (
    <section className="settings-workspace" aria-label="Settings">
      <aside className="settings-sidebar" aria-label="Settings navigation">
        <div>
          <p className="eyebrow">Settings</p>
          <strong>Workspace</strong>
          <span>Providers, credentials, automation, and runtime defaults.</span>
        </div>
        <nav className="settings-nav" role="tablist" aria-label="Settings pages">
          {SETTINGS_PAGES.map((page) => (
            <button
              type="button"
              role="tab"
              aria-selected={page.id === activeSettingsPage}
              key={page.id}
              onClick={() => setActiveSettingsPage(page.id)}
            >
              <strong>{page.label}</strong>
              <span>{page.summary}</span>
            </button>
          ))}
        </nav>
        <div className="settings-sidebar-status" aria-label="Settings status">
          <SettingsStat label="Default" value={selectedAiProvider?.label ?? "Graphview Local"} />
          <SettingsStat label="Enabled" value={enabledProviders.toString()} />
        </div>
      </aside>

      <div className="settings-page-main">
        <div className="settings-page-head">
          <div>
            <p className="eyebrow">Settings / {activePage.label}</p>
            <h2>{activePage.label}</h2>
            <span>{activePage.summary}</span>
          </div>
          <div className="settings-stat-strip" aria-label="Provider settings status">
            <SettingsStat label="Provider" value={selectedAiProvider?.label ?? "Graphview Local"} />
            <SettingsStat label="Credential" value={selectedProviderStatus} />
            <SettingsStat label="Extraction" value={llmEnabled ? "On" : "Off"} />
          </div>
        </div>

        <div className="settings-page-body">
          {activeSettingsPage === "providers" && (
            <section className="settings-section settings-provider-section" aria-label="Provider catalog">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Providers</p>
                  <h3>Model routing</h3>
                </div>
                <span className="settings-status-pill">{selectedProviderStatus}</span>
              </div>
              <div className="settings-provider-grid">
                {providerList.map((provider) => (
                  <button
                    className="provider-status-card"
                    type="button"
                    aria-pressed={provider.id === selectedAiProviderId}
                    key={provider.id}
                    onClick={() => onProviderChange(provider.id)}
                  >
                    <span className={provider.enabled ? "is-enabled" : ""}>{provider.enabled ? "Enabled" : "Not configured"}</span>
                    <strong>{provider.label}</strong>
                    <small>{provider.default_model}</small>
                  </button>
                ))}
              </div>
            </section>
          )}

          {activeSettingsPage === "credentials" && (
            <section className="settings-section settings-form-section" aria-label="Provider credentials">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Credentials</p>
                  <h3>Provider access</h3>
                </div>
                <span className="settings-status-pill">{selectedProviderStatus}</span>
              </div>
              <ProviderCredentialPanel
                providerList={providerList}
                selectedAiProvider={selectedAiProvider}
                selectedAiProviderId={selectedAiProviderId}
                selectedProviderHasSavedKey={selectedProviderHasSavedKey}
                providerApiKey={providerApiKey}
                saveProviderPending={saveProviderPending}
                clearProviderPending={clearProviderPending}
                onProviderChange={onProviderChange}
                onProviderApiKeyChange={onProviderApiKeyChange}
                onSaveProviderKey={onSaveProviderKey}
                onClearProviderKey={onClearProviderKey}
              />
            </section>
          )}

          {activeSettingsPage === "automation" && (
            <section className="settings-section settings-form-section" aria-label="Automation settings">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Automation</p>
                  <h3>Extraction and review rules</h3>
                </div>
              </div>
              <AutomationSettingsPanel
                llmEnabled={llmEnabled}
                autoCommitThreshold={autoCommitThreshold}
                updateSettingsPending={updateSettingsPending}
                onLlmEnabledChange={onLlmEnabledChange}
                onAutoCommitThresholdChange={onAutoCommitThresholdChange}
                onSaveSettings={onSaveSettings}
              />
            </section>
          )}

          {activeSettingsPage === "runtime" && (
            <section className="settings-section settings-runtime-section" aria-label="Runtime defaults">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Runtime</p>
                  <h3>Defaults and guardrails</h3>
                </div>
              </div>
              <div className="settings-readout-grid">
                <SettingsReadout label="Runtime model" value={selectedModel} detail="Used for planning, graph Q&A, and research runs." />
                <SettingsReadout label="Credential source" value={selectedProviderStatus} detail="Reflects saved provider credential state." />
                <SettingsReadout label="Auto-commit" value={autoCommitThreshold.toFixed(2)} detail="Minimum confidence before automatic graph commits." />
                <SettingsReadout label="Extraction" value={llmEnabled ? "LLM-assisted" : "Deterministic"} detail="Controls connector and ingestion proposal generation." />
              </div>
            </section>
          )}

          {activeSettingsPage === "capabilities" && (
            <section className="settings-section settings-capability-section" aria-label="Selected provider capabilities">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Capabilities</p>
                  <h3>{selectedAiProvider?.label ?? "Graphview Local"}</h3>
                </div>
              </div>
              <div className="settings-capability-list">
                {selectedCapabilities.map((capability) => (
                  <span key={capability}>{capability.replaceAll("_", " ")}</span>
                ))}
              </div>
              <div className="settings-provider-matrix">
                {providerList.map((provider) => (
                  <article key={provider.id}>
                    <span>{provider.enabled ? "Enabled" : "Needs setup"}</span>
                    <strong>{provider.label}</strong>
                    <small>{provider.capabilities.map((capability) => capability.replaceAll("_", " ")).join(" / ")}</small>
                  </article>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </section>
  );
}

function ProviderCredentialPanel({
  providerList,
  selectedAiProvider,
  selectedAiProviderId,
  selectedProviderHasSavedKey,
  providerApiKey,
  saveProviderPending,
  clearProviderPending,
  onProviderChange,
  onProviderApiKeyChange,
  onSaveProviderKey,
  onClearProviderKey
}: {
  providerList: ApiProviderDescriptor[];
  selectedAiProvider?: ApiProviderDescriptor;
  selectedAiProviderId: ApiProviderId;
  selectedProviderHasSavedKey: boolean;
  providerApiKey: string;
  saveProviderPending: boolean;
  clearProviderPending: boolean;
  onProviderChange: (providerId: ApiProviderId) => void;
  onProviderApiKeyChange: (value: string) => void;
  onSaveProviderKey: () => void;
  onClearProviderKey: () => void;
}) {
  const selectedCredentialStatus =
    selectedAiProviderId === "graphview-local"
      ? "No key required"
      : selectedProviderHasSavedKey
        ? "Saved key"
        : selectedAiProvider?.configured
          ? "Environment key"
          : "Needs key";
  const credentialCopy = providerCredentialCopy[selectedAiProviderId];
  const selectedModels =
    selectedAiProvider?.models?.length
      ? selectedAiProvider.models
      : [
          {
            id: selectedAiProvider?.default_model ?? "graphview-local-deterministic-v1",
            label: selectedAiProvider?.default_model ?? "graphview-local-deterministic-v1",
            default: true,
            capabilities: selectedAiProvider?.capabilities ?? []
          }
        ];
  const selectedDefaultModel = selectedModels.find((model) => model.default) ?? selectedModels[0];

  return (
    <div className="credential-settings-grid">
      <div className="credential-provider-grid" aria-label="LLM provider selection">
        {providerList.map((provider) => {
          const providerStatus = provider.id === "graphview-local" ? "No key" : provider.configured ? "Configured" : "Needs key";
          return (
            <button
              className="credential-provider-card"
              type="button"
              aria-pressed={provider.id === selectedAiProviderId}
              key={provider.id}
              onClick={() => onProviderChange(provider.id)}
            >
              <span className={provider.configured ? "is-configured" : ""}>{providerStatus}</span>
              <strong>{provider.label}</strong>
              <small>{provider.default_model}</small>
            </button>
          );
        })}
      </div>

      <div className="credential-detail-panel">
        <div className="credential-detail-head">
          <div>
            <p className="eyebrow">Selected provider</p>
            <h4>{selectedAiProvider?.label ?? "Graphview Local"}</h4>
            <span>{credentialCopy.detail}</span>
          </div>
          <strong>{selectedCredentialStatus}</strong>
        </div>

        <div className="credential-summary-row" aria-label="Selected provider details">
          <div>
            <span>Default model</span>
            <strong>{selectedDefaultModel.label}</strong>
          </div>
          <div>
            <span>Credential source</span>
            <strong>{credentialCopy.source}</strong>
          </div>
        </div>

        <div className="credential-model-list" aria-label={`${selectedAiProvider?.label ?? "Provider"} model catalog`}>
          {selectedModels.map((model) => (
            <span key={model.id}>
              <strong>{model.label}</strong>
              <small>{model.default ? "Default" : model.capabilities.map((capability) => capability.replaceAll("_", " ")).join(" / ")}</small>
            </span>
          ))}
        </div>

        {selectedAiProviderId === "graphview-local" ? (
          <div className="settings-callout credential-callout">
            <strong>Graphview Local</strong>
            <span>Runs without external credentials and remains available when cloud providers are not configured.</span>
          </div>
        ) : (
          <div className="credential-key-panel">
            <label>
              {credentialCopy.secretLabel}
              <input
                type="password"
                value={providerApiKey}
                autoComplete="off"
                aria-label={credentialCopy.secretLabel}
                placeholder={selectedAiProvider?.configured ? `${selectedAiProvider.label} key configured` : credentialCopy.placeholder}
                onChange={(event) => onProviderApiKeyChange(event.target.value)}
              />
            </label>
            <div className="credential-key-actions">
              <button className="provider-save-settings" type="button" disabled={saveProviderPending || !providerApiKey.trim()} onClick={onSaveProviderKey}>
                Save key
              </button>
              <button type="button" disabled={clearProviderPending || !selectedProviderHasSavedKey} onClick={onClearProviderKey}>
                Clear key
              </button>
            </div>
            <small>Saving sets {selectedAiProvider?.label ?? "this provider"} as the default LLM provider.</small>
          </div>
        )}
      </div>
    </div>
  );
}

function AutomationSettingsPanel({
  llmEnabled,
  autoCommitThreshold,
  updateSettingsPending,
  onLlmEnabledChange,
  onAutoCommitThresholdChange,
  onSaveSettings
}: {
  llmEnabled: boolean;
  autoCommitThreshold: number;
  updateSettingsPending: boolean;
  onLlmEnabledChange: (enabled: boolean) => void;
  onAutoCommitThresholdChange: (threshold: number) => void;
  onSaveSettings: () => void;
}) {
  return (
    <div className="settings-form-grid">
      <label className="settings-toggle-row">
        <input type="checkbox" checked={llmEnabled} onChange={(event) => onLlmEnabledChange(event.target.checked)} />
        <span>
          <strong>LLM extraction</strong>
          <small>Use the selected provider to generate richer graph proposals during ingestion.</small>
        </span>
      </label>
      <label>
        Auto-commit threshold
        <input
          type="number"
          min="0"
          max="1"
          step="0.01"
          value={autoCommitThreshold}
          onChange={(event) => onAutoCommitThresholdChange(Number(event.target.value))}
        />
      </label>
      <button className="provider-save-settings" type="button" disabled={updateSettingsPending} onClick={onSaveSettings}>
        Save automation
      </button>
    </div>
  );
}

function SettingsStat({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <strong>{value}</strong>
      {label}
    </span>
  );
}

function SettingsReadout({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function PlanningWorkspace({
  goal,
  message,
  providerList,
  selectedSession,
  sessions,
  createPending,
  sendPending,
  onGoalChange,
  onMessageChange,
  onCreateSession,
  onSendMessage,
  onSelectSession,
  onOpenSettings,
  onRunResearch
}: {
  goal: string;
  message: string;
  providerList: ApiProviderDescriptor[];
  selectedSession?: ApiPlanningSession;
  sessions: ApiPlanningSession[];
  createPending: boolean;
  sendPending: boolean;
  onGoalChange: (value: string) => void;
  onMessageChange: (value: string) => void;
  onCreateSession: () => void;
  onSendMessage: () => void;
  onSelectSession: (id: string) => void;
  onOpenSettings: () => void;
  onRunResearch: (query: string) => void;
}) {
  const buildSpec = selectedSession?.build_spec;
  const openQuestions = buildSpec?.spec.open_questions ?? [];
  const researchTasks = buildSpec?.spec.research_tasks ?? [];
  const topics = buildSpec?.spec.topics ?? [];

  return (
    <section className="planning-workspace" aria-label="Planning Mode">
      <aside className="panel planning-rail" aria-label="Planning sessions">
        <div className="panel-head planning-rail-head">
          <span>
            Planning
            <small>{sessions.length} session{sessions.length === 1 ? "" : "s"}</small>
          </span>
          <button type="button" disabled={createPending || !goal.trim()} onClick={onCreateSession}>New</button>
        </div>
        <div className="planning-view-tabs" role="tablist" aria-label="Planning view">
          <button type="button" role="tab" aria-selected="true">
            Sessions
          </button>
          <button type="button" role="tab" aria-selected="false" onClick={onOpenSettings}>
            Settings
          </button>
        </div>
        <div className="planning-session-list">
          {sessions.map((session) => (
            <button
              className="planning-session-row"
              key={session.id}
              type="button"
              aria-pressed={session.id === selectedSession?.id}
              onClick={() => onSelectSession(session.id)}
            >
              <strong>{session.title}</strong>
              <span>{session.messages.length} turns / {session.lens}</span>
            </button>
          ))}
          {sessions.length === 0 && <span className="source-content-empty">No planning sessions yet.</span>}
        </div>
      </aside>

      <section className="panel planning-chat" aria-label="Planning Mode conversation">
	        <div className="planning-chat-head">
	          <div>
	            <p className="eyebrow">Planning Mode</p>
	            <h2>{selectedSession?.title ?? "New graph plan"}</h2>
	          </div>
	        </div>
        <label className="planning-goal">
          Goal
          <textarea value={goal} onChange={(event) => onGoalChange(event.target.value)} />
        </label>
        <div className="planning-thread" aria-label="Planning conversation messages">
          {(selectedSession?.messages ?? []).map((item) => (
            <article className={`planning-message planning-message-${item.role}`} key={item.id}>
              <span>{item.role}</span>
              <p>{item.content}</p>
              {planningMessageToolCalls(item).length > 0 && (
                <div className="planning-tool-stack" aria-label="Agent activity">
                  {planningMessageToolCalls(item).map((toolCall) => (
                    <AgentToolCallCard toolCall={toolCall} key={toolCall.id} />
                  ))}
                </div>
              )}
            </article>
          ))}
          {!selectedSession?.messages.length && (
            <article className="planning-message planning-message-system">
              <span>system</span>
              <p>No planning turns yet.</p>
            </article>
          )}
        </div>
        <form
          className="planning-composer"
          onSubmit={(event) => {
            event.preventDefault();
            if (message.trim()) onSendMessage();
          }}
        >
          <input value={message} onChange={(event) => onMessageChange(event.target.value)} placeholder="Ask the agent to read, research, or plan" />
          <button type="submit" disabled={sendPending || !message.trim()}>Send</button>
          <button type="button" disabled={!goal.trim()} onClick={() => onRunResearch(goal)}>Research</button>
        </form>
      </section>

      <aside className="panel planning-preview" aria-label="Artifact Preview">
        <div className="panel-head">
          <span>Artifact Preview</span>
          <strong>{buildSpec?.status ?? "draft"}</strong>
	        </div>
	        <div className="planning-preview-body">
	          <section className="blueprint-panel" aria-label="AI-native graph blueprint">
	            <div className="blueprint-head">
	              <div>
	                <p className="eyebrow">AI-native blueprint</p>
	                <strong>{buildSpec?.title ?? selectedSession?.title ?? "Draft graph"}</strong>
	              </div>
	              <span>{topics.length} topics / {openQuestions.length} questions / {researchTasks.length} tasks</span>
	            </div>
	            <BlueprintMap topics={topics} openQuestions={openQuestions} researchTasks={researchTasks} />
	            <div className="blueprint-lifecycle" aria-label="Graph build lifecycle">
	              <span>Plan</span>
	              <span>Research</span>
	              <span>Propose</span>
	              <span>Review</span>
	            </div>
	          </section>
	          <section>
	            <p className="eyebrow">Providers</p>
            <div className="provider-strip">
              {providerList.map((provider) => (
                <span className={provider.enabled ? "is-enabled" : ""} key={provider.id}>
                  {provider.label}
                </span>
              ))}
            </div>
          </section>
          <section>
            <p className="eyebrow">Topics</p>
            {topics.slice(0, 5).map((topic, index) => (
              <div className="preview-line" key={`${topic.name}-${index}`}>
                <strong>{topic.name ?? "Topic"}</strong>
                <span>{topic.priority ?? "review"}</span>
              </div>
            ))}
            {topics.length === 0 && <span className="source-content-empty">Build spec topics will appear here.</span>}
          </section>
          <section>
            <p className="eyebrow">Open questions</p>
            {openQuestions.slice(0, 4).map((question) => (
              <div className="preview-line" key={question}>
                <span>{question}</span>
              </div>
            ))}
          </section>
          <section>
            <p className="eyebrow">Research tasks</p>
            {researchTasks.slice(0, 4).map((task, index) => (
              <button className="preview-line preview-action" type="button" key={`${task.query}-${index}`} onClick={() => task.query && onRunResearch(task.query)}>
                <strong>{task.query ?? "Research task"}</strong>
                <span>{task.source_policy ?? "mixed"}</span>
              </button>
            ))}
            {researchTasks.length === 0 && (
              <button className="preview-line preview-action" type="button" onClick={() => onRunResearch(goal)}>
                <strong>Run seed research</strong>
                <span>mixed</span>
              </button>
            )}
          </section>
        </div>
      </aside>
    </section>
  );
}

function planningMessageToolCalls(message: ApiPlanningMessage): ApiAgentToolCall[] {
  if (message.role !== "assistant") return [];
  const metadata = isRecord(message.metadata) ? message.metadata : {};
  const buildSpec = isRecord(metadata.buildSpec) ? metadata.buildSpec : undefined;
  if (!buildSpec) return [];
  const openQuestions = Array.isArray(buildSpec.open_questions) ? buildSpec.open_questions : [];
  const researchTasks = Array.isArray(buildSpec.research_tasks) ? buildSpec.research_tasks : [];
  const topics = Array.isArray(buildSpec.topics) ? buildSpec.topics : [];
  const calls: ApiAgentToolCall[] = [
    {
      id: `${message.id}-graph-query`,
      kind: "graph_query",
      input: { message_id: message.id },
      status: "succeeded",
      citations: [],
      affected_graph_ids: [],
      summary: `Mapped ${topics.length} topics and ${openQuestions.length} open questions.`
    }
  ];
  if (researchTasks.length > 0) {
    calls.push({
      id: `${message.id}-research`,
      kind: "research_run",
      input: { tasks: researchTasks.slice(0, 3) },
      status: "pending_review",
      citations: [],
      affected_graph_ids: [],
      summary: `${researchTasks.length} research task${researchTasks.length === 1 ? "" : "s"} ready for review.`
    });
  }
  calls.push({
    id: `${message.id}-proposal`,
    kind: "proposal_create",
    input: { artifact: "graph_build_spec" },
    status: "pending_review",
    citations: [],
    affected_graph_ids: [],
    summary: "Graph build spec is available as a reviewable artifact."
  });
  return calls;
}

function AgentToolCallCard({ toolCall }: { toolCall: ApiAgentToolCall }) {
  return (
    <article className={`agent-tool-card agent-tool-${toolCall.status}`}>
      <div>
        <span>{toolKindLabel(toolCall.kind)}</span>
        <strong>{toolStatusLabel(toolCall.status)}</strong>
      </div>
      <p>{toolCall.summary ?? "Agent activity recorded."}</p>
      <footer>
        <span>{toolCall.citations.length} citations</span>
        <span>{toolCall.affected_graph_ids.length} affected</span>
      </footer>
    </article>
  );
}

function agentRunToolCalls(run: ApiAgentRun): ApiAgentToolCall[] {
  if (run.tool_calls?.length) return run.tool_calls;
  const status = run.status === "waiting_for_review" ? "pending_review" : run.status === "failed" ? "failed" : "succeeded";
  const kind: AgentToolKind =
    run.kind === "research"
      ? "research_run"
      : run.kind === "action_apply"
        ? "review_action"
        : "graph_query";
  const proposalIds = Array.isArray(run.output.proposal_ids) ? run.output.proposal_ids.filter((item): item is string => typeof item === "string") : [];
  const affectedGraphIds = [
    typeof run.output.source_id === "string" ? run.output.source_id : undefined,
    ...proposalIds
  ].filter((item): item is string => Boolean(item));
  return [
    {
      id: `${run.id}-tool`,
      kind,
      input: {},
      status,
      citations: Array.isArray(run.output.citations) ? run.output.citations as ApiAgentCitation[] : [],
      affected_graph_ids: affectedGraphIds,
      resulting_proposal_id: proposalIds[0],
      summary:
        typeof run.output.answer === "string"
          ? run.output.answer
          : typeof run.output.message === "string"
            ? run.output.message
            : `${toolKindLabel(kind)} completed.`
    }
  ];
}

function toolKindLabel(kind: AgentToolKind) {
  if (kind === "graph_query") return "Graph query";
  if (kind === "source_search") return "Source search";
  if (kind === "source_open") return "Source read";
  if (kind === "research_run") return "Research";
  if (kind === "proposal_create") return "Graph proposal";
  if (kind === "review_action") return "Review action";
  if (kind === "connector_sync") return "Connector sync";
  return "Graph layout";
}

function toolStatusLabel(status: ApiAgentToolCall["status"]) {
  if (status === "pending_review") return "Review";
  if (status === "running") return "Running";
  if (status === "succeeded") return "Done";
  if (status === "failed") return "Failed";
  return "Blocked";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function viewModeLabel(mode: GraphViewMode) {
  if (mode === "overview") return "Overview";
  if (mode === "focus") return "Focus";
  if (mode === "evidence") return "Evidence";
  if (mode === "attention") return "Attention";
  return "Review";
}

function DockIcon({
  kind
}: {
  kind: GraphViewMode | GraphLayoutMode | "sources" | "fit";
}) {
  if (kind === "overview") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <circle cx="7" cy="7" r="2.5" />
        <circle cx="17" cy="7" r="2.5" />
        <circle cx="12" cy="17" r="2.5" />
        <path d="M9 8.5 11 14" />
        <path d="m15 8.5-2 5.5" />
        <path d="M9.5 7h5" />
      </svg>
    );
  }
  if (kind === "focus") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 3v4" />
        <path d="M12 17v4" />
        <path d="M3 12h4" />
        <path d="M17 12h4" />
      </svg>
    );
  }
  if (kind === "evidence" || kind === "sources") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M6 4h9l3 3v13H6Z" />
        <path d="M14 4v4h4" />
        <path d="M8.5 12h7" />
        <path d="M8.5 16h5" />
      </svg>
    );
  }
  if (kind === "review") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M7 5h10" />
        <path d="M6 8h12v12H6Z" />
        <path d="m8.5 14 2 2 5-5" />
      </svg>
    );
  }
  if (kind === "attention") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M12 3v5" />
        <path d="M12 16v5" />
        <path d="M4 12h5" />
        <path d="M15 12h5" />
        <circle cx="12" cy="12" r="3" />
        <path d="m6 6 3 3" />
        <path d="m18 6-3 3" />
      </svg>
    );
  }
  if (kind === "radial") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="2.5" />
        <circle cx="6" cy="6" r="2" />
        <circle cx="18" cy="6" r="2" />
        <circle cx="6" cy="18" r="2" />
        <circle cx="18" cy="18" r="2" />
        <path d="M10.5 10.5 7.5 7.5" />
        <path d="m13.5 10.5 3-3" />
        <path d="m10.5 13.5-3 3" />
        <path d="m13.5 13.5 3 3" />
      </svg>
    );
  }
  if (kind === "arc") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M4 18c3-8 13-8 16 0" />
        <circle cx="6" cy="17" r="2" />
        <circle cx="12" cy="10" r="2" />
        <circle cx="18" cy="17" r="2" />
      </svg>
    );
  }
  if (kind === "fit") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M8 4H4v4" />
        <path d="M16 4h4v4" />
        <path d="M8 20H4v-4" />
        <path d="M16 20h4v-4" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
      <path d="M4 12h16" />
      <circle cx="7" cy="12" r="2" />
      <circle cx="17" cy="12" r="2" />
    </svg>
  );
}

function GraphPicker({
  graphViews,
  open,
  selectedGraphId,
  onOpenChange,
  onSelect
}: {
  graphViews: ApiGraphView[];
  open: boolean;
  selectedGraphId: string;
  onOpenChange: (open: boolean) => void;
  onSelect: (graphId: string) => void;
}) {
  const selectedGraphView = graphViews.find((view) => view.id === selectedGraphId) ?? graphViews[0];
  const selectedMeta = selectedGraphView
    ? `${selectedGraphView.node_count} nodes / ${selectedGraphView.source_count} sources`
    : "No graph selected";

  return (
    <div className={`graph-picker ${open ? "is-open" : ""}`}>
      <button
        className="graph-picker-trigger"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        <span className="graph-picker-kicker">Graph</span>
        <span className="graph-picker-title">{selectedGraphView?.label ?? "Select graph"}</span>
        <span className="graph-picker-meta">{selectedMeta}</span>
        <span className="graph-picker-chevron" aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="graph-picker-menu" role="listbox" aria-label="Knowledge graph selection">
          {graphViews.map((view) => (
            <button
              className="graph-picker-option"
              key={view.id}
              type="button"
              role="option"
              aria-selected={view.id === selectedGraphId}
              onClick={() => onSelect(view.id)}
            >
              <span>
                <strong>{view.label}</strong>
                <small>{view.description ?? `${view.node_count} nodes and ${view.edge_count} links`}</small>
              </span>
              <em>{view.kind === "scope" ? "Scope" : view.id === GENERAL_GRAPH_VIEW_ID ? "General" : "Graph"}</em>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ensureGeneralGraphView(views: ApiGraphView[], fallbackView?: ApiGraphView): ApiGraphView[] {
  const generalView: ApiGraphView = {
    id: GENERAL_GRAPH_VIEW_ID,
    project_id: GENERAL_GRAPH_VIEW_ID,
    label: "General Knowledge Graph",
    description: "All reviewed sources, scopes, planning sessions, and graph data unified into one knowledge graph.",
    kind: "project",
    source_ids: [],
    node_count: 0,
    edge_count: 0,
    source_count: 0,
    pending_proposal_count: 0
  };
  const seedViews = fallbackView && views.length === 0 ? [fallbackView] : views;
  const normalized = seedViews.map((view) =>
    view.id === GENERAL_GRAPH_VIEW_ID
      ? {
          ...view,
          label: "General Knowledge Graph",
          description: generalView.description
        }
      : view
  );
  return normalized.some((view) => view.id === GENERAL_GRAPH_VIEW_ID)
    ? normalized
    : [generalView, ...normalized];
}

function normalizeGraph(data: ApiGraph): { project: GraphProject; nodes: ContentNode[]; edges: SemanticEdge[] } {
  return {
    project: {
      id: data.project.id as GraphProjectId,
      name: data.project.name,
      description: data.project.description ?? undefined,
      createdAt: data.project.created_at,
      updatedAt: data.project.updated_at
    },
    nodes: data.nodes.map((node) => ({
      id: node.id as ContentNode["id"],
      projectId: node.project_id as GraphProjectId,
      topicIds: node.topic_ids as ContentNode["topicIds"],
      label: node.label,
      kind: normalizeContentNodeKind(node.kind),
      summary: node.summary ?? undefined,
      metadata: node.metadata ?? {},
      provenance: node.provenance,
      createdAt: node.created_at,
      updatedAt: node.updated_at
    })),
    edges: data.edges.map((edge) => ({
      id: edge.id as SemanticEdge["id"],
      projectId: edge.project_id as GraphProjectId,
      sourceNodeId: edge.source_node_id as ContentNodeId,
      targetNodeId: edge.target_node_id as ContentNodeId,
      relation: edge.relation as SemanticEdge["relation"],
      weight: edge.weight ?? undefined,
      metadata: edge.metadata ?? {},
      provenance: edge.provenance,
      createdAt: edge.created_at,
      updatedAt: edge.updated_at
    }))
  };
}

function apiGraphActivityEvents(response?: ApiGraphActivityResponse): ApiGraphActivityEvent[] {
  return response?.events ?? response?.graph_activity_events ?? [];
}

function apiGraphActivityEventToShared(event: ApiGraphActivityEvent): GraphActivityEvent {
  const payload = event.metadata ?? event.payload ?? {};
  const refs = event.object_refs ?? [];
  const subject = event.subject ?? refs[0] ?? { kind: "graph", id: event.graph_id ?? "project-default", label: "Graph activity" };
  const eventType = event.event_type ?? event.kind ?? "graph.activity";
  const sourceIds = event.source_ids ?? graphActivityIds(refs, "source", payload, "source_id");
  const sourceChunkIds = event.source_chunk_ids ?? graphActivityIds(refs, "chunk", payload, "source_chunk_id");
  const nodeIds = event.node_ids ?? graphActivityIds(refs, "node", payload, "node_id");
  const edgeIds = event.edge_ids ?? graphActivityIds(refs, "edge", payload, "edge_id");
  const proposalIds = event.proposal_ids ?? graphActivityIds(refs, "proposal", payload, "proposal_id");
  const reviewDecisionIds = event.review_decision_ids ?? graphActivityIds(refs, "review", payload, "review_decision_id");
  const agentRunId = event.agent_run_id ?? graphActivityId(refs, "agent_run", payload, "agent_run_id");
  const agentToolCallId = event.agent_tool_call_id ?? stringFromUnknown(payload.agent_tool_call_id);

  return {
    id: event.id as GraphActivityEvent["id"],
    projectId: event.project_id as GraphProjectId,
    graphId: event.graph_id ?? undefined,
    kind: event.kind ?? graphActivityKind(eventType, payload),
    status: event.status ?? graphActivityStatus(eventType, payload),
    subject: {
      kind: graphActivityObjectKind(subject.kind),
      id: subject.id,
      label: subject.label ?? undefined
    },
    actorId: event.actor_id ?? undefined,
    agentRunId: agentRunId as GraphActivityEvent["agentRunId"],
    agentToolCallId,
    sourceIds: sourceIds as GraphActivityEvent["sourceIds"],
    sourceChunkIds: sourceChunkIds as GraphActivityEvent["sourceChunkIds"],
    nodeIds: nodeIds as GraphActivityEvent["nodeIds"],
    edgeIds: edgeIds as GraphActivityEvent["edgeIds"],
    proposalIds: proposalIds as GraphActivityEvent["proposalIds"],
    reviewDecisionIds: reviewDecisionIds as GraphActivityEvent["reviewDecisionIds"],
    citations: (event.citations ?? []).map(apiCitationToShared),
    summary: event.summary,
    metadata: {
      ...payload,
      eventType,
      lenses: event.lenses ?? []
    },
    occurredAt: event.occurred_at ?? event.created_at ?? new Date().toISOString()
  };
}

function graphActivityObjectKind(kind: string): GraphActivityEvent["subject"]["kind"] {
  if (
    kind === "graph" ||
    kind === "node" ||
    kind === "edge" ||
    kind === "source" ||
    kind === "chunk" ||
    kind === "proposal" ||
    kind === "review" ||
    kind === "agent_run" ||
    kind === "tool_call" ||
    kind === "signal" ||
    kind === "observation" ||
    kind === "alert" ||
    kind === "attention" ||
    kind === "owner" ||
    kind === "policy" ||
    kind === "decision" ||
    kind === "action_proposal" ||
    kind === "action_run" ||
    kind === "outcome" ||
    kind === "feedback"
  ) {
    return kind;
  }
  if (kind === "source_chunk") return "chunk";
  if (kind === "review_decision") return "review";
  if (kind === "agent_tool_call") return "tool_call";
  return "graph";
}

function graphActivityKind(eventType: string, payload: Record<string, unknown>): GraphActivityEvent["kind"] {
  if (eventType.includes("signal.")) return "signal_sensed";
  if (eventType.includes("observation.")) return "observation_recorded";
  if (eventType.includes("alert.routed")) return "alert_routed";
  if (eventType.includes("alert.assigned") || eventType.includes("attention.assigned") || eventType.includes("attention.opened")) {
    return "attention_assigned";
  }
  if (eventType.includes("attention.transitioned")) {
    return stringFromUnknown(payload.status) === "reopened" ? "attention_reopened" : "attention_assigned";
  }
  if (eventType.includes("decision.")) return "decision_recorded";
  if (eventType.includes("action.proposed")) return "action_proposed";
  if (eventType.includes("action.approved")) return "action_approved";
  if (eventType.includes("action.rejected")) return "review_rejected";
  if (eventType.includes("action.run.failed")) return "outcome_failed";
  if (eventType.includes("action.run.succeeded")) return "outcome_succeeded";
  if (eventType.includes("action.run")) return "action_running";
  if (eventType.includes("outcome.waiting")) return "outcome_waiting";
  if (eventType.includes("outcome.succeeded") || eventType.includes("outcome.resolved")) return "outcome_succeeded";
  if (eventType.includes("outcome.failed") || eventType.includes("outcome.unresolved")) return "outcome_failed";
  if (eventType.includes("outcome.reopened")) return "attention_reopened";
  if (eventType.includes("feedback.")) return "feedback_applied";
  if (eventType.includes("action_rejected")) return "review_rejected";
  if (eventType.includes("action_applied")) return "review_accepted";
  if (eventType.includes("reviewed")) {
    const decision = stringFromUnknown(payload.decision);
    if (decision === "reject") return "review_rejected";
    if (decision === "edit") return "review_edited";
    if (decision === "defer") return "review_deferred";
    return "review_accepted";
  }
  if (eventType.includes("proposal_ready") || eventType.includes("proposal.created") || eventType.includes("action_proposed")) {
    return "proposal_candidate";
  }
  if (eventType.includes("node_committed") || eventType.includes("edge_committed")) return "review_accepted";
  if (eventType.includes("agent.run")) return "agent_scan";
  if (eventType.includes("research")) return "research_started";
  if (eventType.includes("source") || eventType.includes("sync") || eventType.includes("ingestion")) return "source_incoming";
  return "agent_scan";
}

function graphActivityStatus(eventType: string, payload: Record<string, unknown>): GraphActivityEvent["status"] {
  const status = stringFromUnknown(payload.status);
  if (status === "failed" || eventType.includes("failed")) return "failed";
  if (status === "resolved" || eventType.includes("resolved")) return "succeeded";
  if (status === "reopened" || eventType.includes("reopened")) return "blocked";
  if (status === "cancelled" || eventType.includes("cancelled")) return "cancelled";
  if (status === "blocked") return "blocked";
  if (status === "pending_review" || status === "proposed") return "ready";
  if (status === "waiting_for_review" || eventType.includes("waiting_for_review")) return "ready";
  if (status === "running" || eventType.includes("running")) return "running";
  if (eventType.includes("proposal_ready") || eventType.includes("action_proposed")) return "ready";
  return "succeeded";
}

function graphActivityIds(
  refs: Array<{ kind: string; id: string }>,
  kind: GraphActivityEvent["subject"]["kind"],
  payload: Record<string, unknown>,
  payloadKey: string
): string[] {
  const refIds = refs.filter((ref) => graphActivityObjectKind(ref.kind) === kind).map((ref) => ref.id);
  const payloadIds = stringsFromUnknown(payload[payloadKey]);
  return [...new Set([...refIds, ...payloadIds])];
}

function graphActivityId(
  refs: Array<{ kind: string; id: string }>,
  kind: GraphActivityEvent["subject"]["kind"],
  payload: Record<string, unknown>,
  payloadKey: string
): string | undefined {
  return graphActivityIds(refs, kind, payload, payloadKey)[0];
}

function stringsFromUnknown(value: unknown): string[] {
  if (typeof value === "string" && value) return [value];
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string" && item.length > 0);
  return [];
}

function stringFromUnknown(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function apiSourceToShared(source: ApiSource | Source): Source {
  if ("projectId" in source) return source;
  return {
    id: source.id as Source["id"],
    projectId: "project-default" as GraphProjectId,
    kind: normalizeSourceKind(source.kind),
    title: source.title,
    uri: source.uri ?? undefined,
    connectorKind: source.connector_kind ?? undefined,
    remoteId: source.remote_id ?? undefined,
    remoteParentId: source.remote_parent_id ?? undefined,
    remoteUrl: source.remote_url ?? undefined,
    metadata: source.metadata ?? {},
    staleAt: source.stale_at ?? undefined,
    createdAt: "",
    updatedAt: source.stale_at ?? ""
  };
}

function apiProposalToShared(proposal: ApiProposal): ExtractionProposal {
  return {
    id: proposal.id as ExtractionProposal["id"],
    projectId: "project-default" as GraphProjectId,
    ingestionRunId: "" as ExtractionProposal["ingestionRunId"],
    kind: proposal.kind,
    status: proposal.status as ExtractionProposal["status"],
    proposedValue: proposal.proposed_value,
    confidence: typeof proposal.proposed_value.weight === "number" ? proposal.proposed_value.weight : undefined,
    provenance: [],
    createdAt: ""
  };
}

function apiReviewDecisionToShared(decision: ApiReviewActivity["items"][number]["decision"]): ReviewDecision {
  return {
    id: decision.id as ReviewDecision["id"],
    projectId: "project-default" as GraphProjectId,
    proposalId: "" as ReviewDecision["proposalId"],
    reviewerId: decision.reviewer_id,
    decision: decision.decision,
    decidedAt: decision.decided_at
  };
}

function apiAgentRunToShared(run: ApiAgentRun): SharedAgentRun {
  return {
    id: run.id as SharedAgentRun["id"],
    projectId: "project-default" as GraphProjectId,
    kind: run.kind,
    mode: run.mode ?? "graph",
    status: run.status,
    provider: run.provider,
    model: run.model,
    input: {},
    output: run.output,
    traceId: run.trace_id,
    createdBy: "agent",
    startedAt: "",
    finishedAt: undefined,
    steps: [],
    toolCalls: run.tool_calls?.map(apiAgentToolCallToShared),
    generatedArtifacts: [],
    actionProposals: [],
    planningSessionId: undefined
  };
}

function apiAgentToolCallToShared(toolCall: ApiAgentToolCall): SharedAgentToolCall {
  return {
    id: toolCall.id,
    kind: toolCall.kind,
    input: toolCall.input,
    status: toolCall.status,
    citations: toolCall.citations.map(apiCitationToShared),
    affectedGraphIds: toolCall.affected_graph_ids,
    resultingProposalId: toolCall.resulting_proposal_id as SharedAgentToolCall["resultingProposalId"],
    summary: toolCall.summary ?? undefined
  };
}

function apiCitationToShared(citation: ApiAgentCitation): AgentCitation {
  return {
    id: citation.id,
    label: citation.label,
    sourceId: citation.source_id as AgentCitation["sourceId"],
    sourceTitle: citation.source_title ?? undefined,
    sourceChunkId: citation.source_chunk_id as AgentCitation["sourceChunkId"],
    nodeId: citation.node_id as AgentCitation["nodeId"],
    proposalId: citation.proposal_id as AgentCitation["proposalId"],
    locator: citation.locator ?? undefined,
    quote: citation.quote ?? undefined,
    url: citation.url ?? undefined,
    confidence: citation.confidence ?? undefined
  };
}

function normalizeExtractionLens(data: ApiExtractionLens): ExtractionLensDescriptor {
  return {
    id: data.id,
    label: data.label,
    summary: data.summary,
    defaultProposalLimit: data.default_proposal_limit,
    sourceKinds: data.source_kinds,
    primaryNodeKinds: data.primary_node_kinds.map(normalizeContentNodeKind),
    provenanceFields: data.provenance_fields
  };
}

function normalizeGraphLens(data: ApiGraphLens): GraphLensDescriptor {
  return {
    id: data.id,
    label: data.label,
    summary: data.summary,
    activeByDefault: data.active_by_default
  };
}

function GraphLensIcon({ lensId }: { lensId: GraphLensId }) {
  if (lensId === "all") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <circle cx="7" cy="7" r="3" />
        <circle cx="17" cy="7" r="3" />
        <circle cx="12" cy="17" r="3" />
        <path d="M9.5 8.5 11 14" />
        <path d="m14.5 8.5-1.5 5.5" />
        <path d="M10 7h4" />
      </svg>
    );
  }
  if (lensId === "engineering") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M8 8 4 12l4 4" />
        <path d="m16 8 4 4-4 4" />
        <path d="m14 5-4 14" />
      </svg>
    );
  }
  if (lensId === "ops") {
    return (
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
        <path d="M8 5h8" />
        <path d="M9 3h6l1 2v2H8V5l1-2Z" />
        <path d="M7 6H5v15h14V6h-2" />
        <path d="m8 13 2 2 5-5" />
        <path d="M8 18h8" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6" />
      <path d="m16 16 4 4" />
      <path d="M9 9h4" />
      <path d="M9 12h3" />
    </svg>
  );
}

function proposalToGraphEdge(
  proposal: ApiProposal,
  projectId: GraphProject["id"],
  nodes: ContentNode[]
): GraphCanvasEdge[] {
  if (proposal.kind !== "semantic_edge" || proposal.status !== "pending_review") return [];
  const sourceNodeId = proposal.proposed_value.sourceNodeId;
  const targetNodeId = proposal.proposed_value.targetNodeId;
  if (!sourceNodeId || !targetNodeId || sourceNodeId === targetNodeId) return [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  if (!nodeIds.has(sourceNodeId as ContentNodeId) || !nodeIds.has(targetNodeId as ContentNodeId)) return [];
  return [
    {
      id: (proposal.proposed_value.id ?? `proposal-${proposal.id}`) as SemanticEdge["id"],
      projectId,
      sourceNodeId: sourceNodeId as ContentNodeId,
      targetNodeId: targetNodeId as ContentNodeId,
      relation: normalizeRelation(proposal.proposed_value.relation),
      weight: proposal.proposed_value.weight,
      provenance: [],
      createdAt: "",
      updatedAt: "",
      reviewStatus: "pending_review"
    }
  ];
}

function normalizeRelation(relation?: string): SemanticEdge["relation"] {
  if (
    relation === "supports" ||
    relation === "contradicts" ||
    relation === "depends_on" ||
    relation === "causes" ||
    relation === "mentions" ||
    relation === "defines" ||
    relation === "relates_to" ||
    relation === "contains" ||
    relation === "part_of" ||
    relation === "references" ||
    relation === "imports" ||
    relation === "implements" ||
    relation === "owned_by" ||
    relation === "has_review_cycle" ||
    relation === "governs"
  ) {
    return relation;
  }
  return "relates_to";
}

function reviewWorkItemLabel(kind: ReviewWorkItemKind | null | undefined, fallback: ApiReviewQueue["items"][number]["action"]) {
  if (kind === "new_entity") return "New entity";
  if (kind === "new_relation") return "New relation";
  if (kind === "source_extraction") return "Source extraction";
  if (kind === "research_result") return "Research result";
  if (kind === "conflicting_fact") return "Conflict";
  if (kind === "stale_source") return "Stale source";
  if (kind === "connector_issue") return "Connector issue";
  if (kind === "planning_action") return "Planning action";
  return fallback.replaceAll("_", " ");
}

function emptyContentExpansionGraph(): ContentExpansionGraph {
  return { nodes: [], edges: [], actions: new Map(), chunkCount: 0, proposalCount: 0, planningCount: 0 };
}

function buildContentExpansionGraph({
  projectId,
  graphNodes,
  graphEdges,
  selectedGraphNode,
  selectedSource,
  contextSource,
  contextBlocks,
  sourceChunks,
  sources,
  proposals,
  reviewActivity,
  reviewQueue,
  planningSessions
}: {
  projectId: GraphProject["id"];
  graphNodes: ContentNode[];
  graphEdges: GraphCanvasEdge[];
  selectedGraphNode?: ContentNode;
  selectedSource?: ApiSource | Source;
  contextSource?: ApiSource | Source;
  contextBlocks: SourceContentBlock[];
  sourceChunks: ApiSourceChunk[];
  sources: Array<ApiSource | Source>;
  proposals: ApiProposal[];
  reviewActivity?: ApiReviewActivity;
  reviewQueue?: ApiReviewQueue;
  planningSessions: ApiPlanningSession[];
}): ContentExpansionGraph {
  const output = emptyContentExpansionGraph();
  const existingNodeIds = new Set<ContentNode["id"]>(graphNodes.map((node) => node.id));
  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const edgeKeys = new Set(graphEdges.map((edge) => `${edge.sourceNodeId}->${edge.targetNodeId}:${edge.relation}`));
  const fallbackAnchor = selectedGraphNode?.id ?? graphNodes[0]?.id;
  const selectedSourceId = selectedSource?.id;
  const contextSourceId = contextSource?.id;

  const sourceAnchor = (sourceId: string | undefined, fallback?: ContentNode["id"]) => {
    if (!sourceId) return fallback ?? fallbackAnchor;
    const sourceNode = graphNodes.find((node) => node.provenance.some((item) => item.sourceId === sourceId));
    return sourceNode?.id ?? fallback ?? fallbackAnchor;
  };

  const addNode = (
    role: ContentExpansionRole,
    stableId: string,
    label: string,
    kind: ContentNodeKind,
    summary: string,
    action?: ContentExpansionAction,
    metadata: Record<string, unknown> = {}
  ) => {
    const nodeId = contentExpansionNodeId(role, stableId);
    if (existingNodeIds.has(nodeId)) return nodeId;
    existingNodeIds.add(nodeId);
    output.nodes.push({
      id: nodeId,
      projectId,
      topicIds: [],
      label: truncatePlainLabel(label, 72),
      kind,
      summary,
      metadata: {
        ...metadata,
        contentExpansion: {
          role,
          stableId
        }
      },
      provenance: [],
      createdAt: "",
      updatedAt: ""
    });
    if (action) output.actions.set(nodeId, action);
    return nodeId;
  };

  const addEdge = (sourceNodeId: ContentNode["id"] | undefined, targetNodeId: ContentNode["id"], relation: SemanticEdge["relation"]) => {
    if (!sourceNodeId || sourceNodeId === targetNodeId) return;
    const edgeKey = `${sourceNodeId}->${targetNodeId}:${relation}`;
    if (edgeKeys.has(edgeKey)) return;
    edgeKeys.add(edgeKey);
    output.edges.push({
      id: contentExpansionEdgeId(sourceNodeId, targetNodeId, relation),
      projectId,
      sourceNodeId,
      targetNodeId,
      relation,
      metadata: {
        contentExpansion: {
          role: "edge"
        }
      },
      provenance: [],
      createdAt: "",
      updatedAt: "",
      reviewStatus: "accepted"
    });
  };

  const addSourceRoot = (source: ApiSource | Source | undefined, anchorId?: ContentNode["id"]) => {
    if (!source) return undefined;
    const sourceNodeId = addNode(
      "source",
      source.id,
      source.title,
      sourceKindToContentKind(normalizeSourceKind(source.kind)),
      `${sourceOriginPrefix(source)}${source.kind} source`.trim(),
      { type: "source", sourceId: source.id, label: source.title },
      { sourceId: source.id }
    );
    addEdge(anchorId ?? sourceAnchor(source.id), sourceNodeId, "contains");
    return sourceNodeId;
  };

  const sourceRoots = new Map<string, ContentNode["id"]>();
  const ensureSourceRoot = (sourceId: string | undefined, preferredAnchor?: ContentNode["id"]) => {
    if (!sourceId) return undefined;
    const existing = sourceRoots.get(sourceId);
    if (existing) return existing;
    const root = addSourceRoot(sourceById.get(sourceId), preferredAnchor);
    if (root) sourceRoots.set(sourceId, root);
    return root;
  };

  const focusedSource = selectedSource ?? contextSource;
  if (focusedSource) {
    ensureSourceRoot(focusedSource.id, selectedGraphNode?.id ?? sourceAnchor(focusedSource.id));
  } else {
    sources.slice(0, 4).forEach((source, index) => {
      ensureSourceRoot(source.id, graphNodes[index % Math.max(1, graphNodes.length)]?.id ?? fallbackAnchor);
    });
  }

  const selectedChunkSourceIds = new Set([selectedSourceId, contextSourceId].filter(Boolean));
  const focusedChunks = sourceChunks
    .filter((chunk) => selectedChunkSourceIds.size === 0 || selectedChunkSourceIds.has(chunk.source_id))
    .sort((left, right) => left.ordinal - right.ordinal || left.id.localeCompare(right.id));
  const chunkCandidates = (focusedChunks.length > 0 ? focusedChunks : sourceChunks).slice(0, selectedSourceId ? 10 : 14);
  for (const chunk of chunkCandidates) {
    const source = sourceById.get(chunk.source_id);
    const sourceRoot = ensureSourceRoot(chunk.source_id, sourceAnchor(chunk.source_id));
    const heading = chunk.heading_path.at(-1) ?? chunk.heading_path[0];
    const label = heading || firstLine(chunk.text) || `${chunk.block_type} ${chunk.ordinal + 1}`;
    const chunkNodeId = addNode(
      "chunk",
      chunk.id,
      label,
      sourceKindToContentKind(normalizeSourceKind(source?.kind)),
      `${chunk.block_type} / ${chunk.locator}\n${truncatePlainLabel(chunk.text, 180)}`,
      source ? { type: "source", sourceId: source.id, label: source.title } : undefined,
      { sourceId: chunk.source_id, chunkId: chunk.id, locator: chunk.locator }
    );
    addEdge(sourceRoot ?? sourceAnchor(chunk.source_id), chunkNodeId, "contains");
    output.chunkCount += 1;
  }

  if (chunkCandidates.length === 0 && focusedSource) {
    contextBlocks.slice(0, 8).forEach((block) => {
      const sourceRoot = ensureSourceRoot(focusedSource.id, selectedGraphNode?.id ?? sourceAnchor(focusedSource.id));
      const label = block.heading_path.at(-1) ?? firstLine(block.text) ?? `${block.block_type} ${block.ordinal + 1}`;
      const blockNodeId = addNode(
        "chunk",
        block.id,
        label,
        sourceKindToContentKind(normalizeSourceKind(focusedSource.kind)),
        `${block.block_type} / ${block.locator}\n${truncatePlainLabel(block.text, 180)}`,
        { type: "source", sourceId: focusedSource.id, label: focusedSource.title },
        { sourceId: focusedSource.id, locator: block.locator }
      );
      addEdge(sourceRoot ?? selectedGraphNode?.id ?? fallbackAnchor, blockNodeId, "contains");
      output.chunkCount += 1;
    });
  }

  const proposalCandidates = [
    ...(reviewQueue?.items.map((item) => item.proposal) ?? []),
    ...proposals.filter((proposal) => proposal.status === "pending_review")
  ]
    .filter(uniqueById)
    .filter((proposal) => proposalMatchesFocus(proposal, selectedGraphNode, selectedSourceId) || !selectedGraphNode)
    .slice(0, selectedGraphNode ? 4 : 6);
  for (const proposal of proposalCandidates) {
    const anchor = proposalAnchor(proposal, graphNodes) ?? selectedGraphNode?.id ?? fallbackAnchor;
    const label = proposal.proposed_value.label ?? proposal.proposed_value.relation ?? "Pending proposal";
    const proposalNodeId = addNode(
      "proposal",
      proposal.id,
      label,
      proposal.kind === "semantic_edge" ? "decision" : normalizeContentNodeKind(proposal.proposed_value.kind),
      `${proposal.kind.replace("_", " ")} / ${proposal.status}`,
      { type: "proposal", proposalId: proposal.id, label },
      { proposalId: proposal.id, status: proposal.status }
    );
    addEdge(anchor, proposalNodeId, proposal.status === "pending_review" ? "has_review_cycle" : "references");
    output.proposalCount += 1;
  }

  for (const item of (reviewActivity?.items ?? []).slice(0, 3)) {
    const label = item.summary || `${item.decision.decision} review`;
    const anchor = item.proposal ? proposalAnchor(item.proposal, graphNodes) : undefined;
    const decisionNodeId = addNode(
      "decision",
      item.decision.id,
      label,
      "decision",
      `${item.decision.decision} by ${item.decision.reviewer_id}`,
      item.proposal ? { type: "proposal", proposalId: item.proposal.id, label } : undefined,
      { proposalId: item.proposal?.id, decisionId: item.decision.id }
    );
    addEdge(anchor ?? selectedGraphNode?.id ?? fallbackAnchor, decisionNodeId, "governs");
  }

  const planningTaskCandidates = planningSessions
    .flatMap((session) => {
      const tasks = session.build_spec?.spec.research_tasks ?? [];
      const questions = session.build_spec?.spec.open_questions ?? [];
      return [
        ...tasks.map((task, index) => ({
          id: `${session.id}-task-${index}`,
          session,
          label: task.query ?? "Research task",
          summary: `${task.priority ?? "review"} / ${task.source_policy ?? "mixed sources"}`
        })),
        ...questions.slice(0, Math.max(0, 3 - tasks.length)).map((question, index) => ({
          id: `${session.id}-question-${index}`,
          session,
          label: question,
          summary: "Open planning question"
        }))
      ];
    })
    .slice(0, 4);
  for (const task of planningTaskCandidates) {
    const taskNodeId = addNode(
      "task",
      task.id,
      task.label,
      "task",
      task.summary,
      { type: "planning", sessionId: task.session.id, label: task.label },
      { planningSessionId: task.session.id }
    );
    addEdge(selectedGraphNode?.id ?? fallbackAnchor, taskNodeId, "contains");
    output.planningCount += 1;
  }

  return output;
}

function contentExpansionNodeId(role: ContentExpansionRole, stableId: string): ContentNode["id"] {
  return `contents-${role}-${stableId.replaceAll(/[^a-zA-Z0-9_-]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 96)}` as ContentNode["id"];
}

function contentExpansionEdgeId(
  sourceNodeId: ContentNode["id"],
  targetNodeId: ContentNode["id"],
  relation: SemanticEdge["relation"]
): SemanticEdge["id"] {
  return `contents-edge-${sourceNodeId}-${targetNodeId}-${relation}`.replaceAll(/[^a-zA-Z0-9_-]+/g, "-").slice(0, 180) as SemanticEdge["id"];
}

function sourceKindToContentKind(kind: SourceKind | undefined): ContentNodeKind {
  if (kind === "markdown") return "markdown";
  if (kind === "url") return "url";
  if (kind === "pdf") return "pdf";
  if (kind === "repository") return "file";
  if (kind === "ops-document") return "ops_document";
  return "text";
}

function firstLine(value: string) {
  return value.split(/\r?\n/).map((line) => line.trim()).find(Boolean);
}

function truncatePlainLabel(value: string, limit: number) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > limit ? `${normalized.slice(0, Math.max(0, limit - 1)).trim()}…` : normalized;
}

function uniqueById<T extends { id: string }>(item: T, index: number, items: T[]) {
  return items.findIndex((candidate) => candidate.id === item.id) === index;
}

function formatShortDate(value?: string | null) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch {
    return value;
  }
}

function proposalMatchesFocus(proposal: ApiProposal, selectedGraphNode: ContentNode | undefined, selectedSourceId: string | undefined) {
  if (!selectedGraphNode && !selectedSourceId) return true;
  if (selectedGraphNode) {
    const proposed = proposal.proposed_value;
    if (proposed.id === selectedGraphNode.id || proposed.sourceNodeId === selectedGraphNode.id || proposed.targetNodeId === selectedGraphNode.id) {
      return true;
    }
    const label = `${proposed.label ?? ""} ${proposed.sourceLabel ?? ""} ${proposed.targetLabel ?? ""}`.toLowerCase();
    if (selectedGraphNode.label && label.includes(selectedGraphNode.label.toLowerCase())) return true;
  }
  if (selectedSourceId) return false;
  return true;
}

function proposalAnchor(proposal: ApiProposal, graphNodes: ContentNode[]) {
  const proposed = proposal.proposed_value;
  const idCandidates = [proposed.id, proposed.sourceNodeId, proposed.targetNodeId].filter(Boolean);
  for (const id of idCandidates) {
    const node = graphNodes.find((candidate) => candidate.id === id);
    if (node) return node.id;
  }
  const labelCandidates = [proposed.label, proposed.sourceLabel, proposed.targetLabel].filter(Boolean).map((label) => String(label).toLowerCase());
  const labelMatch = graphNodes.find((node) => labelCandidates.some((label) => node.label.toLowerCase().includes(label) || label.includes(node.label.toLowerCase())));
  return labelMatch?.id;
}

function asApiProviderId(value: unknown): ApiProviderId | undefined {
  if (value === "graphview-local" || value === "openai" || value === "anthropic" || value === "gemini") {
    return value;
  }
  return undefined;
}

function connectorLabel(kind: ApiConnectorDescriptor["kind"]) {
  return fallbackConnectors.find((connector) => connector.kind === kind)?.label ?? kind;
}

function targetTypeForConnector(kind: ApiConnectorDescriptor["kind"]): ApiConnectorTarget["target_type"] {
  if (kind === "url") return "url";
  if (kind === "repository") return "repository";
  if (kind === "google-workspace") return "folder";
  if (kind === "notion") return "page";
  return "upload";
}

function connectorSyncSettings(
  kind: ApiConnectorDescriptor["kind"],
  title: string,
  content: string,
  remoteId: string,
  llmEnabled: boolean,
  autoCommitThreshold: number
) {
  const base = {
    llm_enabled: llmEnabled,
    auto_commit_threshold: autoCommitThreshold
  };
  if (kind === "url") {
    return {
      ...base,
      uri: remoteId,
      content,
      title
    };
  }
  if (kind === "repository") {
    return {
      ...base,
      content,
      path: remoteId
    };
  }
  if (kind === "google-workspace") {
    return {
      ...base,
      documents: [{ id: remoteId, title, content }]
    };
  }
  if (kind === "notion") {
    return {
      ...base,
      pages: [{ id: remoteId, title, content }]
    };
  }
  return {
    ...base,
    files: [{ id: remoteId, title, content }]
  };
}

function sourceOriginPrefix(source: ApiSource | Source) {
  const connectorKind = sourceConnectorKind(source);
  const apiSource = source as ApiSource;
  const sharedSource = source as Source;
  const staleAt = apiSource.stale_at ?? sharedSource.staleAt;
  return `${connectorKind ? `${connectorKind} / ` : ""}${staleAt ? "stale / " : ""}`;
}

function sourceConnectorKind(source: ApiSource | Source) {
  const apiSource = source as ApiSource;
  const sharedSource = source as Source;
  return apiSource.connector_kind ?? sharedSource.connectorKind;
}

function buildContextSourceBlocks(
  source: ApiSource | Source | undefined,
  focusNode: ContentNode,
  nodes: ContentNode[],
  edges: GraphCanvasEdge[]
): SourceContentBlock[] {
  const sourceId = source?.id;
  const sourceUri = source ? (source as ApiSource).uri ?? (source as Source).uri : undefined;
  const sourceTitle = source?.title ?? "Focused graph item";
  const linkList = sourceUri && /^https?:\/\//.test(sourceUri) ? [sourceUri] : [];
  const sourceNodes = sourceId
    ? nodes.filter((node) => node.provenance.some((item) => item.sourceId === sourceId))
    : [focusNode];
  const orderedNodes = [
    ...sourceNodes.filter((node) => node.id === focusNode.id),
    ...sourceNodes.filter((node) => node.id !== focusNode.id)
  ];
  const baseNodes = orderedNodes.length > 0 ? orderedNodes : [focusNode];

  return baseNodes.map((node, index) => {
    const nodeEdges = edges.filter((edge) => edge.sourceNodeId === node.id || edge.targetNodeId === node.id);
    const mentions = nodeEdges
      .slice(0, 6)
      .flatMap((edge) => {
        const neighborId = edge.sourceNodeId === node.id ? edge.targetNodeId : edge.sourceNodeId;
        const neighbor = nodes.find((candidate) => candidate.id === neighborId);
        return neighbor ? [`${edge.relation}: ${neighbor.label}`] : [];
      });
    const locator = node.provenance.find((item) => !sourceId || item.sourceId === sourceId)?.locator ?? node.kind;
    return {
      id: `context-block-${sourceId ?? "focus"}-${node.id}`,
      heading_path: [sourceTitle, node.kind],
      block_type: node.kind === "document" || node.kind === "decision" ? "heading" : "paragraph",
      ordinal: index,
      text: `${node.label}\n${node.summary ?? "Reviewed graph item."}`,
      links: linkList,
      mentions,
      locator
    };
  });
}

function buildSourceContentText(source: ApiSource | Source | undefined, blocks: SourceContentBlock[]) {
  const title = source?.title ?? "Focused graph item";
  const sourceUri = source ? (source as ApiSource).uri ?? (source as Source).uri : undefined;
  const header = [`# ${title}`, sourceUri ? `Source: ${sourceUri}` : undefined].filter(Boolean).join("\n");
  const body = blocks
    .map((block) => {
      const heading = block.heading_path.length > 0 ? `## ${block.heading_path.join(" / ")}` : "## Content";
      const links = block.links.length > 0 ? `\nLinks: ${block.links.join(", ")}` : "";
      const mentions = block.mentions.length > 0 ? `\nMentions: ${block.mentions.join(", ")}` : "";
      return `${heading}\n${block.text}${links}${mentions}\nLocator: ${block.locator}`;
    })
    .join("\n\n");
  return `${header}\n\n${body}`.trim();
}

async function writeClipboardText(value: string) {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back for embedded browsers that block the async clipboard API.
    }
  }
  const textArea = document.createElement("textarea");
  textArea.value = value;
  textArea.setAttribute("readonly", "true");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  textArea.style.top = "0";
  document.body.append(textArea);
  textArea.focus();
  textArea.select();
  const copied = document.execCommand("copy");
  textArea.remove();
  if (!copied) throw new Error("Copy command failed");
}

function slugify(value: string) {
  return value.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "source-content";
}

function defaultTitleForSourceKind(kind: SourceKind, index: number) {
  if (kind === "repository") return "Repository map";
  if (kind === "ops-document") return "Ops document map";
  if (kind === "url") return "URL source";
  if (kind === "pdf") return "PDF source";
  if (kind === "markdown") return "Research memo";
  return `Source ${index}`;
}

function inferSourceKind(filename: string): SourceKind {
  const lowered = filename.toLowerCase();
  if (lowered.endsWith(".md") || lowered.endsWith(".markdown")) return "markdown";
  if (lowered.endsWith(".pdf")) return "pdf";
  if (/\.(py|ts|tsx|js|mjs|json|yml|yaml|go|rs|java)$/.test(lowered)) return "repository";
  return "text";
}

function sampleContentForSourceKind(kind: SourceKind): string {
  if (kind === "repository") {
    return "App/Sources/AppShell/App.swift\nFeature/Timeline/TimelineView.swift\nPackage.swift\nimport SwiftUI\nimport SwiftData\nfunc registerAppIntents() {}\nIssue #26 tracks Liquid Glass migration.";
  }
  if (kind === "ops-document") {
    return "# iOS 26 Release Checklist\nOwner: Mobile Platform\nReview: each TestFlight train\nPrivacy labels\nApp Review notes\nRollback criteria";
  }
  if (kind === "url") {
    return "https://developer.apple.com/documentation/swiftui";
  }
  return demoDefaultSourceText;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell />
    </QueryClientProvider>
  );
}
