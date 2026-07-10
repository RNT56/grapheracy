import { useMemo, useRef, useState } from "react";
import type { ContentNode, SemanticEdge } from "@graphview/shared-types";

const PAGE_SIZE = 250;

export function AccessibleGraphData({
  nodes,
  edges,
  onSelectNode
}: {
  nodes: ContentNode[];
  edges: SemanticEdge[];
  onSelectNode?: (nodeId: ContentNode["id"]) => void;
}) {
  const [query, setQuery] = useState("");
  const [visibleLimit, setVisibleLimit] = useState(PAGE_SIZE);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const labels = useMemo(() => new Map(nodes.map((node) => [node.id, node.label])), [nodes]);
  const degree = useMemo(() => {
    const counts = new Map(nodes.map((node) => [node.id, 0]));
    for (const edge of edges) {
      counts.set(edge.sourceNodeId, (counts.get(edge.sourceNodeId) ?? 0) + 1);
      counts.set(edge.targetNodeId, (counts.get(edge.targetNodeId) ?? 0) + 1);
    }
    return counts;
  }, [edges, nodes]);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredNodes = useMemo(
    () => normalizedQuery
      ? nodes.filter((node) => `${node.label} ${node.kind} ${node.summary ?? ""}`.toLowerCase().includes(normalizedQuery))
      : nodes,
    [nodes, normalizedQuery]
  );
  const filteredEdges = useMemo(
    () => normalizedQuery
      ? edges.filter((edge) =>
          `${labels.get(edge.sourceNodeId) ?? ""} ${edge.relation} ${labels.get(edge.targetNodeId) ?? ""}`
            .toLowerCase()
            .includes(normalizedQuery)
        )
      : edges,
    [edges, labels, normalizedQuery]
  );
  const visibleNodes = filteredNodes.slice(0, visibleLimit);
  const visibleEdges = filteredEdges.slice(0, visibleLimit);

  return (
    <details className="graph-accessible-data" ref={detailsRef}>
      <summary>Accessible graph data ({nodes.length} nodes, {edges.length} relations)</summary>
      <div className="graph-accessible-tables">
        <label className="graph-accessible-search">
          Filter visible graph data
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setVisibleLimit(PAGE_SIZE);
            }}
          />
        </label>
        <table>
          <caption>Visible graph nodes ({filteredNodes.length} matches)</caption>
          <thead><tr><th>Node</th><th>Kind</th><th>Connections</th></tr></thead>
          <tbody>{visibleNodes.map((node) => (
            <tr key={`accessible-${node.id}`}>
              <td>
                <button
                  type="button"
                  onClick={() => {
                    onSelectNode?.(node.id);
                    detailsRef.current?.removeAttribute("open");
                  }}
                >
                  {node.label}
                </button>
              </td>
              <td>{node.kind}</td><td>{degree.get(node.id)}</td>
            </tr>
          ))}</tbody>
        </table>
        <table>
          <caption>Visible graph relations ({filteredEdges.length} matches)</caption>
          <thead><tr><th>Source</th><th>Relation</th><th>Target</th></tr></thead>
          <tbody>{visibleEdges.map((edge) => (
            <tr key={`accessible-${edge.id}`}>
              <td>{labels.get(edge.sourceNodeId)}</td><td>{edge.relation.replaceAll("_", " ")}</td><td>{labels.get(edge.targetNodeId)}</td>
            </tr>
          ))}</tbody>
        </table>
        {visibleLimit < Math.max(filteredNodes.length, filteredEdges.length) && (
          <button type="button" onClick={() => setVisibleLimit((current) => current + PAGE_SIZE)}>
            Show {Math.min(PAGE_SIZE, Math.max(filteredNodes.length, filteredEdges.length) - visibleLimit)} more rows
          </button>
        )}
      </div>
    </details>
  );
}
