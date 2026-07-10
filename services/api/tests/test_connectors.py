from __future__ import annotations

import asyncio
import base64
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


def test_github_incremental_compare_fetches_changed_files_and_tombstones_deletions(monkeypatch) -> None:
    issue_since: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/acme/repo/commits/HEAD"):
            return httpx.Response(
                200,
                json={"sha": "head-sha", "commit": {"committer": {"date": "2026-07-10T10:00:00Z"}}},
            )
        if request.url.path.endswith("/repos/acme/repo/compare/base-sha...head-sha"):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {"filename": "docs/changed.md", "status": "modified", "sha": "blob-1", "size": 50},
                        {"filename": "src/removed.py", "status": "removed", "sha": "blob-2", "size": 20},
                        {
                            "filename": "src/renamed.py",
                            "previous_filename": "src/old-name.py",
                            "status": "renamed",
                            "sha": "blob-3",
                            "size": 30,
                        },
                    ]
                },
            )
        if "/contents/" in request.url.path:
            path = request.url.path.split("/contents/", 1)[1]
            return httpx.Response(
                200,
                json={
                    "content": base64.b64encode(f"content for {path}".encode()).decode(),
                    "html_url": f"https://github.test/acme/repo/blob/head-sha/{path}",
                },
            )
        if request.url.path.endswith("/repos/acme/repo/issues"):
            issue_since.append(str(request.url.params.get("since") or ""))
            return httpx.Response(200, json=[])
        raise AssertionError(f"Unexpected request {request.method} {request.url}")

    _mock_async_client(monkeypatch, handler)
    result = asyncio.run(
        connectors.fetch_connector_documents(
            account={"kind": "repository", "settings": {}},
            target={
                "target_type": "repository",
                "remote_id": "acme/repo",
                "title": "Repository",
                "sync_settings": {
                    "provider": "github",
                    "repository": "acme/repo",
                    "connector_cursor": "github:base-sha:1783674000",
                    "existing_remote_ids": [
                        "acme/repo:docs/changed.md",
                        "acme/repo:src/removed.py",
                        "acme/repo:src/old-name.py",
                    ],
                },
            },
            token_json={"access_token": "github-token"},
        )
    )

    assert [document.remote_id for document in result.documents] == [
        "acme/repo:docs/changed.md",
        "acme/repo:src/renamed.py",
    ]
    assert result.documents[0].metadata["baseCommitSha"] == "base-sha"
    assert result.documents[1].metadata["previousPath"] == "src/old-name.py"
    assert result.tombstone_remote_ids == (
        "acme/repo:src/old-name.py",
        "acme/repo:src/removed.py",
    )
    assert result.cursor.startswith("github:head-sha:")
    assert result.full_snapshot is False
    assert issue_since and issue_since[0]


def test_google_drive_watch_renews_expiring_channel_and_persists_verification_state(monkeypatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url}")
        if request.url.path.endswith("/changes"):
            return httpx.Response(200, json={"newStartPageToken": "cursor-2", "changes": []})
        if request.url.path.endswith("/channels/stop"):
            return httpx.Response(204)
        if request.url.path.endswith("/changes/watch"):
            body = json.loads(request.content)
            assert body["address"] == "https://graphview.example.test/api/v1/connectors/google/target-1/webhook"
            assert body["token"]
            return httpx.Response(
                200,
                json={
                    "id": body["id"],
                    "resourceId": "resource-new",
                    "resourceUri": "https://www.googleapis.com/drive/v3/changes",
                    "expiration": body["expiration"],
                },
            )
        raise AssertionError(f"Unexpected request {request.method} {request.url}")

    _mock_async_client(monkeypatch, handler)
    tokens = {
        "access_token": "valid",
        "expires_at": time.time() + 3600,
        "drive_watch": {
            "channel_id": "channel-old",
            "resource_id": "resource-old",
            "expiration_ms": 1,
            "channel_token": "old-token",
            "page_token": "cursor-1",
            "webhook_url": "https://graphview.example.test/api/v1/connectors/google/target-1/webhook",
        },
    }
    result = asyncio.run(
        connectors.fetch_connector_documents(
            account={"kind": "google-workspace", "settings": {}},
            target={
                "id": "target-1",
                "target_type": "folder",
                "remote_id": "folder-1",
                "title": "Drive",
                "sync_settings": {
                    "connector_cursor": "google:cursor-1",
                    "watch_webhook_url": "https://graphview.example.test/api/v1/connectors/google/target-1/webhook",
                },
            },
            token_json=tokens,
        )
    )

    assert result.cursor == "google:cursor-2"
    assert tokens["drive_watch"]["resource_id"] == "resource-new"
    assert tokens["drive_watch"]["page_token"] == "cursor-2"
    assert tokens["drive_watch"]["channel_token"] != "old-token"
    assert any("channels/stop" in call for call in calls)
    assert any("changes/watch" in call for call in calls)


def test_github_delta_at_api_limit_falls_back_to_safe_full_snapshot(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/commits/HEAD"):
            return httpx.Response(200, json={"sha": "head-sha", "commit": {"committer": {"date": "2026-07-10T10:00:00Z"}}})
        if "/compare/" in request.url.path:
            return httpx.Response(
                200,
                json={"files": [{"filename": f"changed-{index}.md", "status": "modified", "size": 10} for index in range(300)]},
            )
        if "/git/trees/head-sha" in request.url.path:
            return httpx.Response(
                200,
                json={"truncated": False, "tree": [{"path": "current.md", "type": "blob", "size": 20, "sha": "blob-current"}]},
            )
        if request.url.path.endswith("/contents/current.md"):
            return httpx.Response(
                200,
                json={"content": base64.b64encode(b"current full snapshot").decode(), "html_url": "https://github.test/current.md"},
            )
        raise AssertionError(f"Unexpected request {request.method} {request.url}")

    _mock_async_client(monkeypatch, handler)
    result = asyncio.run(
        connectors.fetch_connector_documents(
            account={"kind": "repository", "settings": {}},
            target={
                "target_type": "repository",
                "remote_id": "acme/repo",
                "title": "Repository",
                "sync_settings": {
                    "provider": "github",
                    "connector_cursor": "github:base-sha:1783674000",
                    "include_issues": False,
                },
            },
            token_json={"access_token": "github-token"},
        )
    )

    assert [document.remote_id for document in result.documents] == ["acme/repo:current.md"]
    assert result.full_snapshot is True


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
