from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from pypdf import PdfReader


EMBEDDING_MODEL = "graphview-local-hash-v1"


@dataclass(frozen=True)
class RawSource:
    kind: Literal["text", "markdown", "pdf"]
    title: str
    content: str | bytes
    uri: str | None = None


@dataclass(frozen=True)
class IngestionProposal:
    kind: Literal["content_node"]
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


def ingest_source(source: RawSource, *, proposal_limit: int = 4) -> IngestionResult:
    text = _extract_text(source)
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return IngestionResult(
        source_checksum=checksum,
        normalized_text=text,
        embedding_model=EMBEDDING_MODEL,
        embedding_vector=embed_text(text),
        proposals=generate_proposals(title=source.title, text=text, locator=source.uri or f"{source.kind}:inline")[
            :proposal_limit
        ],
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


def embed_text(text: str, dimensions: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        byte = digest[index % len(digest)]
        values.append(round((byte / 127.5) - 1, 6))
    return values


def generate_proposals(*, title: str, text: str, locator: str) -> list[IngestionProposal]:
    labels = _candidate_labels(title, text)
    return [
        IngestionProposal(
            kind="content_node",
            proposed_value={
                "label": label,
                "kind": "concept",
                "summary": summarize_for_label(text, label),
                "topicIds": [],
            },
            confidence=round(max(0.55, 0.82 - (index * 0.07)), 2),
            locator=locator,
        )
        for index, label in enumerate(labels or [title])
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


def _append_unique(values: list[str], value: str) -> None:
    normalized = " ".join(value.split())
    if normalized and normalized.lower() not in {existing.lower() for existing in values}:
        values.append(normalized)
