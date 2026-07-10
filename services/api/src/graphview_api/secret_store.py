from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any, Protocol

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from graphview_api.settings import Settings


class SecretStore(Protocol):
    def put(self, value: dict[str, Any]) -> str: ...

    def get(self, reference: str) -> dict[str, Any]: ...


class LocalAeadSecretStore:
    """Development-only opaque references backed by permission-restricted AES-GCM files."""

    reference_prefix = "gvsecret:local-aead:v1:"
    _secret_id = re.compile(r"^[A-Za-z0-9_-]{20,100}$")

    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.local_secret_store_path).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.key = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()

    def put(self, value: dict[str, Any]) -> str:
        secret_id = secrets.token_urlsafe(24)
        nonce = os.urandom(12)
        plaintext = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(self.key).encrypt(nonce, plaintext, b"graphview-local-secret-v1")
        envelope = base64.urlsafe_b64encode(nonce + ciphertext)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".graphview-secret-", dir=self.root)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(envelope)
                temporary.flush()
                os.fsync(temporary.fileno())
            destination = self.root / f"{secret_id}.aead"
            os.replace(temporary_name, destination)
            os.chmod(destination, 0o600)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
        return f"{self.reference_prefix}{secret_id}"

    def get(self, reference: str) -> dict[str, Any]:
        if not reference.startswith(self.reference_prefix):
            raise ValueError("Unsupported local secret reference")
        secret_id = reference.removeprefix(self.reference_prefix)
        if not self._secret_id.fullmatch(secret_id):
            raise ValueError("Invalid local secret reference")
        envelope = base64.urlsafe_b64decode((self.root / f"{secret_id}.aead").read_bytes())
        plaintext = AESGCM(self.key).decrypt(
            envelope[:12],
            envelope[12:],
            b"graphview-local-secret-v1",
        )
        value = json.loads(plaintext.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Local secret payload must be a JSON object")
        return value


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
        return LocalAeadSecretStore(settings)
    if settings.secret_provider == "vault":
        return VaultSecretStore(settings)
    raise ValueError(f"Unsupported secret provider: {settings.secret_provider}")
