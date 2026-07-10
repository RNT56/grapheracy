from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Protocol

import httpx

from graphview_api.settings import Settings


class SecretStore(Protocol):
    def put(self, value: dict[str, Any]) -> str: ...

    def get(self, reference: str) -> dict[str, Any]: ...


class VaultSecretStore:
    """Minimal Vault KV v2 adapter; database fields retain only opaque references."""

    reference_prefix = "gvsecret:vault:v1:"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.vault_address:
            raise ValueError("Vault address is required")
        token = settings.vault_token
        if not token and settings.vault_token_file:
            token = Path(settings.vault_token_file).read_text(encoding="utf-8").strip()
        if not token:
            raise ValueError("Vault token is required")
        headers = {"X-Vault-Token": token}
        if settings.vault_namespace:
            headers["X-Vault-Namespace"] = settings.vault_namespace
        self.client = client or httpx.Client(base_url=settings.vault_address.rstrip("/"), headers=headers, timeout=10)
        self.mount = settings.vault_mount.strip("/")

    def put(self, value: dict[str, Any]) -> str:
        secret_id = secrets.token_urlsafe(24)
        response = self.client.post(f"/v1/{self.mount}/data/graphview/{secret_id}", json={"data": value})
        response.raise_for_status()
        return f"{self.reference_prefix}{secret_id}"

    def get(self, reference: str) -> dict[str, Any]:
        if not reference.startswith(self.reference_prefix):
            raise ValueError("Unsupported Vault secret reference")
        secret_id = reference.removeprefix(self.reference_prefix)
        response = self.client.get(f"/v1/{self.mount}/data/graphview/{secret_id}")
        response.raise_for_status()
        document = response.json()
        return dict(document["data"]["data"])


def build_secret_store(settings: Settings) -> SecretStore | None:
    if settings.secret_provider == "local-aead":
        return None
    if settings.secret_provider == "vault":
        return VaultSecretStore(settings)
    raise ValueError(f"Unsupported secret provider: {settings.secret_provider}")
