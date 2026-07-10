import asyncio
import json
import socket

import httpx

from graphview_api.action_adapters import ActionExecutor
from graphview_api.settings import Settings


class FakeSecrets:
    def get(self, reference: str) -> dict:
        return {
            "github-ref": {"token": "github-token"},
            "webhook-ref": {"secret": "webhook-secret"},
            "smtp-ref": {"username": "mailer", "password": "smtp-secret"},
        }[reference]


def proposal(action_type: str) -> dict:
    return {"id": f"proposal-{action_type}", "action_type": action_type, "title": "Action title", "summary": "Action summary"}


def test_github_issue_adapter_reuses_marker_before_creating() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": 42,
                    "body": "Already created\n<!-- graphview-action:proposal-create_external_ticket -->",
                    "html_url": "https://github.example.test/issues/42",
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    executor = ActionExecutor(Settings(), secret_store=FakeSecrets(), http_client=client)
    result = asyncio.run(
        executor.execute(
            proposal("create_external_ticket"),
            {"credential_ref": "github-ref", "repository": "owner/repository"},
        )
    )
    asyncio.run(client.aclose())

    assert result.external_id == "42"
    assert result.metadata["reused"] is True
    assert [request.method for request in calls] == ["GET"]
    assert calls[0].headers["authorization"] == "Bearer github-token"


def test_signed_workflow_webhook_has_stable_id_and_hmac(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(action_webhook_allowed_hosts="hooks.example.test")
    executor = ActionExecutor(settings, secret_store=FakeSecrets(), http_client=client)
    result = asyncio.run(
        executor.execute(
            proposal("trigger_workflow"),
            {
                "credential_ref": "webhook-ref",
                "destination": "https://hooks.example.test/workflow",
                "event": {"kind": "review.accepted"},
            },
        )
    )
    asyncio.run(client.aclose())

    assert result.external_id == "action-proposal-trigger_workflow"
    assert captured["headers"]["x-graphview-signature"].startswith("v1=")
    assert captured["body"]["event_id"] == result.external_id


def test_smtp_adapter_uses_stable_message_id_and_suppression(monkeypatch) -> None:
    messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def starttls(self): return None
        def login(self, username, password): assert (username, password) == ("mailer", "smtp-secret")
        def send_message(self, message): messages.append(message)

    monkeypatch.setattr("graphview_api.action_adapters.smtplib.SMTP", FakeSMTP)
    settings = Settings(smtp_host="smtp.example.test", smtp_from_address="graphview@example.test")
    executor = ActionExecutor(settings, secret_store=FakeSecrets())
    result = asyncio.run(
        executor.execute(
            proposal("create_notification"),
            {"credential_ref": "smtp-ref", "to": "owner@example.test", "body": "Review complete"},
        )
    )

    assert result.external_id == "<graphview-proposal-create_notification@example.test>"
    assert messages[0]["To"] == "owner@example.test"
