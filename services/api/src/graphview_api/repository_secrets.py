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
from graphview_api.schemas import GraphSettingsUpdate


DEFAULT_PROJECT_ID = "project-default"
AI_PROVIDER_CREDENTIALS_KEY = "ai_provider_credentials"
AI_PROVIDER_IDS = {"openai", "anthropic", "gemini"}
AI_DEFAULT_PROVIDER_KEY = "ai_default_provider"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _dump_json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _load_json(value: str | None, fallback: object):
    return fallback if value is None else json.loads(value)


class SecretRepositoryMixin:
    def graph_settings(self) -> dict:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            return self._settings_from_row(row)

    def graph_settings_with_secrets(self) -> dict:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            return self._settings_from_row(row, redact=False)

    def update_graph_settings(self, payload: GraphSettingsUpdate) -> dict:
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return self.graph_settings()
        values["updated_at"] = _now()
        removed_secret_references: list[str] = []
        with self.engine.begin() as conn:
            if "settings" in values:
                settings_payload = values.pop("settings") or {}
                row = conn.execute(
                    select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                ).mappings().one()
                merged_settings = _load_json(json_value(row, "settings_json"), {})
                for key, value in settings_payload.items():
                    if key == "llm_api_key":
                        credentials = dict(merged_settings.get(AI_PROVIDER_CREDENTIALS_KEY) or {})
                        existing_credential = credentials.get("openai") if isinstance(credentials.get("openai"), dict) else {}
                        current_reference = existing_credential.get("encrypted_api_key")
                        if value:
                            credentials["openai"] = {
                                "encrypted_api_key": self._replace_encrypted_json(
                                    str(current_reference) if current_reference else None,
                                    {"api_key": str(value)},
                                ),
                                "updated_at": _now().isoformat(),
                            }
                        else:
                            credentials.pop("openai", None)
                            if current_reference:
                                removed_secret_references.append(str(current_reference))
                        merged_settings[AI_PROVIDER_CREDENTIALS_KEY] = credentials
                        merged_settings.pop("llm_api_key", None)
                        continue
                    if value is None:
                        merged_settings.pop(key, None)
                    else:
                        merged_settings[key] = value
                values["settings_json"] = _dump_json(merged_settings)
            conn.execute(
                update(db.graph_settings)
                .where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                .values(**values)
            )
        for reference in removed_secret_references:
            self._delete_encrypted_json(reference)
        return self.graph_settings()

    def ai_provider_api_keys(self) -> dict[str, str]:
        settings_doc = self.graph_settings_with_secrets()["settings"]
        credentials = settings_doc.get(AI_PROVIDER_CREDENTIALS_KEY)
        if not isinstance(credentials, dict):
            return {}
        api_keys: dict[str, str] = {}
        for provider_id, credential in credentials.items():
            if provider_id not in AI_PROVIDER_IDS or not isinstance(credential, dict):
                continue
            encrypted_api_key = credential.get("encrypted_api_key")
            if not encrypted_api_key:
                continue
            try:
                decrypted = self._decrypt_json(str(encrypted_api_key))
            except Exception:
                continue
            api_key = decrypted.get("api_key")
            if isinstance(api_key, str) and api_key:
                api_keys[provider_id] = api_key
        return api_keys

    def ai_default_provider(self) -> str | None:
        provider_id = self.graph_settings_with_secrets()["settings"].get(AI_DEFAULT_PROVIDER_KEY)
        if provider_id == "graphview-local" or provider_id in AI_PROVIDER_IDS:
            return str(provider_id)
        return None

    def upsert_ai_provider_api_key(self, provider_id: str, api_key: str, *, make_default: bool = True) -> dict:
        if provider_id not in AI_PROVIDER_IDS:
            raise ValueError(f"Provider {provider_id} does not accept user API keys")
        cleaned_key = api_key.strip()
        if not cleaned_key:
            raise ValueError("API key is required")
        timestamp = _now()
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            settings_doc = _load_json(json_value(row, "settings_json"), {})
            credentials = dict(settings_doc.get(AI_PROVIDER_CREDENTIALS_KEY) or {})
            existing_credential = credentials.get(provider_id) if isinstance(credentials.get(provider_id), dict) else {}
            current_reference = existing_credential.get("encrypted_api_key")
            credentials[provider_id] = {
                "encrypted_api_key": self._replace_encrypted_json(
                    str(current_reference) if current_reference else None,
                    {"api_key": cleaned_key},
                ),
                "updated_at": timestamp.isoformat(),
            }
            settings_doc[AI_PROVIDER_CREDENTIALS_KEY] = credentials
            if make_default:
                settings_doc[AI_DEFAULT_PROVIDER_KEY] = provider_id
            conn.execute(
                update(db.graph_settings)
                .where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                .values(settings_json=_dump_json(settings_doc), updated_at=timestamp)
            )
        return self.graph_settings()

    def delete_ai_provider_api_key(self, provider_id: str) -> dict:
        if provider_id not in AI_PROVIDER_IDS:
            raise ValueError(f"Provider {provider_id} does not accept user API keys")
        timestamp = _now()
        removed_reference: str | None = None
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.graph_settings.c.settings_json).where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
            ).mappings().one()
            settings_doc = _load_json(json_value(row, "settings_json"), {})
            credentials = dict(settings_doc.get(AI_PROVIDER_CREDENTIALS_KEY) or {})
            removed_credential = credentials.pop(provider_id, None)
            if isinstance(removed_credential, dict) and removed_credential.get("encrypted_api_key"):
                removed_reference = str(removed_credential["encrypted_api_key"])
            if credentials:
                settings_doc[AI_PROVIDER_CREDENTIALS_KEY] = credentials
            else:
                settings_doc.pop(AI_PROVIDER_CREDENTIALS_KEY, None)
            if settings_doc.get(AI_DEFAULT_PROVIDER_KEY) == provider_id:
                settings_doc[AI_DEFAULT_PROVIDER_KEY] = "graphview-local"
            conn.execute(
                update(db.graph_settings)
                .where(db.graph_settings.c.project_id == DEFAULT_PROJECT_ID)
                .values(settings_json=_dump_json(settings_doc), updated_at=timestamp)
            )
        self._delete_encrypted_json(removed_reference)
        return self.graph_settings()

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

    def _replace_encrypted_json(self, current: str | None, value: dict) -> str:
        if current and current.startswith("gvsecret:") and self.secret_store is not None:
            return self.secret_store.replace(current, value)
        return self._encrypt_json(value)

    def _delete_encrypted_json(self, value: str | None) -> None:
        if value and value.startswith("gvsecret:") and self.secret_store is not None:
            self.secret_store.delete(value)

    def _rotate_legacy_secrets(self, conn) -> None:
        for row in conn.execute(
            select(db.connector_accounts.c.id, db.connector_accounts.c.encrypted_token_json).where(
                db.connector_accounts.c.encrypted_token_json.is_not(None)
            )
        ).mappings():
            envelope = str(json_value(row, "encrypted_token_json"))
            if envelope.startswith("gvsecret:") or (
                self.secret_store is None and envelope.startswith("gvenc:aesgcm:v2:")
            ):
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
            if not envelope or str(envelope).startswith("gvsecret:") or (
                self.secret_store is None and str(envelope).startswith("gvenc:aesgcm:v2:")
            ):
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
