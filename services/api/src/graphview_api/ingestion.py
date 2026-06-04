from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

import httpx
from pypdf import PdfReader


SourceKind = Literal["text", "markdown", "url", "pdf"]
EMBEDDING_MODEL = "graphview-local-hash-v1"


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
    kind: Literal["content_node"]
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
    text = normalize_markdown(raw_text) if kind == "markdown" else normalize_text(raw_text)
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
        headers={"User-Agent": "GraphviewPhase4Ingestion/0.4"},
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


def embed_text(text: str, dimensions: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        byte = digest[index % len(digest)]
        values.append(round((byte / 127.5) - 1, 6))
    return values


def generate_proposals(document: NormalizedDocument, *, limit: int = 4) -> list[GeneratedProposal]:
    candidates = _candidate_labels(document)
    proposals: list[GeneratedProposal] = []
    for index, label in enumerate(candidates[:limit]):
        proposals.append(
            GeneratedProposal(
                kind="content_node",
                proposed_value={
                    "label": label,
                    "kind": "concept",
                    "summary": summarize_for_label(document.text, label),
                    "topicIds": [],
                },
                confidence=round(max(0.55, 0.82 - (index * 0.07)), 2),
                locator=document.locator,
            )
        )
    if not proposals:
        proposals.append(
            GeneratedProposal(
                kind="content_node",
                proposed_value={
                    "label": document.title,
                    "kind": "concept",
                    "summary": summarize_for_label(document.text, document.title),
                    "topicIds": [],
                },
                confidence=0.55,
                locator=document.locator,
            )
        )
    return proposals


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


def _append_unique(values: list[str], value: str) -> None:
    normalized = " ".join(value.split())
    if normalized and normalized.lower() not in {existing.lower() for existing in values}:
        values.append(normalized)
