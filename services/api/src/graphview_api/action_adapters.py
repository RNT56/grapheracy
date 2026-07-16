from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import ssl
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from string import Template
from typing import Any

import httpx
import jwt

from graphview_api.ingestion import validate_outbound_url
from graphview_api.settings import Settings


@dataclass(frozen=True)
class ActionAdapterResult:
    external_id: str
    metadata: dict[str, Any]


class ActionExecutor:
    def __init__(self, settings: Settings, *, secret_store=None, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.secret_store = secret_store
        self.http_client = http_client

    def _credential(self, payload: dict) -> dict:
        reference = payload.get("credential_ref")
        if not reference or self.secret_store is None:
            raise ValueError("External action requires a credential_ref backed by the configured secret store")
        return self.secret_store.get(str(reference))

    async def execute(self, proposal: dict, payload: dict) -> ActionAdapterResult:
        action_type = proposal["action_type"]
        if action_type == "create_external_ticket":
            return await self._github_issue(proposal, payload)
        if action_type == "create_notification":
            return await self._smtp_notification(proposal, payload)
        if action_type == "trigger_workflow":
            return await self._signed_webhook(proposal, payload)
        raise ValueError(f"No external adapter is registered for {action_type}")

    async def _github_issue(self, proposal: dict, payload: dict) -> ActionAdapterResult:
        credential = self._credential(payload)
        repository = str(payload.get("repository") or "")
        if repository.count("/") != 1:
            raise ValueError("GitHub issue action requires repository as owner/name")
        marker = f"<!-- graphview-action:{proposal['id']} -->"
        client = self.http_client or httpx.AsyncClient(timeout=20)
        close_client = self.http_client is None
        try:
            access_token = await self._github_access_token(client, credential)
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            for page in range(1, 101):
                existing = await client.get(
                    f"{self.settings.github_api_url.rstrip('/')}/repos/{repository}/issues",
                    params={"state": "all", "per_page": 100, "page": page},
                    headers=headers,
                )
                existing.raise_for_status()
                issues = existing.json()
                for issue in issues:
                    if marker in str(issue.get("body") or ""):
                        return ActionAdapterResult(
                            str(issue["id"]),
                            {"url": issue.get("html_url"), "reused": True},
                        )
                if len(issues) < 100:
                    break
            else:
                raise RuntimeError("GitHub issue idempotency scan exceeded 10,000 issues")
            body = f"{payload.get('body') or proposal['summary']}\n\n{marker}"
            created = await client.post(
                f"{self.settings.github_api_url.rstrip('/')}/repos/{repository}/issues",
                headers=headers,
                json={"title": payload.get("title") or proposal["title"], "body": body, "labels": payload.get("labels", [])},
            )
            created.raise_for_status()
            issue = created.json()
            return ActionAdapterResult(str(issue["id"]), {"url": issue.get("html_url"), "reused": False})
        finally:
            if close_client:
                await client.aclose()

    async def _github_access_token(self, client: httpx.AsyncClient, credential: dict) -> str:
        access_token = credential.get("token") or credential.get("access_token")
        expires_at = credential.get("expires_at")
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                expires_at = 0
        if access_token and (not expires_at or float(expires_at) > time.time() + 120):
            return str(access_token)
        app_id = str(credential.get("app_id") or "")
        installation_id = str(credential.get("installation_id") or "")
        private_key = str(credential.get("private_key") or "")
        if not app_id or not installation_id or not private_key:
            raise ValueError("GitHub Issue action requires a token or GitHub App credentials")
        now_seconds = int(time.time())
        app_jwt = jwt.encode(
            {"iat": now_seconds - 60, "exp": now_seconds + 540, "iss": app_id},
            private_key,
            algorithm="RS256",
        )
        response = await client.post(
            f"{self.settings.github_api_url.rstrip('/')}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        issued = response.json()
        if not issued.get("token"):
            raise RuntimeError("GitHub App installation token response was empty")
        return str(issued["token"])

    async def _smtp_notification(self, proposal: dict, payload: dict) -> ActionAdapterResult:
        if not self.settings.smtp_host or not self.settings.smtp_from_address:
            raise ValueError("SMTP adapter is not configured")
        credential = self._credential(payload)
        recipient = str(payload.get("to") or "").strip().lower()
        suppressed = {item.strip().lower() for item in self.settings.smtp_suppressed_recipients.split(",") if item.strip()}
        if not recipient or recipient in suppressed:
            raise ValueError("SMTP recipient is missing or suppressed")
        message_id = f"<graphview-{proposal['id']}@{self.settings.smtp_from_address.split('@')[-1]}>"
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_address
        message["To"] = recipient
        template = payload.get("template") if isinstance(payload.get("template"), dict) else {}
        variables = {
            str(key): str(value)
            for key, value in (payload.get("variables") or {}).items()
            if isinstance(value, (str, int, float, bool))
        }
        variables.setdefault("action_title", str(proposal["title"]))
        variables.setdefault("action_summary", str(proposal["summary"]))
        subject_template = str(template.get("subject") or payload.get("subject") or proposal["title"])
        body_template = str(template.get("body") or payload.get("body") or proposal["summary"])
        message["Subject"] = Template(subject_template).safe_substitute(variables)
        message["Message-ID"] = message_id
        message.set_content(Template(body_template).safe_substitute(variables))

        def send() -> None:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
                if self.settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if credential.get("username"):
                    smtp.login(str(credential["username"]), str(credential["password"]))
                smtp.send_message(message)

        await asyncio.to_thread(send)
        return ActionAdapterResult(message_id, {"recipient": recipient, "delivery": "accepted"})

    async def _signed_webhook(self, proposal: dict, payload: dict) -> ActionAdapterResult:
        credential = self._credential(payload)
        destination = str(payload.get("destination") or "")
        allowed_hosts = {host.strip().lower() for host in self.settings.action_webhook_allowed_hosts.split(",") if host.strip()}
        if not allowed_hosts:
            raise ValueError("Workflow webhook destination allowlist is empty")
        await validate_outbound_url(destination, allowed_hosts)
        timestamp = str(int(time.time()))
        event_id = f"action-{proposal['id']}"
        body = json.dumps(
            {"event_id": event_id, "schema_version": 1, "action": payload.get("event", {}), "proposal_id": proposal["id"]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(str(credential["secret"]).encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        client = self.http_client or httpx.AsyncClient(timeout=15)
        close_client = self.http_client is None
        try:
            response = await client.post(
                destination,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Graphview-Event-Id": event_id,
                    "X-Graphview-Timestamp": timestamp,
                    "X-Graphview-Signature": f"v1={signature}",
                },
            )
            response.raise_for_status()
            return ActionAdapterResult(event_id, {"status_code": response.status_code})
        finally:
            if close_client:
                await client.aclose()
