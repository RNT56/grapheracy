import type { ContentNode, SemanticEdge } from "@graphview/shared-types";

interface Props {
  nodes: ContentNode[];
  edges: SemanticEdge[];
}

const positions = [
  { x: 140, y: 150 },
  { x: 410, y: 110 },
  { x: 450, y: 330 },
  { x: 190, y: 360 }
];

export function GraphCanvas({ nodes, edges }: Props) {
  const byId = new Map(nodes.map((node, index) => [node.id, { node, position: positions[index] ?? positions[0] }]));

  return (
    <svg className="graph-canvas" viewBox="0 0 620 460" role="img" aria-label="Prototype-informed graph shell">
      <defs>
        <marker id="arrow" markerHeight="8" markerWidth="8" orient="auto-start-reverse" refX="8" refY="4">
          <path d="M 0 0 L 8 4 L 0 8 z" />
        </marker>
      </defs>
      {edges.map((edge) => {
        const source = byId.get(edge.sourceNodeId);
        const target = byId.get(edge.targetNodeId);
        if (!source || !target) return null;
        return (
          <line
            className="graph-edge"
            key={edge.id}
            x1={source.position.x}
            y1={source.position.y}
            x2={target.position.x}
            y2={target.position.y}
            markerEnd="url(#arrow)"
          />
        );
      })}
      {nodes.map((node, index) => {
        const position = positions[index] ?? positions[0];
        return (
          <g key={node.id} transform={`translate(${position.x} ${position.y})`}>
            <circle className={`graph-node graph-node-${index + 1}`} r="58" />
            <text className="graph-label" textAnchor="middle">
              {node.label.split(" ").map((word, lineIndex) => (
                <tspan key={word} x="0" dy={lineIndex === 0 ? "-0.1em" : "1.1em"}>
                  {word}
                </tspan>
              ))}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
