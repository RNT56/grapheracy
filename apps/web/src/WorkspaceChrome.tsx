import type { GraphLensId } from "@graphview/shared-types";
import type { GraphLayoutMode } from "./GraphCanvas";
import type { ApiGraphView, GraphViewMode } from "./workspaceTypes";

const GENERAL_GRAPH_VIEW_ID = "project-default";

export function MobileNavIcon({ kind }: { kind: "graph" | "sources" | "ask" | "review" }) {
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export function viewModeLabel(mode: GraphViewMode) {
  if (mode === "overview") return "Overview";
  if (mode === "focus") return "Focus";
  if (mode === "evidence") return "Evidence";
  if (mode === "attention") return "Attention";
  return "Review";
}

export function DockIcon({
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

export function GraphPicker({
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

export function GraphLensIcon({ lensId }: { lensId: GraphLensId }) {
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
