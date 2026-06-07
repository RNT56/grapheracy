export const docsAppNavItems = [
  { label: "Start Here", href: "../../docs/00-start-here.md" },
  { label: "Product Goals", href: "../../docs/01-product-goals.md" },
  { label: "Architecture", href: "../../docs/02-architecture.md" },
  { label: "Security", href: "../../docs/03-security.md" },
  { label: "Development", href: "../../docs/04-development.md" },
  { label: "Testing", href: "../../docs/05-testing.md" },
  { label: "Operations", href: "../../docs/06-operations.md" },
  { label: "Agent Workflows", href: "../../docs/07-agent-workflows.md" },
  { label: "Roadmap", href: "../../docs/08-roadmap.md" },
  { label: "Data Schema", href: "../../docs/09-data-schema.md" },
  { label: "User Journeys", href: "../../docs/10-user-journeys-and-value-map.md" },
  { label: "Living Graph UI", href: "../../docs/11-living-graph-ui-vision-and-upgrade-plan.md" },
  { label: "Digital Nervous System", href: "../../docs/12-digital-nervous-system-phase25-plan.md" }
];

export function docsAppRoutes() {
  return docsAppNavItems.map((item) => ({
    ...item,
    route: `/${item.label.toLowerCase().replaceAll(" ", "-")}`
  }));
}
