import { create } from "zustand";
import type { ContentNode, GraphBounds, GraphLensId } from "@graphview/shared-types";

type GraphLayout = "force" | "radial" | "arc";
type GraphDimension = "2d" | "3d";
type GraphView = "overview" | "focus" | "evidence" | "review" | "attention";

interface GraphWorkspaceState {
  selectedGraphLensId: GraphLensId;
  searchText: string;
  graphLayout: GraphLayout;
  graphDimension: GraphDimension;
  graphViewMode: GraphView;
  showContents: boolean;
  fitSequence: number;
  viewportZoom: number;
  viewportBounds: GraphBounds;
  selectedGraphNodeId?: ContentNode["id"];
  selectedSourceId?: string;
  setSelectedGraphLensId: (value: GraphLensId) => void;
  setSearchText: (value: string) => void;
  setGraphLayout: (value: GraphLayout) => void;
  setGraphDimension: (value: GraphDimension) => void;
  setGraphViewMode: (value: GraphView) => void;
  toggleContents: () => void;
  fitGraph: () => void;
  setViewportProjection: (zoom: number, bounds: GraphBounds) => void;
  setSelectedGraphNodeId: (value?: ContentNode["id"]) => void;
  setSelectedSourceId: (value?: string) => void;
}

const requestedLens = typeof window === "undefined"
  ? null
  : new URLSearchParams(window.location.search).get("lens") ?? window.localStorage.getItem("graphview.graphLens");
const initialLens: GraphLensId = ["all", "research", "engineering", "ops"].includes(requestedLens ?? "")
  ? requestedLens as GraphLensId
  : "all";

export const useGraphWorkspaceStore = create<GraphWorkspaceState>((set) => ({
  selectedGraphLensId: initialLens,
  searchText: "",
  graphLayout: "force",
  graphDimension: "2d",
  graphViewMode: "overview",
  showContents: false,
  fitSequence: 0,
  viewportZoom: 0.25,
  viewportBounds: { minX: -1, minY: -1, maxX: 1, maxY: 1 },
  setSelectedGraphLensId: (selectedGraphLensId) => set({ selectedGraphLensId }),
  setSearchText: (searchText) => set({ searchText }),
  setGraphLayout: (graphLayout) => set({ graphLayout }),
  setGraphDimension: (graphDimension) => set({ graphDimension }),
  setGraphViewMode: (graphViewMode) => set({ graphViewMode }),
  toggleContents: () => set((state) => ({ showContents: !state.showContents })),
  fitGraph: () => set((state) => ({ fitSequence: state.fitSequence + 1 })),
  setViewportProjection: (viewportZoom, viewportBounds) => set({ viewportZoom, viewportBounds }),
  setSelectedGraphNodeId: (selectedGraphNodeId) => set({ selectedGraphNodeId }),
  setSelectedSourceId: (selectedSourceId) => set({ selectedSourceId })
}));
