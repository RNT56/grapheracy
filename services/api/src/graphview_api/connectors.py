from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from graphview_api.ingestion import GeneratedProposal, fetch_url_text, normalize_for_kind, normalize_text

ConnectorKind = Literal["upload", "url", "repository", "google-workspace", "notion"]
SourceKind = Literal["text", "markdown", "url", "pdf", "repository", "ops-document"]


@dataclass(frozen=True)
class NormalizedSourceChunk:
    stable_key: str
    parent_stable_key: str | None
    heading_path: list[str]
    block_type: str
    ordinal: int
    text: str
    links: list[str]
    mentions: list[str]
    checksum: str
    locator: str


@dataclass(frozen=True)
class NormalizedSourceDocument:
    connector_kind: ConnectorKind
    source_kind: SourceKind
    title: str
    text: str
    uri: str | None
    remote_id: str
    remote_parent_id: str | None = None
    remote_modified_at: datetime | None = None
    remote_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[NormalizedSourceChunk] = field(default_factory=list)

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def connector_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "kind": "upload",
            "label": "Upload",
            "summary": "Import pasted or uploaded text, markdown, JSON, CSV, PDF text, and office exports.",
            "target_types": ["upload", "file"],
            "requires_account": False,
        },
        {
            "kind": "url",
            "label": "URL",
            "summary": "Fetch a webpage, extract text, headings, and explicit links.",
            "target_types": ["url"],
            "requires_account": False,
        },
        {
            "kind": "repository",
            "label": "Repository",
            "summary": "Map repository files, symbols, imports, dependencies, and issue references.",
            "target_types": ["repository", "folder", "file"],
            "requires_account": False,
        },
        {
            "kind": "google-workspace",
            "label": "Google Workspace",
            "summary": "Read Drive folders/files and exported Docs, Sheets, Slides, PDFs, and office files.",
            "target_types": ["folder", "file"],
            "requires_account": True,
        },
        {
            "kind": "notion",
            "label": "Notion",
            "summary": "Read pages, databases, page properties, recursive blocks, mentions, relations, and file references.",
            "target_types": ["page", "database"],
            "requires_account": True,
        },
    ]


async def fetch_connector_documents(
    *,
    account: dict[str, Any],
    target: dict[str, Any],
    token_json: dict[str, Any] | None,
) -> list[NormalizedSourceDocument]:
    kind = account["kind"]
    settings = {**account.get("settings", {}), **target.get("sync_settings", {})}
    if kind == "upload":
        return _upload_documents(target, settings)
    if kind == "url":
        return [await _url_document(target, settings)]
    if kind == "repository":
        return _repository_documents(target, settings)
    if kind == "google-workspace":
        return await _google_documents(target, settings, token_json or {})
    if kind == "notion":
        return await _notion_documents(target, settings, token_json or {})
    raise ValueError(f"Unsupported connector kind: {kind}")


def build_connector_proposals(document: NormalizedSourceDocument) -> list[GeneratedProposal]:
    proposals: list[GeneratedProposal] = []
    lens_metadata = _source_lens_metadata(document)
    document_node_id = stable_id("node", document.connector_kind, document.remote_id, "document")
    proposals.append(
        _node_proposal(
            node_id=document_node_id,
            label=document.title,
            node_kind=_document_node_kind(document),
            summary=f"Imported {document.connector_kind} source document.",
            confidence=0.95,
            locator=document.uri or document.remote_url or document.remote_id,
            metadata={
                "connectorKind": document.connector_kind,
                "remoteId": document.remote_id,
                "sourceKind": document.source_kind,
                **lens_metadata,
            },
        )
    )

    heading_node_ids: dict[str, str] = {}
    for chunk in document.chunks:
        if chunk.block_type == "heading" and chunk.text:
            heading_key = " / ".join(chunk.heading_path) or chunk.text
            heading_node_id = stable_id("node", document.connector_kind, document.remote_id, heading_key)
            heading_node_ids[heading_key] = heading_node_id
            proposals.append(
                _node_proposal(
                    node_id=heading_node_id,
                    label=chunk.text[:220],
                    node_kind="topic",
                    summary=f"Section from {document.title}: {chunk.text[:180]}",
                    confidence=0.93,
                    locator=chunk.locator,
                    metadata={"headingPath": chunk.heading_path, "connectorKind": document.connector_kind, **lens_metadata},
                )
            )
            parent_key = " / ".join(chunk.heading_path[:-1])
            parent_id = heading_node_ids.get(parent_key, document_node_id)
            proposals.append(
                _edge_proposal(
                    edge_id=stable_id("edge", parent_id, heading_node_id, "contains"),
                    source_node_id=parent_id,
                    target_node_id=heading_node_id,
                    source_label=document.title,
                    target_label=chunk.text[:220],
                    relation="contains",
                    confidence=0.94,
                    locator=chunk.locator,
                    metadata={"connectorKind": document.connector_kind, "source": "heading-hierarchy", **lens_metadata},
                )
            )

        for link in chunk.links[:6]:
            label = _label_for_url(link)
            ref_id = stable_id("node", "reference", link)
            proposals.append(
                _node_proposal(
                    node_id=ref_id,
                    label=label,
                    node_kind="source",
                    summary=f"External reference linked from {document.title}.",
                    confidence=0.92,
                    locator=chunk.locator,
                    metadata={"url": link, "connectorKind": document.connector_kind, **lens_metadata},
                )
            )
            proposals.append(
                _edge_proposal(
                    edge_id=stable_id("edge", document_node_id, ref_id, "references"),
                    source_node_id=document_node_id,
                    target_node_id=ref_id,
                    source_label=document.title,
                    target_label=label,
                    relation="references",
                    confidence=0.93,
                    locator=chunk.locator,
                    metadata={"connectorKind": document.connector_kind, "source": "explicit-link", **lens_metadata},
                )
            )

        for mention in chunk.mentions[:8]:
            label = mention.strip("@[] ")
            if len(label) < 2:
                continue
            mention_id = stable_id("node", "mention", label)
            proposals.append(
                _node_proposal(
                    node_id=mention_id,
                    label=label[:220],
                    node_kind="concept",
                    summary=f"Mentioned in {document.title}.",
                    confidence=0.88,
                    locator=chunk.locator,
                    metadata={"connectorKind": document.connector_kind, "source": "mention", **lens_metadata},
                )
            )
            proposals.append(
                _edge_proposal(
                    edge_id=stable_id("edge", document_node_id, mention_id, "mentions"),
                    source_node_id=document_node_id,
                    target_node_id=mention_id,
                    source_label=document.title,
                    target_label=label[:220],
                    relation="mentions",
                    confidence=0.86,
                    locator=chunk.locator,
                    metadata={"connectorKind": document.connector_kind, "source": "mention", **lens_metadata},
                )
            )

    if document.connector_kind == "repository":
        for path in sorted(_repository_paths(document.text))[:16]:
            path_id = stable_id("node", "path", document.remote_id, path)
            proposals.append(
                _node_proposal(
                    node_id=path_id,
                    label=f"Path {path}"[:220],
                    node_kind="file",
                    summary=f"Repository file or artifact at {path}.",
                    confidence=0.92,
                    locator=document.uri or document.remote_id,
                    metadata={"connectorKind": "repository", "artifactType": "Path", **lens_metadata},
                )
            )
            proposals.append(
                _edge_proposal(
                    edge_id=stable_id("edge", document_node_id, path_id, "contains"),
                    source_node_id=document_node_id,
                    target_node_id=path_id,
                    source_label=document.title,
                    target_label=f"Path {path}",
                    relation="contains",
                    confidence=0.92,
                    locator=document.uri or document.remote_id,
                    metadata={"connectorKind": "repository", "source": "path", **lens_metadata},
                )
            )

        for symbol in sorted(_repository_symbols(document.text))[:16]:
            symbol_id = stable_id("node", "symbol", document.remote_id, symbol)
            proposals.append(
                _node_proposal(
                    node_id=symbol_id,
                    label=f"Symbol {symbol}"[:220],
                    node_kind="symbol",
                    summary=f"Code symbol `{symbol}` detected in repository source.",
                    confidence=0.92,
                    locator=document.uri or document.remote_id,
                    metadata={"connectorKind": "repository", "artifactType": "Symbol", **lens_metadata},
                )
            )
            proposals.append(
                _edge_proposal(
                    edge_id=stable_id("edge", document_node_id, symbol_id, "defines"),
                    source_node_id=document_node_id,
                    target_node_id=symbol_id,
                    source_label=document.title,
                    target_label=f"Symbol {symbol}",
                    relation="defines",
                    confidence=0.92,
                    locator=document.uri or document.remote_id,
                    metadata={"connectorKind": "repository", "source": "symbol", **lens_metadata},
                )
            )

        for dependency in sorted(_repository_dependencies(document.text))[:12]:
            dependency_id = stable_id("node", "dependency", dependency)
            proposals.append(
                _node_proposal(
                    node_id=dependency_id,
                    label=f"Dependency {dependency}"[:220],
                    node_kind="package",
                    summary=f"Dependency or import reference `{dependency}` detected in repository source.",
                    confidence=0.92,
                    locator=document.uri or document.remote_id,
                    metadata={"connectorKind": "repository", "artifactType": "Dependency", **lens_metadata},
                )
            )
            proposals.append(
                _edge_proposal(
                    edge_id=stable_id("edge", document_node_id, dependency_id, "imports"),
                    source_node_id=document_node_id,
                    target_node_id=dependency_id,
                    source_label=document.title,
                    target_label=f"Dependency {dependency}",
                    relation="imports",
                    confidence=0.92,
                    locator=document.uri or document.remote_id,
                    metadata={"connectorKind": "repository", "source": "import", **lens_metadata},
                )
            )

    return _dedupe_proposals(proposals)


def _document_node_kind(document: NormalizedSourceDocument) -> str:
    if document.connector_kind == "repository":
        target_type = str(document.metadata.get("targetType") or document.metadata.get("target_type") or "").lower()
        identifier = f"{document.title} {document.remote_id} {document.metadata.get('path') or ''}"
        if target_type == "file" or _repository_paths(identifier):
            return "file"
        return "repository"
    if document.source_kind == "url":
        return "source"
    if document.source_kind == "ops-document":
        return "document"
    return "document"


def _source_lens_metadata(document: NormalizedSourceDocument) -> dict[str, list[str]]:
    lenses = ["research"]
    if document.source_kind == "repository" or document.connector_kind == "repository":
        lenses.append("engineering")
    if document.source_kind == "ops-document":
        lenses.append("ops")
    return {"extractionLenses": lenses}


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("::".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _upload_documents(target: dict[str, Any], settings: dict[str, Any]) -> list[NormalizedSourceDocument]:
    files = settings.get("files")
    if isinstance(files, list):
        return [_document_from_mapping("upload", item, target, index) for index, item in enumerate(files)]
    return [
        _document_from_mapping(
            "upload",
            {
                "title": target["title"],
                "content": settings.get("content", ""),
                "kind": _source_kind_for_content(str(settings.get("content", "")), settings.get("mimeType") or settings.get("mime_type")),
                "uri": settings.get("uri"),
                "remoteId": target["remote_id"],
            },
            target,
            0,
        )
    ]


async def _url_document(target: dict[str, Any], settings: dict[str, Any]) -> NormalizedSourceDocument:
    uri = settings.get("uri") or target["remote_id"]
    raw = settings.get("content")
    if not raw:
        raw = await fetch_url_text(uri)
    title = settings.get("title") or _html_title(raw) or target["title"]
    text = normalize_text(_strip_html(raw))
    return _make_document(
        connector_kind="url",
        source_kind="url",
        title=title,
        text=text,
        uri=uri,
        remote_id=target["remote_id"],
        remote_url=uri,
        metadata={"targetType": target["target_type"]},
    )


def _repository_documents(target: dict[str, Any], settings: dict[str, Any]) -> list[NormalizedSourceDocument]:
    files = settings.get("files")
    if isinstance(files, list):
        return [_document_from_mapping("repository", item, target, index) for index, item in enumerate(files)]
    return [
        _make_document(
            connector_kind="repository",
            source_kind="repository",
            title=target["title"],
            text=normalize_for_kind("repository", str(settings.get("content", ""))),
            uri=settings.get("uri"),
            remote_id=target["remote_id"],
            remote_parent_id=target.get("parent_remote_id"),
            remote_url=settings.get("remoteUrl") or settings.get("remote_url"),
            metadata={"targetType": target["target_type"], "path": settings.get("path")},
        )
    ]


async def _google_documents(
    target: dict[str, Any],
    settings: dict[str, Any],
    token_json: dict[str, Any],
) -> list[NormalizedSourceDocument]:
    documents = settings.get("documents") or settings.get("files")
    if isinstance(documents, list):
        return [_document_from_mapping("google-workspace", item, target, index) for index, item in enumerate(documents)]

    access_token = token_json.get("access_token")
    if not access_token:
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        if target["target_type"] == "folder":
            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={
                    "q": f"'{target['remote_id']}' in parents and trashed = false",
                    "fields": "files(id,name,mimeType,modifiedTime,webViewLink,parents)",
                },
            )
            response.raise_for_status()
            files = response.json().get("files", [])
        else:
            response = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{target['remote_id']}",
                params={"fields": "id,name,mimeType,modifiedTime,webViewLink,parents"},
            )
            response.raise_for_status()
            files = [response.json()]

        docs: list[NormalizedSourceDocument] = []
        for item in files:
            content = await _download_google_file(client, item)
            docs.append(
                _make_document(
                    connector_kind="google-workspace",
                    source_kind=_google_source_kind(item.get("mimeType", "")),
                    title=item.get("name") or target["title"],
                    text=content,
                    uri=item.get("webViewLink"),
                    remote_id=item.get("id") or target["remote_id"],
                    remote_parent_id=(item.get("parents") or [target.get("parent_remote_id")])[0],
                    remote_modified_at=_parse_datetime(item.get("modifiedTime")),
                    remote_url=item.get("webViewLink"),
                    metadata={"mimeType": item.get("mimeType"), "targetType": target["target_type"]},
                )
            )
        return docs


async def _download_google_file(client: httpx.AsyncClient, item: dict[str, Any]) -> str:
    file_id = item.get("id")
    mime_type = item.get("mimeType", "")
    if mime_type.startswith("application/vnd.google-apps."):
        response = await client.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
            params={"mimeType": "text/plain"},
        )
    else:
        response = await client.get(f"https://www.googleapis.com/drive/v3/files/{file_id}", params={"alt": "media"})
    response.raise_for_status()
    return normalize_text(response.text)


async def _notion_documents(
    target: dict[str, Any],
    settings: dict[str, Any],
    token_json: dict[str, Any],
) -> list[NormalizedSourceDocument]:
    pages = settings.get("pages")
    if isinstance(pages, list):
        return [_document_from_mapping("notion", item, target, index) for index, item in enumerate(pages)]

    access_token = token_json.get("access_token")
    if not access_token:
        return []

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": str(token_json.get("notion_version") or "2022-06-28"),
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        if target["target_type"] == "database":
            response = await client.post(f"https://api.notion.com/v1/databases/{target['remote_id']}/query", json={})
            response.raise_for_status()
            pages = response.json().get("results", [])
        else:
            response = await client.get(f"https://api.notion.com/v1/pages/{target['remote_id']}")
            response.raise_for_status()
            pages = [response.json()]

        docs = []
        for page in pages:
            page_id = page.get("id") or target["remote_id"]
            blocks = await _notion_blocks(client, page_id)
            title = _notion_title(page) or target["title"]
            text = normalize_text("\n".join(_notion_block_text(block) for block in blocks if _notion_block_text(block)))
            docs.append(
                _make_document(
                    connector_kind="notion",
                    source_kind="markdown",
                    title=title,
                    text=text,
                    uri=page.get("url"),
                    remote_id=page_id,
                    remote_parent_id=_notion_parent_id(page),
                    remote_modified_at=_parse_datetime(page.get("last_edited_time")),
                    remote_url=page.get("url"),
                    metadata={"targetType": target["target_type"], "properties": page.get("properties", {})},
                )
            )
        return docs


async def _notion_blocks(client: httpx.AsyncClient, block_id: str, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 8:
        return []
    results: list[dict[str, Any]] = []
    cursor = None
    while True:
        response = await client.get(
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            params={key: value for key, value in {"start_cursor": cursor, "page_size": 100}.items() if value},
        )
        response.raise_for_status()
        body = response.json()
        for block in body.get("results", []):
            results.append(block)
            if block.get("has_children"):
                results.extend(await _notion_blocks(client, block["id"], depth + 1))
        if not body.get("has_more"):
            break
        cursor = body.get("next_cursor")
    return results


def _document_from_mapping(connector_kind: ConnectorKind, item: dict[str, Any], target: dict[str, Any], index: int) -> NormalizedSourceDocument:
    title = str(item.get("title") or item.get("name") or target["title"])
    remote_id = str(item.get("remoteId") or item.get("remote_id") or item.get("id") or f"{target['remote_id']}:{index}")
    content = item.get("content")
    if content is None:
        content = item.get("text", "")
    source_kind = item.get("kind") or _source_kind_for_content(str(content), item.get("mimeType") or item.get("mime_type"))
    text = str(content).strip() if source_kind == "markdown" else normalize_for_kind(source_kind, str(content))
    return _make_document(
        connector_kind=connector_kind,
        source_kind=source_kind,
        title=title,
        text=text,
        uri=item.get("uri") or item.get("url"),
        remote_id=remote_id,
        remote_parent_id=item.get("remoteParentId") or item.get("remote_parent_id") or target.get("parent_remote_id"),
        remote_modified_at=_parse_datetime(item.get("remoteModifiedAt") or item.get("remote_modified_at")),
        remote_url=item.get("remoteUrl") or item.get("remote_url") or item.get("url"),
        metadata={key: value for key, value in item.items() if key not in {"content", "text"}},
    )


def _make_document(
    *,
    connector_kind: ConnectorKind,
    source_kind: SourceKind,
    title: str,
    text: str,
    uri: str | None,
    remote_id: str,
    remote_parent_id: str | None = None,
    remote_modified_at: datetime | None = None,
    remote_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedSourceDocument:
    chunks = _chunks_from_text(text, remote_id=remote_id, title=title)
    return NormalizedSourceDocument(
        connector_kind=connector_kind,
        source_kind=source_kind,
        title=title,
        text=text,
        uri=uri,
        remote_id=remote_id,
        remote_parent_id=remote_parent_id,
        remote_modified_at=remote_modified_at,
        remote_url=remote_url,
        metadata=metadata or {},
        chunks=chunks,
    )


def _chunks_from_text(text: str, *, remote_id: str, title: str) -> list[NormalizedSourceChunk]:
    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        lines = [text]
    chunks: list[NormalizedSourceChunk] = []
    heading_path: list[str] = []
    paragraph_buffer: list[str] = []
    paragraph_start = 0

    def flush_paragraph(ordinal: int) -> None:
        nonlocal paragraph_buffer, paragraph_start
        if not paragraph_buffer:
            return
        paragraph = normalize_text(" ".join(paragraph_buffer))
        if paragraph:
            chunks.append(_chunk(remote_id, "paragraph", ordinal, paragraph, heading_path, paragraph_start))
        paragraph_buffer = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            flush_paragraph(index)
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match or (len(stripped) <= 90 and stripped.endswith(":")):
            flush_paragraph(index)
            level = len(heading_match.group(1)) if heading_match else min(6, len(heading_path) + 1)
            heading = heading_match.group(2).strip() if heading_match else stripped.strip(":")
            heading_path = [*heading_path[: level - 1], heading]
            chunks.append(_chunk(remote_id, "heading", index, heading, heading_path, index))
            continue
        if not paragraph_buffer:
            paragraph_start = index
        paragraph_buffer.append(stripped)
    flush_paragraph(len(lines))

    if not chunks and text.strip():
        chunks.append(_chunk(remote_id, "document", 0, title, [title], 0))
        chunks.append(_chunk(remote_id, "paragraph", 1, normalize_text(text), [title], 1))
    return chunks


def _chunk(remote_id: str, block_type: str, ordinal: int, text: str, heading_path: list[str], line_index: int) -> NormalizedSourceChunk:
    checksum = hashlib.sha256(f"{remote_id}:{ordinal}:{text}".encode("utf-8")).hexdigest()
    return NormalizedSourceChunk(
        stable_key=f"{remote_id}:{ordinal}:{block_type}",
        parent_stable_key=None,
        heading_path=heading_path,
        block_type=block_type,
        ordinal=ordinal,
        text=text,
        links=_links(text),
        mentions=_mentions(text),
        checksum=checksum,
        locator=f"{remote_id}#line-{line_index + 1}",
    )


def _node_proposal(
    *,
    node_id: str,
    label: str,
    node_kind: str,
    summary: str,
    confidence: float,
    locator: str,
    metadata: dict[str, Any],
) -> GeneratedProposal:
    return GeneratedProposal(
        kind="content_node",
        proposed_value={
            "id": node_id,
            "label": label,
            "kind": node_kind,
            "summary": summary,
            "topicIds": [],
            "metadata": metadata,
        },
        confidence=confidence,
        locator=locator,
    )


def _edge_proposal(
    *,
    edge_id: str,
    source_node_id: str,
    target_node_id: str,
    source_label: str,
    target_label: str,
    relation: str,
    confidence: float,
    locator: str,
    metadata: dict[str, Any],
) -> GeneratedProposal:
    return GeneratedProposal(
        kind="semantic_edge",
        proposed_value={
            "id": edge_id,
            "sourceNodeId": source_node_id,
            "targetNodeId": target_node_id,
            "sourceLabel": source_label,
            "targetLabel": target_label,
            "relation": relation,
            "weight": confidence,
            "metadata": metadata,
        },
        confidence=confidence,
        locator=locator,
    )


def _dedupe_proposals(proposals: list[GeneratedProposal]) -> list[GeneratedProposal]:
    seen: set[str] = set()
    deduped: list[GeneratedProposal] = []
    for proposal in proposals:
        value = proposal.proposed_value
        key = f"{proposal.kind}:{value.get('id') or value.get('label') or value.get('sourceNodeId')}:{value.get('targetNodeId')}:{value.get('relation')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(proposal)
    return deduped


def _links(text: str) -> list[str]:
    markdown_links = re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", text)
    bare_links = re.findall(r"https?://[^\s)>,]+", text)
    return list(dict.fromkeys([*markdown_links, *bare_links]))


def _mentions(text: str) -> list[str]:
    notion_mentions = re.findall(r"\[\[([^\]]+)\]\]", text)
    at_mentions = re.findall(r"(?<!\w)@([A-Za-z][\w .-]{1,80})", text)
    return list(dict.fromkeys([*notion_mentions, *at_mentions]))


def _repository_dependencies(text: str) -> set[str]:
    dependencies: set[str] = set()
    patterns = [
        r"\bimport\s+([A-Za-z_][\w.]*)",
        r"\bfrom\s+([A-Za-z_][\w.]*)\s+import\b",
        r"\bimport\s+[\"']([^\"']+)[\"']",
        r"\bpackage\s+url:\s*[\"']([^\"']+)[\"']",
        r"\"([@A-Za-z0-9_.\-/]+)\"\s*:\s*\"[\^~]?\d",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            value = match if isinstance(match, str) else next((part for part in match if part), "")
            if value:
                dependencies.add(value.split("/")[0] if value.startswith("@") else value)
    return dependencies


def _repository_paths(text: str) -> set[str]:
    return {
        path
        for path in re.findall(r"(?:^|\s)([\w./-]+\.(?:py|ts|tsx|js|mjs|json|md|yml|yaml|go|rs|java))(?::|\s|$)", text)
    }


def _repository_symbols(text: str) -> set[str]:
    return {
        symbol
        for symbol in re.findall(
            r"\b(?:class|def|function|interface|type|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
            text,
        )
    }


def _source_kind_from_mime(mime_type: str | None) -> SourceKind:
    value = (mime_type or "").lower()
    if "markdown" in value:
        return "markdown"
    if "pdf" in value:
        return "pdf"
    if "json" in value or "csv" in value or "spreadsheet" in value:
        return "text"
    return "text"


def _source_kind_for_content(content: str, mime_type: str | None) -> SourceKind:
    if mime_type:
        return _source_kind_from_mime(mime_type)
    if re.search(r"(^|\n)#{1,6}\s+", content):
        return "markdown"
    return "text"


def _google_source_kind(mime_type: str) -> SourceKind:
    if "document" in mime_type or "presentation" in mime_type or "spreadsheet" in mime_type:
        return "markdown"
    if "pdf" in mime_type:
        return "pdf"
    return "text"


def _strip_html(raw: str) -> str:
    without_scripts = re.sub(r"<(script|style).*?</\1>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    with_breaks = re.sub(r"</(h[1-6]|p|li|div|section|article)>", "\n", without_scripts, flags=re.IGNORECASE)
    return unescape(re.sub(r"<[^>]+>", " ", with_breaks))


def _html_title(raw: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.DOTALL | re.IGNORECASE)
    return normalize_text(unescape(match.group(1))) if match else None


def _label_for_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    label = f"{parsed.netloc}/{path}" if path else parsed.netloc
    return label[:220] or url[:220]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _notion_title(page: dict[str, Any]) -> str | None:
    properties = page.get("properties", {})
    for property_value in properties.values():
        if property_value.get("type") == "title":
            title = "".join(item.get("plain_text", "") for item in property_value.get("title", []))
            if title:
                return title
    return None


def _notion_parent_id(page: dict[str, Any]) -> str | None:
    parent = page.get("parent", {})
    return parent.get("page_id") or parent.get("database_id") or parent.get("workspace")


def _notion_block_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    payload = block.get(block_type, {}) if block_type else {}
    rich_text = payload.get("rich_text") or payload.get("title") or []
    text = "".join(item.get("plain_text", "") for item in rich_text)
    if block_type and block_type.startswith("heading_") and text:
        return f"# {text}"
    return text
