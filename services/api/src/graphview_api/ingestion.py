from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

import httpx
from pypdf import PdfReader


SourceKind = Literal["text", "markdown", "url", "pdf", "repository", "ops-document"]
ExtractionLens = Literal["research", "engineering", "ops"]
EMBEDDING_MODEL = "graphview-local-hash-v1"
DEFAULT_EXTRACTION_LENSES: tuple[ExtractionLens, ...] = ("research", "engineering", "ops")
DEFAULT_PROPOSAL_LIMIT_BY_LENS: dict[ExtractionLens, int] = {
    "research": 6,
    "engineering": 8,
    "ops": 8,
}


@dataclass(frozen=True)
class NormalizedDocument:
    kind: SourceKind
    title: str
    text: str
    uri: str | None
    checksum: str
    locator: str


@dataclass(frozen=True)
class GeneratedProposal:
    kind: Literal["content_node", "semantic_edge"]
    proposed_value: dict
    confidence: float
    locator: str


async def build_document(
    *,
    kind: SourceKind,
    title: str,
    content: str | None = None,
    uri: str | None = None,
    content_base64: str | None = None,
) -> NormalizedDocument:
    raw_text = await _load_raw_text(kind=kind, content=content, uri=uri, content_base64=content_base64)
    text = normalize_for_kind(kind, raw_text)
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return NormalizedDocument(
        kind=kind,
        title=title,
        text=text,
        uri=uri,
        checksum=checksum,
        locator=uri or f"{kind}:inline",
    )


async def _load_raw_text(
    *,
    kind: SourceKind,
    content: str | None,
    uri: str | None,
    content_base64: str | None,
) -> str:
    if kind == "url":
        if content:
            return content
        if not uri:
            raise ValueError("URL ingestion requires uri or content.")
        return await fetch_url_text(uri)
    if kind == "pdf":
        if content:
            return content
        if not content_base64:
            raise ValueError("PDF ingestion requires content_base64 or extracted content.")
        return extract_pdf_text(base64.b64decode(content_base64))
    if content is None:
        raise ValueError(f"{kind} ingestion requires content.")
    return content


async def fetch_url_text(uri: str) -> str:
    async with httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,
        headers={"User-Agent": "GraphviewPhase16Ingestion/0.16"},
    ) as client:
        response = await client.get(uri)
        response.raise_for_status()
        return response.text


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


def normalize_for_kind(kind: SourceKind, text: str) -> str:
    if kind == "markdown":
        return normalize_markdown(text)
    if kind == "repository":
        return normalize_repository(text)
    if kind == "ops-document":
        return normalize_structured_text(text)
    return normalize_text(text)


def embed_text(text: str, dimensions: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        byte = digest[index % len(digest)]
        values.append(round((byte / 127.5) - 1, 6))
    return values


def generate_proposals(
    document: NormalizedDocument,
    *,
    limit: int | None = None,
    extraction_lenses: list[ExtractionLens] | None = None,
    proposal_limit_per_lens: int | None = None,
) -> list[GeneratedProposal]:
    proposals: list[GeneratedProposal] = []
    for lens in _lenses_for_document(document, extraction_lenses):
        lens_limit = proposal_limit_per_lens or limit or DEFAULT_PROPOSAL_LIMIT_BY_LENS[lens]
        proposals.extend(_proposals_for_lens(document, lens)[:lens_limit])
    proposals = _merge_duplicate_proposals(proposals)
    if not proposals:
        proposals.append(
            GeneratedProposal(
                kind="content_node",
                proposed_value={
                    "label": document.title,
                    "kind": "concept",
                    "summary": summarize_for_label(document.text, document.title),
                    "topicIds": [],
                    "metadata": {"extractionLenses": ["research"]},
                },
                confidence=0.55,
                locator=document.locator,
            )
        )
    return proposals


def _normalize_extraction_lenses(lenses: list[ExtractionLens] | None) -> list[ExtractionLens]:
    if not lenses:
        return list(DEFAULT_EXTRACTION_LENSES)
    normalized: list[ExtractionLens] = []
    for lens in lenses:
        if lens in DEFAULT_EXTRACTION_LENSES and lens not in normalized:
            normalized.append(lens)
    return normalized or list(DEFAULT_EXTRACTION_LENSES)


def _lenses_for_document(document: NormalizedDocument, lenses: list[ExtractionLens] | None) -> list[ExtractionLens]:
    if lenses:
        return _normalize_extraction_lenses(lenses)
    if document.kind == "repository":
        return ["engineering", "research", "ops"]
    if document.kind == "ops-document":
        return ["ops", "research", "engineering"]
    return list(DEFAULT_EXTRACTION_LENSES)


def _proposals_for_lens(document: NormalizedDocument, lens: ExtractionLens) -> list[GeneratedProposal]:
    if lens == "engineering":
        return _engineering_proposals(document) if _has_engineering_signal(document) else []
    if lens == "ops":
        return _ops_proposals(document) if _has_ops_signal(document) else []
    return _research_proposals(document)


def _research_proposals(document: NormalizedDocument) -> list[GeneratedProposal]:
    candidates = _candidate_labels(document)
    node_proposals = [
        _content_node_proposal(
            label=label,
            node_kind="document" if index == 0 and label == document.title else "concept",
            summary=summarize_for_label(document.text, label),
            confidence=round(max(0.55, 0.82 - (index * 0.07)), 2),
            locator=document.locator,
            metadata={"extractionLenses": ["research"]},
        )
        for index, label in enumerate(candidates)
    ]
    return [
        *node_proposals,
        *_edge_proposals_from_labels(
            candidates,
            relation="relates_to",
            locator=document.locator,
            metadata={"extractionLenses": ["research"]},
        ),
    ]


def _engineering_proposals(document: NormalizedDocument) -> list[GeneratedProposal]:
    candidates: list[tuple[str, str, str, str]] = []
    _append_repository_candidates(candidates, "Repository", document.title, "repository", summarize_for_label(document.text, document.title))

    for path in re.findall(r"(?:^|\s)([\w./-]+\.(?:py|ts|tsx|js|mjs|json|md|yml|yaml|go|rs|java))(?::|\s|$)", document.text):
        _append_repository_candidates(candidates, "Path", path, "file", f"Repository artifact at {path}.")

    for symbol in re.findall(
        r"\b(?:class|def|function|interface|type|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
        document.text,
    ):
        _append_repository_candidates(candidates, "Symbol", symbol, "symbol", f"Code symbol `{symbol}` detected in repository source.")

    for dependency in _repository_dependencies(document.text):
        _append_repository_candidates(
            candidates,
            "Dependency",
            dependency,
            "package",
            f"Dependency or import reference `{dependency}` detected in repository source.",
        )

    for reference in re.findall(r"\b(?:PR|Issue|GH)[\s#-]*(\d+)\b|#(\d+)", document.text, flags=re.IGNORECASE):
        number = next((part for part in reference if part), "")
        if number:
            _append_repository_candidates(
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
            locator=document.locator,
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
            locator=document.locator,
            metadata={"extractionLenses": ["engineering"], "artifactType": artifact_type},
        )
        for index, (label, artifact_type, _, _) in enumerate(candidates[1:])
    ]
    return [*node_proposals, *edge_proposals]


def _ops_proposals(document: NormalizedDocument) -> list[GeneratedProposal]:
    metadata = _ops_metadata(document.text)
    candidates: list[tuple[str, str, str]] = []
    _append_ops_candidate(candidates, document.title, _ops_node_kind(document.title), summarize_for_label(document.text, document.title))

    for line in document.text.splitlines():
        cleaned = line.strip(" -:\t")
        if re.search(r"\b(policy|process|vendor|incident|project)\b", cleaned, flags=re.IGNORECASE):
            _append_ops_candidate(candidates, cleaned, _ops_node_kind(cleaned), summarize_for_label(document.text, cleaned))

    if metadata.get("owner"):
        _append_ops_candidate(
            candidates,
            f"Owner {metadata['owner']}",
            "owner",
            f"Operational owner recorded as {metadata['owner']}.",
        )
    if metadata.get("reviewCycle"):
        _append_ops_candidate(
            candidates,
            f"Review cycle {metadata['reviewCycle']}",
            "review_cycle",
            f"Review cycle recorded as {metadata['reviewCycle']}.",
        )

    node_proposals = [
        _content_node_proposal(
            label=label,
            node_kind=node_kind,
            summary=_append_ops_summary(summary, metadata),
            confidence=round(max(0.57, 0.86 - (index * 0.06)), 2),
            locator=document.locator,
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
            locator=document.locator,
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
) -> GeneratedProposal:
    proposed_value = {
        "label": label,
        "kind": node_kind,
        "summary": summary,
        "topicIds": [],
    }
    if metadata:
        proposed_value["metadata"] = {key: value for key, value in metadata.items() if value}
    return GeneratedProposal(
        kind="content_node",
        proposed_value=proposed_value,
        confidence=confidence,
        locator=locator,
    )


def _semantic_edge_proposal(
    *,
    source_label: str,
    target_label: str,
    relation: str,
    confidence: float,
    locator: str,
    metadata: dict | None = None,
) -> GeneratedProposal:
    proposed_value = {
        "label": f"{source_label} {relation.replace('_', ' ')} {target_label}",
        "sourceLabel": source_label,
        "targetLabel": target_label,
        "relation": relation,
        "weight": confidence,
    }
    if metadata:
        proposed_value["metadata"] = {key: value for key, value in metadata.items() if value}
    return GeneratedProposal(
        kind="semantic_edge",
        proposed_value=proposed_value,
        confidence=confidence,
        locator=locator,
    )


def _edge_proposals_from_labels(
    labels: list[str],
    *,
    relation: str,
    locator: str,
    metadata: dict | None = None,
) -> list[GeneratedProposal]:
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


def _candidate_labels(document: NormalizedDocument) -> list[str]:
    candidates: list[str] = []
    if document.title:
        _append_unique(candidates, document.title)
    for heading in re.findall(r"(?:^|\n)#{1,3}\s+(.+)", document.text):
        _append_unique(candidates, heading.strip())
    for match in re.findall(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3}\b", document.text):
        cleaned = match.strip()
        if len(cleaned) > 3 and cleaned.lower() not in {"this", "that"}:
            _append_unique(candidates, cleaned)
    return candidates


def _append_repository_candidates(
    values: list[tuple[str, str, str, str]],
    artifact_type: str,
    value: str,
    node_kind: str,
    summary: str,
) -> None:
    label = f"{artifact_type} {value}".strip()
    if label and label.lower() not in {existing[0].lower() for existing in values}:
        values.append((label, artifact_type.lower(), node_kind, summary))


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


def _has_engineering_signal(document: NormalizedDocument) -> bool:
    if document.kind == "repository":
        return True
    return bool(
        re.search(r"[\w./-]+\.(?:py|ts|tsx|js|mjs|json|md|yml|yaml|go|rs|java)\b", document.text)
        or re.search(r"\b(?:class|def|function|interface|type|const|let|var)\s+[A-Za-z_][A-Za-z0-9_]*", document.text)
        or re.search(r"\b(?:from|import)\s+[\"'][^\"']+[\"']", document.text)
        or re.search(r"\b(?:PR|Issue|GH)[\s#-]*\d+\b|#\d+", document.text, flags=re.IGNORECASE)
    )


def _has_ops_signal(document: NormalizedDocument) -> bool:
    if document.kind == "ops-document":
        return True
    return bool(
        _ops_metadata(document.text).get("owner")
        or _ops_metadata(document.text).get("reviewCycle")
        or _ops_metadata(document.text).get("effectiveDate")
        or re.search(r"\b(policy|process|vendor|incident|project|review cycle|rollback|escalation)\b", document.text, flags=re.IGNORECASE)
    )


def _merge_duplicate_proposals(proposals: list[GeneratedProposal]) -> list[GeneratedProposal]:
    merged: dict[tuple[str, str, str, str], GeneratedProposal] = {}
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
        merged[key] = GeneratedProposal(
            kind=existing.kind,
            proposed_value=existing.proposed_value,
            confidence=max(existing.confidence, proposal.confidence),
            locator=existing.locator or proposal.locator,
        )
    return list(merged.values())


def _proposal_merge_key(proposal: GeneratedProposal) -> tuple[str, str, str, str]:
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
