from __future__ import annotations

import hashlib
import base64
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import jwt

from graphview_api.ingestion import GeneratedProposal, fetch_safe_url_text, normalize_for_kind, normalize_text

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


@dataclass(frozen=True)
class ConnectorFetchResult:
    documents: list[NormalizedSourceDocument]
    cursor: str | None = None
    tombstone_remote_ids: tuple[str, ...] = ()
    full_snapshot: bool = True


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
) -> ConnectorFetchResult:
    kind = account["kind"]
    settings = {**account.get("settings", {}), **target.get("sync_settings", {})}
    if kind == "upload":
        documents = _upload_documents(target, settings)
        return _snapshot_result(documents)
    if kind == "url":
        return _snapshot_result([await _url_document(target, settings)])
    if kind == "repository":
        return await _repository_fetch_result(target, settings, token_json or {})
    if kind == "google-workspace":
        return await _google_documents(target, settings, token_json or {})
    if kind == "notion":
        return _snapshot_result(await _notion_documents(target, settings, token_json or {}))
    raise ValueError(f"Unsupported connector kind: {kind}")


def _snapshot_result(documents: list[NormalizedSourceDocument]) -> ConnectorFetchResult:
    digest = hashlib.sha256("\n".join(sorted(document.remote_id for document in documents)).encode("utf-8")).hexdigest()
    return ConnectorFetchResult(documents=documents, cursor=f"snapshot:{digest}")


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
        allowed_hosts = {str(host).strip().lower() for host in settings.get("allowed_hosts", []) if str(host).strip()}
        if settings.get("require_allowed_hosts") and not allowed_hosts:
            raise ValueError("URL connector requires an outbound host allowlist in production")
        raw = await fetch_safe_url_text(uri, allowed_hosts=allowed_hosts or None)
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


async def _repository_documents(
    target: dict[str, Any],
    settings: dict[str, Any],
    token_json: dict[str, Any],
) -> list[NormalizedSourceDocument]:
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


async def _repository_fetch_result(
    target: dict[str, Any],
    settings: dict[str, Any],
    token_json: dict[str, Any],
) -> ConnectorFetchResult:
    if settings.get("provider") == "github" or token_json.get("installation_id"):
        return await _github_repository_documents(target, settings, token_json)
    return _snapshot_result(await _repository_documents(target, settings, token_json))


async def _github_repository_documents(
    target: dict[str, Any],
    settings: dict[str, Any],
    token_json: dict[str, Any],
) -> ConnectorFetchResult:
    repository = str(settings.get("repository") or target["remote_id"])
    if repository.count("/") != 1:
        raise ValueError("GitHub repository target must be owner/name")
    api_url = str(settings.get("api_url") or "https://api.github.com").rstrip("/")
    access_token = token_json.get("access_token")
    if access_token and float(token_json.get("expires_at") or 0) and float(token_json["expires_at"]) <= time.time() + 120:
        access_token = None
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        if not access_token:
            app_id = str(token_json.get("app_id") or "")
            installation_id = str(token_json.get("installation_id") or "")
            private_key = str(token_json.get("private_key") or "")
            if not app_id or not installation_id or not private_key:
                raise ValueError("GitHub App credentials require app_id, installation_id, and private_key")
            now_seconds = int(time.time())
            app_jwt = jwt.encode({"iat": now_seconds - 60, "exp": now_seconds + 540, "iss": app_id}, private_key, algorithm="RS256")
            token_response = await client.post(
                f"{api_url}/app/installations/{installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
            )
            token_response.raise_for_status()
            issued_token = token_response.json()
            access_token = issued_token["token"]
            token_json["access_token"] = access_token
            if issued_token.get("expires_at"):
                parsed_expiry = _parse_datetime(str(issued_token["expires_at"]))
                if parsed_expiry is not None:
                    token_json["expires_at"] = parsed_expiry.timestamp()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        reference = str(settings.get("ref") or "HEAD")
        commit_response = await client.get(f"{api_url}/repos/{repository}/commits/{reference}", headers=headers)
        commit_response.raise_for_status()
        commit = commit_response.json()
        commit_sha = str(commit["sha"])
        cursor = str(settings.get("connector_cursor") or "")
        previous_commit_sha, previous_sync_seconds = _parse_github_cursor(cursor)
        incremental = previous_commit_sha is not None
        tombstones: set[str] = set()
        complete_snapshot = not incremental
        if incremental and previous_commit_sha != commit_sha:
            try:
                tree_items, tombstones = await _github_compare_files(
                    client,
                    api_url=api_url,
                    repository=repository,
                    base_sha=previous_commit_sha,
                    head_sha=commit_sha,
                    headers=headers,
                )
            except ValueError as error:
                if "300-file API limit" not in str(error):
                    raise
                tree_response = await client.get(
                    f"{api_url}/repos/{repository}/git/trees/{commit_sha}",
                    params={"recursive": "1"},
                    headers=headers,
                )
                tree_response.raise_for_status()
                tree = tree_response.json()
                if tree.get("truncated"):
                    raise ValueError("GitHub tree response was truncated; narrow the repository target before syncing") from error
                tree_items = tree.get("tree", [])
                tombstones = set()
                incremental = False
                complete_snapshot = True
        elif incremental:
            tree_items = []
        else:
            tree_response = await client.get(
                f"{api_url}/repos/{repository}/git/trees/{commit_sha}",
                params={"recursive": "1"},
                headers=headers,
            )
            tree_response.raise_for_status()
            tree = tree_response.json()
            if tree.get("truncated"):
                raise ValueError("GitHub tree response was truncated; narrow the repository target before syncing")
            tree_items = tree.get("tree", [])
        documents: list[NormalizedSourceDocument] = []
        allowed_suffixes = tuple(settings.get("allowed_suffixes") or [".md", ".txt", ".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".go", ".rs", ".java"])
        max_files = min(2_000, max(1, int(settings.get("max_files", 500))))
        existing_remote_ids = {str(value) for value in settings.get("existing_remote_ids", [])}
        for item in tree_items:
            path = str(item.get("path") or item.get("filename") or "")
            remote_id = f"{repository}:{path}"
            previous_path = str(item.get("previous_filename") or "")
            if previous_path and previous_path != path:
                tombstones.add(f"{repository}:{previous_path}")
            if item.get("status") == "removed":
                tombstones.add(remote_id)
                continue
            if item.get("type") != "blob" or not path.endswith(allowed_suffixes) or int(item.get("size") or 0) > 1_000_000:
                if incremental and remote_id in existing_remote_ids:
                    tombstones.add(remote_id)
                continue
            content_response = await client.get(f"{api_url}/repos/{repository}/contents/{path}", params={"ref": commit_sha}, headers=headers)
            content_response.raise_for_status()
            content_document = content_response.json()
            content = base64.b64decode(content_document.get("content", "")).decode("utf-8", errors="replace")
            documents.append(
                _make_document(
                    connector_kind="repository",
                    source_kind="repository",
                    title=path,
                    text=normalize_for_kind("repository", content),
                    uri=content_document.get("html_url"),
                    remote_id=remote_id,
                    remote_parent_id=repository,
                    remote_modified_at=_parse_datetime(commit.get("commit", {}).get("committer", {}).get("date")),
                    remote_url=content_document.get("html_url"),
                    metadata={
                        "targetType": "file",
                        "path": path,
                        "repository": repository,
                        "commitSha": commit_sha,
                        "blobSha": item.get("sha"),
                        "baseCommitSha": previous_commit_sha,
                        "changeStatus": item.get("status") or "snapshot",
                        "previousPath": previous_path or None,
                    },
                )
            )
            if len(documents) >= max_files:
                complete_snapshot = False
                break
        if bool(settings.get("include_issues", True)):
            page = 1
            while page <= 10 and len(documents) < max_files:
                issue_params: dict[str, Any] = {
                    "state": "all",
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc",
                }
                if incremental and previous_sync_seconds:
                    issue_params["since"] = datetime.fromtimestamp(previous_sync_seconds, tz=UTC).isoformat()
                issues_response = await client.get(
                    f"{api_url}/repos/{repository}/issues",
                    params=issue_params,
                    headers=headers,
                )
                issues_response.raise_for_status()
                issues = issues_response.json()
                for issue in issues:
                    number = issue.get("number")
                    is_pull_request = "pull_request" in issue
                    documents.append(
                        _make_document(
                            connector_kind="repository",
                            source_kind="repository",
                            title=f"{'PR' if is_pull_request else 'Issue'} #{number}: {issue.get('title') or ''}",
                            text=normalize_for_kind("repository", f"{issue.get('title') or ''}\n\n{issue.get('body') or ''}"),
                            uri=issue.get("html_url"),
                            remote_id=f"{repository}:{'pr' if is_pull_request else 'issue'}:{number}",
                            remote_parent_id=repository,
                            remote_modified_at=_parse_datetime(issue.get("updated_at")),
                            remote_url=issue.get("html_url"),
                            metadata={
                                "targetType": "pull_request" if is_pull_request else "issue",
                                "repository": repository,
                                "number": number,
                                "state": issue.get("state"),
                                "labels": [label.get("name") for label in issue.get("labels", [])],
                            },
                        )
                    )
                    if len(documents) >= max_files:
                        complete_snapshot = False
                        break
                if len(issues) < 100:
                    break
                page += 1
            if page > 10:
                complete_snapshot = False
        return ConnectorFetchResult(
            documents=documents,
            cursor=f"github:{commit_sha}:{int(time.time())}",
            tombstone_remote_ids=tuple(sorted(tombstones)),
            full_snapshot=complete_snapshot,
        )


def _parse_github_cursor(cursor: str) -> tuple[str | None, float | None]:
    if not cursor.startswith("github:"):
        return None, None
    values = cursor.split(":", 2)
    commit_sha = values[1] if len(values) > 1 and values[1] else None
    try:
        sync_seconds = float(values[2]) if len(values) > 2 else None
    except ValueError:
        sync_seconds = None
    return commit_sha, sync_seconds


async def _github_compare_files(
    client: httpx.AsyncClient,
    *,
    api_url: str,
    repository: str,
    base_sha: str,
    head_sha: str,
    headers: dict[str, str],
) -> tuple[list[dict[str, Any]], set[str]]:
    response = await client.get(
        f"{api_url}/repos/{repository}/compare/{base_sha}...{head_sha}",
        headers=headers,
    )
    response.raise_for_status()
    page_files = response.json().get("files", [])
    if len(page_files) >= 300:
        raise ValueError("GitHub comparison reached the 300-file API limit; perform a narrowed full sync")
    files: list[dict[str, Any]] = []
    tombstones: set[str] = set()
    for item in page_files:
        normalized = {**item, "path": item.get("filename"), "type": "blob"}
        files.append(normalized)
        if item.get("status") == "removed":
            tombstones.add(f"{repository}:{item.get('filename')}")
        if item.get("status") == "renamed" and item.get("previous_filename"):
            tombstones.add(f"{repository}:{item['previous_filename']}")
    return files, tombstones


async def _google_documents(
    target: dict[str, Any],
    settings: dict[str, Any],
    token_json: dict[str, Any],
) -> ConnectorFetchResult:
    documents = settings.get("documents") or settings.get("files")
    if isinstance(documents, list):
        return _snapshot_result([_document_from_mapping("google-workspace", item, target, index) for index, item in enumerate(documents)])

    access_token = await _google_access_token(token_json)
    if not access_token:
        return _snapshot_result([])

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        connector_cursor = str(settings.get("connector_cursor") or "")
        existing_remote_ids = {str(value) for value in settings.get("existing_remote_ids", [])}
        tombstones: set[str] = set()
        incremental = connector_cursor.startswith("google:")
        next_cursor: str | None = None
        if incremental:
            files, tombstones, next_cursor = await _google_changes(
                client,
                connector_cursor.removeprefix("google:"),
                target=target,
                existing_remote_ids=existing_remote_ids,
            )
        elif target["target_type"] == "folder":
            start_token_response = await client.get("https://www.googleapis.com/drive/v3/changes/startPageToken")
            start_token_response.raise_for_status()
            next_cursor = str(start_token_response.json()["startPageToken"])
            files = []
            page_token = None
            while True:
                response = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    params={
                        "q": f"'{target['remote_id']}' in parents and trashed = false",
                        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,parents,trashed)",
                        "pageSize": 1000,
                        **({"pageToken": page_token} if page_token else {}),
                    },
                )
                response.raise_for_status()
                body = response.json()
                files.extend(body.get("files", []))
                page_token = body.get("nextPageToken")
                if not page_token:
                    break
        else:
            start_token_response = await client.get("https://www.googleapis.com/drive/v3/changes/startPageToken")
            start_token_response.raise_for_status()
            next_cursor = str(start_token_response.json()["startPageToken"])
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
        watch_cursor = next_cursor or connector_cursor.removeprefix("google:")
        if watch_cursor:
            await _ensure_google_drive_watch(
                client,
                settings=settings,
                token_json=token_json,
                page_token=watch_cursor,
            )
        return ConnectorFetchResult(
            documents=docs,
            cursor=f"google:{next_cursor}" if next_cursor else connector_cursor or None,
            tombstone_remote_ids=tuple(sorted(tombstones)),
            full_snapshot=not incremental,
        )


async def _google_access_token(token_json: dict[str, Any]) -> str | None:
    access_token = token_json.get("access_token")
    expires_at = float(token_json.get("expires_at") or 0)
    if access_token and (not expires_at or expires_at > time.time() + 120):
        return str(access_token)
    if not all(token_json.get(key) for key in ("refresh_token", "client_id", "client_secret")):
        return str(access_token) if access_token else None
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_json["refresh_token"],
                "client_id": token_json["client_id"],
                "client_secret": token_json["client_secret"],
            },
        )
        response.raise_for_status()
        refreshed = response.json()
        token_json["access_token"] = str(refreshed["access_token"])
        token_json["expires_at"] = time.time() + int(refreshed.get("expires_in") or 3600)
        if refreshed.get("scope"):
            token_json["scope"] = refreshed["scope"]
        if refreshed.get("token_type"):
            token_json["token_type"] = refreshed["token_type"]
        return str(token_json["access_token"])


async def _ensure_google_drive_watch(
    client: httpx.AsyncClient,
    *,
    settings: dict[str, Any],
    token_json: dict[str, Any],
    page_token: str,
) -> None:
    webhook_url = str(settings.get("watch_webhook_url") or "").strip()
    if not webhook_url:
        return
    parsed = urlparse(webhook_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Google Drive watch webhook URL must be an absolute HTTPS URL")
    current = token_json.get("drive_watch") if isinstance(token_json.get("drive_watch"), dict) else {}
    renewal_window_ms = min(86_400_000, max(300_000, int(settings.get("watch_renewal_window_ms") or 21_600_000)))
    if (
        current.get("webhook_url") == webhook_url
        and int(current.get("expiration_ms") or 0) > int(time.time() * 1000) + renewal_window_ms
        and current.get("page_token") == page_token
    ):
        return
    if current.get("channel_id") and current.get("resource_id"):
        stop = await client.post(
            "https://www.googleapis.com/drive/v3/channels/stop",
            json={"id": current["channel_id"], "resourceId": current["resource_id"]},
        )
        if stop.status_code not in {200, 204, 404, 410}:
            stop.raise_for_status()
    duration_seconds = min(604_800, max(3_600, int(settings.get("watch_duration_seconds") or 518_400)))
    requested_expiration = int((time.time() + duration_seconds) * 1000)
    channel_token = secrets.token_urlsafe(32)
    channel_id = str(uuid4())
    response = await client.post(
        "https://www.googleapis.com/drive/v3/changes/watch",
        params={"pageToken": page_token},
        json={
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
            "expiration": requested_expiration,
        },
    )
    response.raise_for_status()
    watch = response.json()
    token_json["drive_watch"] = {
        "channel_id": str(watch.get("id") or channel_id),
        "resource_id": str(watch["resourceId"]),
        "resource_uri": watch.get("resourceUri"),
        "expiration_ms": int(watch.get("expiration") or requested_expiration),
        "channel_token": channel_token,
        "page_token": page_token,
        "webhook_url": webhook_url,
    }


async def _google_changes(
    client: httpx.AsyncClient,
    page_token: str,
    *,
    target: dict[str, Any],
    existing_remote_ids: set[str],
) -> tuple[list[dict[str, Any]], set[str], str | None]:
    files: list[dict[str, Any]] = []
    tombstones: set[str] = set()
    next_cursor: str | None = None
    while page_token:
        response = await client.get(
            "https://www.googleapis.com/drive/v3/changes",
            params={
                "pageToken": page_token,
                "pageSize": 1000,
                "includeRemoved": "true",
                "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,webViewLink,parents,trashed))",
            },
        )
        response.raise_for_status()
        body = response.json()
        for change in body.get("changes", []):
            file_id = str(change.get("fileId") or "")
            file = change.get("file") or {}
            parents = {str(value) for value in file.get("parents") or []}
            belongs = (
                (target["target_type"] == "file" and file_id == target["remote_id"])
                or (target["target_type"] == "folder" and target["remote_id"] in parents)
            )
            removed = bool(change.get("removed") or file.get("trashed"))
            moved_out = file_id in existing_remote_ids and target["target_type"] == "folder" and target["remote_id"] not in parents
            if removed or moved_out:
                if file_id in existing_remote_ids:
                    tombstones.add(file_id)
            elif belongs:
                files.append(file)
        page_token = str(body.get("nextPageToken") or "")
        next_cursor = str(body.get("newStartPageToken") or next_cursor or page_token or "") or None
    return files, tombstones, next_cursor


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
            pages = []
            cursor = None
            while True:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{target['remote_id']}/query",
                    json={**({"start_cursor": cursor} if cursor else {}), "page_size": 100},
                )
                response.raise_for_status()
                body = response.json()
                pages.extend(body.get("results", []))
                cursor = body.get("next_cursor")
                if not body.get("has_more") or not cursor:
                    break
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
