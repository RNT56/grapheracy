from __future__ import annotations

import base64
import hashlib
import json

from graphview_api.json_compat import json_value
import os
from datetime import UTC, datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, update

from graphview_api import db


DEFAULT_PROJECT_ID = "project-default"
AI_PROVIDER_CREDENTIALS_KEY = "ai_provider_credentials"


class SecretRepositoryMixin:
    def _encrypt_json(self, value: dict) -> str:
        if self.secret_store is not None:
            return self.secret_store.put(value)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = hashlib.sha256(self.secret_key.encode("utf-8")).digest()
        nonce = os.urandom(12)
        encrypted = AESGCM(key).encrypt(nonce, raw, b"graphview-secret-json-v2")
        return f"gvenc:aesgcm:v2:{base64.urlsafe_b64encode(nonce + encrypted).decode('ascii')}"

    def _decrypt_json(self, value: str) -> dict:
        if value.startswith("gvsecret:"):
            if self.secret_store is None:
                raise ValueError("External secret store is not configured")
            return self.secret_store.get(value)
        key = hashlib.sha256(self.secret_key.encode("utf-8")).digest()
        if value.startswith("gvenc:aesgcm:v2:"):
            encrypted = base64.urlsafe_b64decode(value.removeprefix("gvenc:aesgcm:v2:").encode("ascii"))
            raw = AESGCM(key).decrypt(encrypted[:12], encrypted[12:], b"graphview-secret-json-v2")
            return json.loads(raw.decode("utf-8"))
        encrypted = base64.urlsafe_b64decode(value.encode("ascii"))
        raw = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(encrypted))
        return json.loads(raw.decode("utf-8"))

    def _rotate_legacy_secrets(self, conn) -> None:
        for row in conn.execute(
            select(db.connector_accounts.c.id, db.connector_accounts.c.encrypted_token_json).where(
                db.connector_accounts.c.encrypted_token_json.is_not(None)
            )
        ).mappings():
            envelope = str(json_value(row, "encrypted_token_json"))
            if envelope.startswith(("gvenc:aesgcm:v2:", "gvsecret:")):
                continue
            try:
                rotated = self._encrypt_json(self._decrypt_json(envelope))
            except Exception:
                continue
            conn.execute(update(db.connector_accounts).where(db.connector_accounts.c.id == row["id"]).values(encrypted_token_json=rotated))

        row = conn.execute(
            select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
        ).mappings().first()
        if row is None:
            return
        settings = json.loads(json_value(row, "settings_json"))
        changed = "llm_api_key" in settings
        plaintext_key = settings.pop("llm_api_key", None)
        credentials = dict(settings.get(AI_PROVIDER_CREDENTIALS_KEY) or {})
        if plaintext_key:
            credentials["openai"] = {
                "encrypted_api_key": self._encrypt_json({"api_key": str(plaintext_key)}),
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
        for credential in credentials.values():
            if not isinstance(credential, dict):
                continue
            envelope = credential.get("encrypted_api_key")
            if not envelope or str(envelope).startswith(("gvenc:aesgcm:v2:", "gvsecret:")):
                continue
            try:
                credential["encrypted_api_key"] = self._encrypt_json(self._decrypt_json(str(envelope)))
                changed = True
            except Exception:
                continue
        if credentials:
            settings[AI_PROVIDER_CREDENTIALS_KEY] = credentials
        if changed:
            conn.execute(
                update(db.graph_settings)
                .where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                .values(settings_json=json.dumps(settings, sort_keys=True, separators=(",", ":")), updated_at=datetime.now(tz=UTC))
            )
