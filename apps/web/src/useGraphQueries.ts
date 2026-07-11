import { useQuery } from "@tanstack/react-query";
import type { GraphLensId } from "@graphview/shared-types";
import { fetchJson, graphLensScopedPath, graphScopedPath } from "./apiClient";
import type {
  ApiExtractionLens, ApiGraph, ApiGraphActivityResponse, ApiGraphLens, ApiGraphView, ApiInsights,
  ApiProposal, ApiReviewActivity, ApiReviewDashboard, ApiReviewQueue, ApiSource, ApiSourceChunk,
  ApiSourceReviewCoverage
} from "./workspaceTypes";

export function useGraphQueries({
  selectedGraphId,
  selectedGraphLensId,
  searchText,
  selectedSourceId,
  showContents
}: {
  selectedGraphId: string;
  selectedGraphLensId: GraphLensId;
  searchText: string;
  selectedSourceId?: string;
  showContents: boolean;
}) {
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
    graphViews,
    graph,
    sources,
    proposals,
    reviewQueue,
    reviewDashboard,
    reviewActivity,
    graphActivity,
    sourceReviewCoverage,
    reviewDecisions,
    insights,
    extractionLenses,
    graphLenses,
    selectedSourceChunks,
    contentExpansionChunks
  };
}
