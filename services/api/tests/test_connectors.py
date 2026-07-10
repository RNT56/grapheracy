from __future__ import annotations

import asyncio
import json
import time

import httpx

from graphview_api import connectors


def _mock_async_client(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(connectors.httpx, "AsyncClient", factory)


def test_google_refresh_updates_tokens_for_secret_persistence(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://oauth2.googleapis.com/token")
        return httpx.Response(
            200,
            json={"access_token": "fresh-token", "expires_in": 3600, "scope": "drive.readonly", "token_type": "Bearer"},
        )

    _mock_async_client(monkeypatch, handler)
    tokens = {"refresh_token": "refresh", "client_id": "client", "client_secret": "secret", "expires_at": 1}

    access_token = asyncio.run(connectors._google_access_token(tokens))

    assert access_token == "fresh-token"
    assert tokens["access_token"] == "fresh-token"
    assert tokens["expires_at"] > time.time() + 3500
    assert tokens["scope"] == "drive.readonly"


def test_google_change_cursor_handles_pagination_updates_and_tombstones(monkeypatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/changes"):
            token = request.url.params["pageToken"]
            if token == "cursor-1":
                return httpx.Response(
                    200,
                    json={
                        "nextPageToken": "cursor-2",
                        "changes": [
                            {
                                "fileId": "changed",
                                "file": {
                                    "id": "changed",
                                    "name": "Changed",
                                    "mimeType": "text/plain",
                                    "modifiedTime": "2026-07-10T09:00:00Z",
                                    "parents": ["folder-1"],
                                },
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "newStartPageToken": "cursor-3",
                    "changes": [{"fileId": "deleted", "removed": True}],
                },
            )
        if request.url.path.endswith("/files/changed"):
            return httpx.Response(200, text="updated content")
        raise AssertionError(f"Unexpected request {request.method} {request.url}")

    _mock_async_client(monkeypatch, handler)
    result = asyncio.run(
        connectors.fetch_connector_documents(
            account={"kind": "google-workspace", "settings": {}},
            target={
                "target_type": "folder",
                "remote_id": "folder-1",
                "title": "Drive",
                "sync_settings": {
                    "connector_cursor": "google:cursor-1",
                    "existing_remote_ids": ["changed", "deleted"],
                },
            },
            token_json={"access_token": "valid", "expires_at": time.time() + 3600},
        )
    )

    assert [document.remote_id for document in result.documents] == ["changed"]
    assert result.documents[0].text == "updated content"
    assert result.tombstone_remote_ids == ("deleted",)
    assert result.cursor == "google:cursor-3"
    assert result.full_snapshot is False
    assert len([url for url in calls if "/changes?" in url]) == 2


def test_notion_database_and_recursive_blocks_paginate(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/databases/database-1/query"):
            body = json.loads(request.content or b"{}")
            if "start_cursor" not in body:
                return httpx.Response(200, json={"results": [_page("page-1", "One")], "has_more": True, "next_cursor": "next"})
            return httpx.Response(200, json={"results": [_page("page-2", "Two")], "has_more": False})
        if request.url.path.endswith("/blocks/page-1/children"):
            return httpx.Response(200, json={"results": [_paragraph("block-1", "Parent", has_children=True)], "has_more": False})
        if request.url.path.endswith("/blocks/block-1/children"):
            return httpx.Response(200, json={"results": [_paragraph("block-2", "Child")], "has_more": False})
        if request.url.path.endswith("/blocks/page-2/children"):
            return httpx.Response(200, json={"results": [_paragraph("block-3", "Second page")], "has_more": False})
        raise AssertionError(f"Unexpected request {request.method} {request.url}")

    _mock_async_client(monkeypatch, handler)
    result = asyncio.run(
        connectors.fetch_connector_documents(
            account={"kind": "notion", "settings": {}},
            target={"target_type": "database", "remote_id": "database-1", "title": "Database", "sync_settings": {}},
            token_json={"access_token": "notion-token"},
        )
    )

    assert [document.remote_id for document in result.documents] == ["page-1", "page-2"]
    assert "Parent" in result.documents[0].text and "Child" in result.documents[0].text
    assert result.full_snapshot is True


def _page(page_id: str, title: str) -> dict:
    return {
        "id": page_id,
        "url": f"https://notion.test/{page_id}",
        "last_edited_time": "2026-07-10T09:00:00Z",
        "parent": {"type": "database_id", "database_id": "database-1"},
        "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
    }


def _paragraph(block_id: str, text: str, *, has_children: bool = False) -> dict:
    return {
        "id": block_id,
        "type": "paragraph",
        "has_children": has_children,
        "paragraph": {"rich_text": [{"plain_text": text}]},
    }
