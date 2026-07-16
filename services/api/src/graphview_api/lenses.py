EXTRACTION_LENS_IDS = ("research", "engineering", "ops")
GRAPH_LENS_IDS = ("all", "research", "engineering", "ops")

EXTRACTION_LENS_DESCRIPTORS = [
    {
        "id": "research",
        "label": "Research",
        "summary": "Concept, document, term, citation, provenance, and unresolved-idea extraction.",
        "default_proposal_limit": 6,
        "source_kinds": ["text", "markdown", "url", "pdf", "repository", "ops-document"],
        "primary_node_kinds": ["concept", "document", "term"],
        "provenance_fields": ["source", "locator", "reviewer", "trace"],
    },
    {
        "id": "engineering",
        "label": "Engineering",
        "summary": "Repository, file, module, symbol, dependency, issue, and pull-request extraction.",
        "default_proposal_limit": 8,
        "source_kinds": ["repository", "markdown", "text"],
        "primary_node_kinds": ["repository", "file", "module", "symbol", "package"],
        "provenance_fields": ["repository", "path", "symbol", "dependency", "issue_or_pr"],
    },
    {
        "id": "ops",
        "label": "Ops",
        "summary": "Policy, process, vendor, incident, project, owner, and review-cycle extraction.",
        "default_proposal_limit": 8,
        "source_kinds": ["ops-document", "markdown", "text"],
        "primary_node_kinds": ["policy", "process", "vendor", "incident", "project", "owner", "review_cycle"],
        "provenance_fields": ["document", "owner", "review_cycle", "effective_date", "incident_or_project"],
    },
]

GRAPH_LENS_DESCRIPTORS = [
    {
        "id": "all",
        "label": "All",
        "summary": "Full reviewed graph without an active use-case lens.",
        "active_by_default": True,
    },
    {
        "id": "research",
        "label": "Research",
        "summary": "Concepts, documents, terms, citations, provenance, and related idea clusters.",
        "active_by_default": False,
    },
    {
        "id": "engineering",
        "label": "Engineering",
        "summary": "Repositories, modules, files, symbols, dependencies, issues, and architecture hotspots.",
        "active_by_default": False,
    },
    {
        "id": "ops",
        "label": "Ops",
        "summary": "Owners, policies, processes, vendors, incidents, projects, stale review cycles, and handoffs.",
        "active_by_default": False,
    },
]


def normalize_graph_lens(lens: str | None) -> str:
    return lens if lens in GRAPH_LENS_IDS else "all"


def normalize_extraction_lenses(lenses: list[str] | None) -> list[str]:
    if not lenses:
        return list(EXTRACTION_LENS_IDS)
    normalized = []
    for lens in lenses:
        if lens in EXTRACTION_LENS_IDS and lens not in normalized:
            normalized.append(lens)
    return normalized or list(EXTRACTION_LENS_IDS)
