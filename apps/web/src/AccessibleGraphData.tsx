import type { ContentNode, SemanticEdge } from "@graphview/shared-types";

export function AccessibleGraphData({
  nodes,
  edges,
  onSelectNode
}: {
  nodes: ContentNode[];
  edges: SemanticEdge[];
  onSelectNode?: (nodeId: ContentNode["id"]) => void;
}) {
  const labels = new Map(nodes.map((node) => [node.id, node.label]));
  const degree = new Map(nodes.map((node) => [node.id, 0]));
  for (const edge of edges) {
    degree.set(edge.sourceNodeId, (degree.get(edge.sourceNodeId) ?? 0) + 1);
    degree.set(edge.targetNodeId, (degree.get(edge.targetNodeId) ?? 0) + 1);
  }
  return (
    <details className="graph-accessible-data">
      <summary>Accessible graph data</summary>
      <div className="graph-accessible-tables">
        <table>
          <caption>Visible graph nodes</caption>
          <thead><tr><th>Node</th><th>Kind</th><th>Connections</th></tr></thead>
          <tbody>{nodes.map((node) => (
            <tr key={`accessible-${node.id}`}>
              <td><button type="button" onClick={() => onSelectNode?.(node.id)}>{node.label}</button></td>
              <td>{node.kind}</td><td>{degree.get(node.id)}</td>
            </tr>
          ))}</tbody>
        </table>
        <table>
          <caption>Visible graph relations</caption>
          <thead><tr><th>Source</th><th>Relation</th><th>Target</th></tr></thead>
          <tbody>{edges.map((edge) => (
            <tr key={`accessible-${edge.id}`}>
              <td>{labels.get(edge.sourceNodeId)}</td><td>{edge.relation.replaceAll("_", " ")}</td><td>{labels.get(edge.targetNodeId)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </details>
  );
}
