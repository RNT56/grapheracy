from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from pypdf import PdfReader


EMBEDDING_MODEL = "graphview-local-hash-v1"
EXTRACTION_LENSES = ("research", "engineering", "ops")
DEFAULT_PROPOSAL_LIMIT_BY_LENS = {
    "research": 6,
    "engineering": 8,
    "ops": 8,
}


@dataclass(frozen=True)
class RawSource:
    kind: Literal["text", "markdown", "pdf", "repository", "ops-document"]
    title: str
    content: str | bytes
    uri: str | None = None


@dataclass(frozen=True)
class IngestionProposal:
    kind: Literal["content_node", "semantic_edge"]
    proposed_value: dict
    confidence: float
    locator: str


@dataclass(frozen=True)
class IngestionResult:
    source_checksum: str
    normalized_text: str
    embedding_model: str
    embedding_vector: list[float]
    proposals: list[IngestionProposal]


def ingest_source(source: RawSource, *, proposal_limit: int | None = None, extraction_lenses: list[str] | None = None) -> IngestionResult:
    text = _extract_text(source)
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return IngestionResult(
        source_checksum=checksum,
        normalized_text=text,
        embedding_model=EMBEDDING_MODEL,
        embedding_vector=embed_text(text),
        proposals=generate_proposals(
            title=source.title,
            text=text,
            locator=source.uri or f"{source.kind}:inline",
            kind=source.kind,
            extraction_lenses=extraction_lenses,
            proposal_limit_per_lens=proposal_limit,
        ),
    )


def _extract_text(source: RawSource) -> str:
    if source.kind == "pdf":
        if isinstance(source.content, str):
            return normalize_text(source.content)
        return normalize_text(extract_pdf_text(source.content))
    if not isinstance(source.content, str):
        raise TypeError("Text and markdown sources require string content.")
    if source.kind == "markdown":
        return normalize_markdown(source.content)
    if source.kind == "repository":
        return normalize_repository(source.content)
    if source.kind == "ops-document":
        return normalize_structured_text(source.content)
    return normalize_text(source.content)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page for page in pages if page).strip()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_markdown(text: str) -> str:
    without_code_fences = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    without_links = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", without_code_fences)
    without_markup = re.sub(r"[#>*_`~-]+", " ", without_links)
    return normalize_text(without_markup)


def normalize_structured_text(text: str) -> str:
    lines = [re.sub(r"^[#>*_`~-]+\s*", "", line.rstrip()) for line in text.splitlines()]
    compact = "\n".join(line for line in lines if line.strip())
    return re.sub(r"\n{3,}", "\n\n", compact).strip()


def normalize_repository(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\t", "    ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line.strip())).strip()


def embed_text(text: str, dimensions: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        byte = digest[index % len(digest)]
        values.append(round((byte / 127.5) - 1, 6))
    return values


def generate_proposals(
    *,
    title: str,
    text: str,
    locator: str,
    kind: Literal["text", "markdown", "pdf", "repository", "ops-document"] = "text",
    extraction_lenses: list[str] | None = None,
    proposal_limit_per_lens: int | None = None,
) -> list[IngestionProposal]:
    proposals: list[IngestionProposal] = []
    for lens in _normalize_extraction_lenses(extraction_lenses):
        limit = proposal_limit_per_lens or DEFAULT_PROPOSAL_LIMIT_BY_LENS[lens]
        proposals.extend(_proposals_for_lens(title=title, text=text, locator=locator, kind=kind, lens=lens)[:limit])
    proposals = _merge_duplicate_proposals(proposals)
    return proposals or [
        IngestionProposal(
            kind="content_node",
            proposed_value={
                "label": title,
                "kind": "concept",
                "summary": summarize_for_label(text, title),
                "topicIds": [],
                "metadata": {"extractionLenses": ["research"]},
            },
            confidence=0.55,
            locator=locator,
        )
    ]


def _normalize_extraction_lenses(lenses: list[str] | None) -> list[str]:
    if not lenses:
        return list(EXTRACTION_LENSES)
    normalized = []
    for lens in lenses:
        if lens in EXTRACTION_LENSES and lens not in normalized:
            normalized.append(lens)
    return normalized or list(EXTRACTION_LENSES)


def _proposals_for_lens(*, title: str, text: str, locator: str, kind: str, lens: str) -> list[IngestionProposal]:
    if lens == "engineering":
        return _engineering_proposals(title=title, text=text, locator=locator) if _has_engineering_signal(kind, text) else []
    if lens == "ops":
        return _ops_proposals(title=title, text=text, locator=locator) if _has_ops_signal(kind, text) else []
    return _research_proposals(title=title, text=text, locator=locator)


def _research_proposals(*, title: str, text: str, locator: str) -> list[IngestionProposal]:
    labels = _candidate_labels(title, text)
    node_proposals = [
        _content_node_proposal(
            label=label,
            node_kind="document" if index == 0 and label == title else "concept",
            summary=summarize_for_label(text, label),
            confidence=round(max(0.55, 0.82 - (index * 0.07)), 2),
            locator=locator,
            metadata={"extractionLenses": ["research"]},
        )
        for index, label in enumerate(labels)
    ]
    return [*node_proposals, *_edge_proposals_from_labels(labels, relation="relates_to", locator=locator, metadata={"extractionLenses": ["research"]})]


def _engineering_proposals(*, title: str, text: str, locator: str) -> list[IngestionProposal]:
    candidates: list[tuple[str, str, str, str]] = []
    _append_repository_candidate(candidates, "Repository", title, "repository", summarize_for_label(text, title))
    for path in re.findall(r"(?:^|\s)([\w./-]+\.(?:py|ts|tsx|js|mjs|json|md|yml|yaml|go|rs|java))(?::|\s|$)", text):
        _append_repository_candidate(candidates, "Path", path, "file", f"Repository artifact at {path}.")
    for symbol in re.findall(r"\b(?:class|def|function|interface|type|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)", text):
        _append_repository_candidate(candidates, "Symbol", symbol, "symbol", f"Code symbol `{symbol}` detected in repository source.")
    for dependency in _repository_dependencies(text):
        _append_repository_candidate(
            candidates,
            "Dependency",
            dependency,
            "package",
            f"Dependency or import reference `{dependency}` detected in repository source.",
        )
    for reference in re.findall(r"\b(?:PR|Issue|GH)[\s#-]*(\d+)\b|#(\d+)", text, flags=re.IGNORECASE):
        number = next((part for part in reference if part), "")
        if number:
            _append_repository_candidate(
                candidates,
                "Issue",
                f"#{number}",
                "task",
                f"Pull-request or issue provenance reference #{number} detected in repository source.",
            )
    node_proposals = [
        _content_node_proposal(
            label=label,
            node_kind=node_kind,
            summary=summary,
            confidence=round(max(0.58, 0.88 - (index * 0.06)), 2),
            locator=locator,
            metadata={"extractionLenses": ["engineering"], "artifactType": artifact_type},
        )
        for index, (label, artifact_type, node_kind, summary) in enumerate(candidates)
    ]
    edge_proposals = [
        _semantic_edge_proposal(
            source_label=candidates[0][0],
            target_label=label,
            relation=_repository_relation(artifact_type),
            confidence=round(max(0.52, 0.78 - (index * 0.04)), 2),
            locator=locator,
            metadata={"extractionLenses": ["engineering"], "artifactType": artifact_type},
        )
        for index, (label, artifact_type, _, _) in enumerate(candidates[1:])
    ]
    return [*node_proposals, *edge_proposals]


def _ops_proposals(*, title: str, text: str, locator: str) -> list[IngestionProposal]:
    metadata = _ops_metadata(text)
    candidates: list[tuple[str, str, str]] = []
    _append_ops_candidate(candidates, title, _ops_node_kind(title), summarize_for_label(text, title))
    for line in text.splitlines():
        cleaned = line.strip(" -:\t")
        if re.search(r"\b(policy|process|vendor|incident|project)\b", cleaned, flags=re.IGNORECASE):
            _append_ops_candidate(candidates, cleaned, _ops_node_kind(cleaned), summarize_for_label(text, cleaned))
    if metadata.get("owner"):
        _append_ops_candidate(candidates, f"Owner {metadata['owner']}", "owner", f"Operational owner recorded as {metadata['owner']}.")
    if metadata.get("reviewCycle"):
        _append_ops_candidate(candidates, f"Review cycle {metadata['reviewCycle']}", "review_cycle", f"Review cycle recorded as {metadata['reviewCycle']}.")
    node_proposals = [
        _content_node_proposal(
            label=label,
            node_kind=node_kind,
            summary=_append_ops_summary(summary, metadata),
            confidence=round(max(0.57, 0.86 - (index * 0.06)), 2),
            locator=locator,
            metadata={"extractionLenses": ["ops"], "documentType": _ops_document_type(label), **metadata},
        )
        for index, (label, node_kind, summary) in enumerate(candidates)
    ]
    edge_proposals = [
        _semantic_edge_proposal(
            source_label=candidates[0][0],
            target_label=label,
            relation=_ops_relation(label),
            confidence=round(max(0.52, 0.76 - (index * 0.04)), 2),
            locator=locator,
            metadata={"extractionLenses": ["ops"], "documentType": _ops_document_type(label), **metadata},
        )
        for index, (label, _, _) in enumerate(candidates[1:])
    ]
    return [*node_proposals, *edge_proposals]


def _content_node_proposal(
    *,
    label: str,
    node_kind: str,
    summary: str,
    confidence: float,
    locator: str,
    metadata: dict | None = None,
) -> IngestionProposal:
    proposed_value = {
        "label": label,
        "kind": node_kind,
        "summary": summary,
        "topicIds": [],
    }
    if metadata:
        proposed_value["metadata"] = {key: value for key, value in metadata.items() if value}
    return IngestionProposal(kind="content_node", proposed_value=proposed_value, confidence=confidence, locator=locator)


def _semantic_edge_proposal(
    *,
    source_label: str,
    target_label: str,
    relation: str,
    confidence: float,
    locator: str,
    metadata: dict | None = None,
) -> IngestionProposal:
    proposed_value = {
        "sourceLabel": source_label,
        "targetLabel": target_label,
        "relation": relation,
        "weight": confidence,
    }
    if metadata:
        proposed_value["metadata"] = {key: value for key, value in metadata.items() if value}
    return IngestionProposal(
        kind="semantic_edge",
        proposed_value=proposed_value,
        confidence=confidence,
        locator=locator,
    )


def _edge_proposals_from_labels(labels: list[str], *, relation: str, locator: str, metadata: dict | None = None) -> list[IngestionProposal]:
    if len(labels) < 2:
        return []
    root = labels[0]
    return [
        _semantic_edge_proposal(
            source_label=root,
            target_label=label,
            relation=relation,
            confidence=round(max(0.5, 0.7 - (index * 0.04)), 2),
            locator=locator,
            metadata=metadata,
        )
        for index, label in enumerate(labels[1:4])
    ]


def summarize_for_label(text: str, label: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if label.lower() in sentence.lower():
            return sentence[:360]
    return text[:360]


def _candidate_labels(title: str, text: str) -> list[str]:
    candidates: list[str] = []
    _append_unique(candidates, title)
    for match in re.findall(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3}\b", text):
        if len(match) > 3:
            _append_unique(candidates, match)
    return candidates


def _repository_dependencies(text: str) -> list[str]:
    dependencies: list[str] = []
    for groups in re.findall(
        r"\bfrom\s+[\"']([^\"']+)[\"']|\bimport\s+[\"']([^\"']+)[\"']|\"([@A-Za-z0-9_.\-/]+)\"\s*:\s*\"[\^~]?\d",
        text,
    ):
        dependency = next((group for group in groups if group), "")
        if dependency:
            _append_unique(dependencies, dependency)
    return dependencies


def _append_repository_candidate(
    values: list[tuple[str, str, str, str]],
    artifact_type: str,
    value: str,
    node_kind: str,
    summary: str,
) -> None:
    label = f"{artifact_type} {value}".strip()
    if label and label.lower() not in {existing[0].lower() for existing in values}:
        values.append((label, artifact_type.lower(), node_kind, summary))


def _append_ops_candidate(values: list[tuple[str, str, str]], label: str, node_kind: str, summary: str) -> None:
    normalized = " ".join(label.split())
    if normalized and normalized.lower() not in {existing[0].lower() for existing in values}:
        values.append((normalized, node_kind, summary))


def _ops_metadata(text: str) -> dict[str, str]:
    return {
        "owner": _first_metadata_value(text, r"\bOwner\s*:\s*([^\n.;]+)"),
        "reviewCycle": _first_metadata_value(text, r"\bReview(?: cycle| cadence)?\s*:\s*([^\n.;]+)"),
        "effectiveDate": _first_metadata_value(text, r"\bEffective(?: date)?\s*:\s*([^\n.;]+)"),
    }


def _first_metadata_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return " ".join(match.group(1).split()) if match else ""


def _ops_node_kind(label: str) -> str:
    lowered = label.lower()
    if "vendor" in lowered:
        return "vendor"
    if "risk" in lowered or "blocker" in lowered:
        return "risk"
    if "incident" in lowered:
        return "incident"
    if "decision" in lowered or "exception" in lowered:
        return "decision"
    if "policy" in lowered:
        return "policy"
    if "requirement" in lowered or "control" in lowered:
        return "requirement"
    if "project" in lowered:
        return "project"
    if "workflow" in lowered:
        return "workflow"
    if "process" in lowered or "procedure" in lowered:
        return "process"
    return "document"


def _ops_document_type(label: str) -> str:
    lowered = label.lower()
    for kind in ["policy", "process", "vendor", "incident", "project", "owner"]:
        if kind in lowered:
            return kind
    if "review" in lowered:
        return "review_cycle"
    return "document"


def _repository_relation(artifact_type: str) -> str:
    if artifact_type == "dependency":
        return "imports"
    if artifact_type == "symbol":
        return "defines"
    if artifact_type == "path":
        return "contains"
    if artifact_type == "issue":
        return "references"
    return "mentions"


def _ops_relation(label: str) -> str:
    lowered = label.lower()
    if lowered.startswith("owner "):
        return "owned_by"
    if "review cycle" in lowered or lowered.startswith("review "):
        return "has_review_cycle"
    if "policy" in lowered or "process" in lowered:
        return "governs"
    if "incident" in lowered or "project" in lowered:
        return "supports"
    if "vendor" in lowered:
        return "depends_on"
    return "mentions"


def _append_ops_summary(summary: str, metadata: dict[str, str]) -> str:
    details = []
    if metadata.get("owner"):
        details.append(f"Owner: {metadata['owner']}")
    if metadata.get("reviewCycle"):
        details.append(f"Review: {metadata['reviewCycle']}")
    if not details:
        return summary
    return f"{summary} {'; '.join(details)}"[:360]


def _append_unique(values: list[str], value: str) -> None:
    normalized = " ".join(value.split())
    if normalized and normalized.lower() not in {existing.lower() for existing in values}:
        values.append(normalized)


def _has_engineering_signal(kind: str, text: str) -> bool:
    if kind == "repository":
        return True
    return bool(
        re.search(r"[\w./-]+\.(?:py|ts|tsx|js|mjs|json|md|yml|yaml|go|rs|java)\b", text)
        or re.search(r"\b(?:class|def|function|interface|type|const|let|var)\s+[A-Za-z_][A-Za-z0-9_]*", text)
        or re.search(r"\b(?:from|import)\s+[\"'][^\"']+[\"']", text)
        or re.search(r"\b(?:PR|Issue|GH)[\s#-]*\d+\b|#\d+", text, flags=re.IGNORECASE)
    )


def _has_ops_signal(kind: str, text: str) -> bool:
    if kind == "ops-document":
        return True
    metadata = _ops_metadata(text)
    return bool(
        metadata.get("owner")
        or metadata.get("reviewCycle")
        or metadata.get("effectiveDate")
        or re.search(r"\b(policy|process|vendor|incident|project|review cycle|rollback|escalation)\b", text, flags=re.IGNORECASE)
    )


def _merge_duplicate_proposals(proposals: list[IngestionProposal]) -> list[IngestionProposal]:
    merged: dict[tuple[str, str, str, str], IngestionProposal] = {}
    for proposal in proposals:
        key = _proposal_merge_key(proposal)
        existing = merged.get(key)
        if existing is None:
            merged[key] = proposal
            continue
        existing.proposed_value["metadata"] = _merge_metadata(
            existing.proposed_value.get("metadata", {}),
            proposal.proposed_value.get("metadata", {}),
        )
        merged[key] = IngestionProposal(
            kind=existing.kind,
            proposed_value=existing.proposed_value,
            confidence=max(existing.confidence, proposal.confidence),
            locator=existing.locator or proposal.locator,
        )
    return list(merged.values())


def _proposal_merge_key(proposal: IngestionProposal) -> tuple[str, str, str, str]:
    value = proposal.proposed_value
    if proposal.kind == "semantic_edge":
        return (
            "semantic_edge",
            str(value.get("sourceLabel") or value.get("sourceNodeId") or "").strip().lower(),
            str(value.get("targetLabel") or value.get("targetNodeId") or "").strip().lower(),
            str(value.get("relation") or "relates_to").strip().lower(),
        )
    return (
        "content_node",
        str(value.get("label") or "").strip().lower(),
        str(value.get("kind") or "concept").strip().lower(),
        "",
    )


def _merge_metadata(left: dict, right: dict) -> dict:
    merged = {key: value for key, value in left.items() if value}
    for key, value in right.items():
        if key == "extractionLenses":
            lenses = []
            left_lenses = merged.get("extractionLenses", [])
            if not isinstance(left_lenses, list):
                left_lenses = []
            right_lenses = value if isinstance(value, list) else []
            for lens in [*left_lenses, *right_lenses]:
                if lens not in lenses:
                    lenses.append(lens)
            merged["extractionLenses"] = lenses
        elif value and key not in merged:
            merged[key] = value
    return merged
