import type { GraphTooltipModel } from "@graphview/shared-types";

export function GraphTooltipLayer({
  tooltip,
  left,
  top,
  placement
}: {
  tooltip: GraphTooltipModel;
  left: number;
  top: number;
  placement: "right" | "left" | "top" | "bottom";
}) {
  return (
    <aside
      className={`graph-tooltip graph-object-tooltip ${tooltip.statuses.map((status) => `is-${status}`).join(" ")}`}
      style={{ left: `${left}%`, top: `${top}%` }}
      data-placement={placement}
      aria-live="polite"
      data-testid="graph-tooltip"
    >
      <header>
        <span>{tooltip.kindLabel}</span>
        <strong>{tooltip.title}</strong>
      </header>
      {tooltip.summary && <p>{tooltip.summary}</p>}
      {tooltip.url && (
        <a
          className="graph-tooltip-source-url"
          data-testid="graph-tooltip-source-url"
          href={tooltip.url}
          target="_blank"
          rel="noreferrer noopener"
        >
          {tooltip.url}
        </a>
      )}
      {tooltip.contains && tooltip.contains.length > 0 && (
        <ul>
          {tooltip.contains.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {tooltip.citations.length > 0 && (
        <footer>
          <span>{tooltip.citations.length} citations</span>
          <span>{tooltip.citations[0].locator ?? tooltip.citations[0].sourceTitle ?? "Graph evidence"}</span>
        </footer>
      )}
    </aside>
  );
}
