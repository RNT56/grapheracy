from __future__ import annotations

import json
from datetime import datetime

from graphview_api.json_compat import normalize_json_row
from graphview_api.schemas import SourceCreate, SourceUpdate


AI_PROVIDER_CREDENTIALS_KEY = "ai_provider_credentials"
ACTION_CREDENTIALS_KEY = "action_credentials"
SENSITIVE_SETTINGS_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "encrypted_api_key",
    "llm_api_key",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def _jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _dump_json(value) -> str:
    return json.dumps(_jsonable(value), sort_keys=True)


def _load_json(value: object | None, fallback):
    if value is None:
        return fallback
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


class RepositorySerializationMixin:
    """Redacted API projections and JSON/row conversion for the legacy repository adapter."""

    def _agent_context_client_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("token_hash", None)
        data["scopes"] = _load_json(data.pop("scopes_json"), [])
        data["settings"] = self._redact_payload(_load_json(data.pop("settings_json"), {}))
        return data

    def _agent_context_session_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = _load_json(data.pop("metadata_json"), {})
        return data

    def _agent_context_artifact_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = _load_json(data.pop("metadata_json"), {})
        return data

    def _agent_context_blob_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("encrypted_content", None)
        data.pop("object_key", None)
        data["metadata"] = _load_json(data.pop("metadata_json"), {})
        return data

    def _agent_context_event_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["payload"] = _load_json(data.pop("payload_json"), {})
        data["object_refs"] = _load_json(data.pop("object_refs_json"), [])
        return data

    def _activity_event_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["object_refs"] = _load_json(data.pop("object_refs_json"), [])
        data["payload"] = _load_json(data.pop("payload_json"), {})
        data["lenses"] = _load_json(data.pop("lenses_json"), [])
        return data

    def _settings_from_row(self, row, *, redact: bool = True) -> dict:
        data = normalize_json_row(row)
        settings = _load_json(data.pop("settings_json"), {})
        data["settings"] = self._redact_settings(settings) if redact else settings
        return data

    def _redact_settings(self, value):
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                key_lower = key.lower()
                if key == AI_PROVIDER_CREDENTIALS_KEY and isinstance(item, dict):
                    redacted[key] = {
                        provider_id: {
                            "configured": isinstance(credential, dict)
                            and bool(credential.get("encrypted_api_key")),
                            "updated_at": credential.get("updated_at")
                            if isinstance(credential, dict)
                            else None,
                        }
                        for provider_id, credential in item.items()
                    }
                elif key == ACTION_CREDENTIALS_KEY and isinstance(item, dict):
                    redacted[key] = {
                        credential_id: {
                            "configured": isinstance(credential, dict)
                            and bool(credential.get("encrypted_secret")),
                            "updated_at": credential.get("updated_at")
                            if isinstance(credential, dict)
                            else None,
                        }
                        for credential_id, credential in item.items()
                    }
                elif key_lower in SENSITIVE_SETTINGS_KEYS:
                    continue
                else:
                    redacted[key] = self._redact_settings(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_settings(item) for item in value]
        return value

    def _connector_account_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data.pop("encrypted_token_json", None)
        data["scopes"] = _load_json(data.pop("scopes_json"), [])
        data["settings"] = self._redact_settings(_load_json(data.pop("settings_json"), {}))
        return data

    def _connector_target_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["sync_settings"] = _load_json(data.pop("sync_settings_json"), {})
        return data

    def _connector_sync_run_from_row(self, row) -> dict:
        return normalize_json_row(row)

    def _source_chunk_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["heading_path"] = _load_json(data.pop("heading_path_json"), [])
        data["links"] = _load_json(data.pop("links_json"), [])
        data["mentions"] = _load_json(data.pop("mentions_json"), [])
        return data

    def _topic_from_row(self, row) -> dict:
        return normalize_json_row(row)

    def _proposal_status(self, decision: str) -> str:
        return {
            "accept": "accepted",
            "reject": "rejected",
            "edit": "edited",
            "defer": "deferred",
        }[decision]

    def _proposal_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["proposed_value"] = _load_json(data.pop("proposed_value_json"), {})
        data["provenance"] = _load_json(data.pop("provenance_json"), [])
        return data

    def _decision_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["edited_value"] = _load_json(data.pop("edited_value_json"), None)
        return data

    def _embedding_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["vector"] = _load_json(data.pop("vector_json"), [])
        return data

    def _source_values_from_payload(
        self,
        payload: SourceCreate | SourceUpdate,
        *,
        exclude_unset: bool = False,
    ) -> dict:
        values = payload.model_dump(exclude_unset=exclude_unset)
        if "metadata" in values:
            values["metadata_json"] = _dump_json(values.pop("metadata") or {})
        return values

    def _source_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = _load_json(data.pop("metadata_json", None), {})
        return data

    def _node_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["topic_ids"] = _load_json(data.pop("topic_ids_json"), [])
        data["metadata"] = _load_json(data.pop("metadata_json", None), {})
        data["provenance"] = _load_json(data.pop("provenance_json"), [])
        return data

    def _edge_from_row(self, row) -> dict:
        data = normalize_json_row(row)
        data["metadata"] = _load_json(data.pop("metadata_json", None), {})
        data["provenance"] = _load_json(data.pop("provenance_json"), [])
        return data
