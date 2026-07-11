import type { ContentNode, GraphRenderEdge as GraphCanvasEdge, Source } from "@graphview/shared-types";
import type { ApiSource, SourceContentBlock } from "./workspaceTypes";

export function sourceOriginPrefix(source: ApiSource | Source) {
  const connectorKind = sourceConnectorKind(source);
  const apiSource = source as ApiSource;
  const sharedSource = source as Source;
  const staleAt = apiSource.stale_at ?? sharedSource.staleAt;
  return `${connectorKind ? `${connectorKind} / ` : ""}${staleAt ? "stale / " : ""}`;
}

export function sourceConnectorKind(source: ApiSource | Source) {
  const apiSource = source as ApiSource;
  const sharedSource = source as Source;
  return apiSource.connector_kind ?? sharedSource.connectorKind;
}

export function buildContextSourceBlocks(
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

export function buildSourceContentText(source: ApiSource | Source | undefined, blocks: SourceContentBlock[]) {
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
