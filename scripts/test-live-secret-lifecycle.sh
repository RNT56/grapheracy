#!/usr/bin/env bash
set -euo pipefail

project_name="${GRAPHVIEW_COMPOSE_PROJECT:-graphview-live-ci}"
base_url="${GRAPHVIEW_PUBLIC_URL:-http://127.0.0.1:8080}"

: "${GRAPHVIEW_SERVICE_CLIENT_SECRET:?required}"
: "${GRAPHVIEW_SECRET_KEY:?required}"
: "${POSTGRES_PASSWORD:?required}"
: "${VAULT_DEV_ROOT_TOKEN:?required}"

compose=(docker compose -p "$project_name" -f infra/compose/docker-compose.production.yml)

service_token="$(
  curl -fsS -X POST "$base_url/identity/realms/graphview/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    --data-urlencode grant_type=client_credentials \
    --data-urlencode client_id=graphview-service \
    --data-urlencode client_secret="$GRAPHVIEW_SERVICE_CLIENT_SECRET" \
  | jq -er .access_token
)"

api_request() {
  method="$1"
  path="$2"
  payload="${3:-}"
  if [[ -n "$payload" ]]; then
    curl -fsS -X "$method" "$base_url$path" \
      -H "authorization: Bearer $service_token" \
      -H 'content-type: application/json' \
      --data "$payload"
  else
    curl -fsS -X "$method" "$base_url$path" -H "authorization: Bearer $service_token"
  fi
}

psql_value() {
  "${compose[@]}" exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    psql -U graphview -d graphview -At --set ON_ERROR_STOP=1 --command "$1"
}

vault_document() {
  secret_id="$1"
  "${compose[@]}" exec -T \
    -e VAULT_ADDR=http://127.0.0.1:8200 \
    -e VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN" \
    vault vault kv get -format=json "secret/graphview/$secret_id"
}

vault_reference_id() {
  reference="$1"
  [[ "$reference" =~ ^gvsecret:vault:v1:([A-Za-z0-9_-]{20,100})$ ]]
  printf '%s' "${BASH_REMATCH[1]}"
}

connector_response="$(
  api_request POST /api/v1/connector-accounts \
    "$(jq -nc '{kind:"notion",display_name:"Vault rotation acceptance",token_json:{access_token:"initial-connector-secret"}}')"
)"
connector_id="$(jq -er '.id | select(startswith("connacct_"))' <<<"$connector_response")"
[[ "$connector_id" =~ ^connacct_[A-Za-z0-9]+$ ]]
connector_reference="$(psql_value "SELECT encrypted_token_json FROM connector_accounts WHERE id = '$connector_id'")"
connector_secret_id="$(vault_reference_id "$connector_reference")"
connector_v1="$(vault_document "$connector_secret_id")"
jq -e '.data.data.access_token == "initial-connector-secret" and .data.metadata.version == 1' <<<"$connector_v1" >/dev/null

rotated_connector="$(
  api_request PATCH "/api/v1/connector-accounts/$connector_id/credentials" \
    "$(jq -nc '{token_json:{access_token:"rotated-connector-secret",refresh_token:"rotated-refresh-secret"}}')"
)"
jq -e '.status == "connected" and (tostring | contains("rotated-connector-secret") | not)' <<<"$rotated_connector" >/dev/null
rotated_connector_reference="$(psql_value "SELECT encrypted_token_json FROM connector_accounts WHERE id = '$connector_id'")"
[[ "$rotated_connector_reference" == "$connector_reference" ]]
connector_v2="$(vault_document "$connector_secret_id")"
jq -e '
  .data.data.access_token == "rotated-connector-secret"
  and .data.data.refresh_token == "rotated-refresh-secret"
  and .data.metadata.version == 2
' <<<"$connector_v2" >/dev/null

api_request PATCH /api/v1/providers/openai/credentials \
  "$(jq -nc '{api_key:"initial-provider-secret",make_default:true}')" >/dev/null
provider_reference="$(
  psql_value "SELECT COALESCE(settings_json__jsonb, settings_json::jsonb) #>> '{ai_provider_credentials,openai,encrypted_api_key}' FROM graph_settings WHERE project_id = 'project-default'"
)"
provider_secret_id="$(vault_reference_id "$provider_reference")"
provider_v1="$(vault_document "$provider_secret_id")"
jq -e '.data.data.api_key == "initial-provider-secret" and .data.metadata.version == 1' <<<"$provider_v1" >/dev/null

api_request PATCH /api/v1/providers/openai/credentials \
  "$(jq -nc '{api_key:"rotated-provider-secret",make_default:true}')" >/dev/null
rotated_provider_reference="$(
  psql_value "SELECT COALESCE(settings_json__jsonb, settings_json::jsonb) #>> '{ai_provider_credentials,openai,encrypted_api_key}' FROM graph_settings WHERE project_id = 'project-default'"
)"
[[ "$rotated_provider_reference" == "$provider_reference" ]]
provider_v2="$(vault_document "$provider_secret_id")"
jq -e '.data.data.api_key == "rotated-provider-secret" and .data.metadata.version == 2' <<<"$provider_v2" >/dev/null

action_credential="$(
  api_request PUT /api/v1/action-credentials/webhook \
    "$(jq -nc '{credentials:{secret:"initial-action-secret",callback_secret:"initial-callback-secret"}}')"
)"
jq -e '.id == "webhook" and .configured == true and (tostring | contains("initial-action-secret") | not)' \
  <<<"$action_credential" >/dev/null
action_reference="$(
  psql_value "SELECT COALESCE(settings_json__jsonb, settings_json::jsonb) #>> '{action_credentials,webhook,encrypted_secret}' FROM graph_settings WHERE project_id = 'project-default'"
)"
action_secret_id="$(vault_reference_id "$action_reference")"
action_v1="$(vault_document "$action_secret_id")"
jq -e '
  .data.data.secret == "initial-action-secret"
  and .data.data.callback_secret == "initial-callback-secret"
  and .data.metadata.version == 1
' <<<"$action_v1" >/dev/null

api_request PUT /api/v1/action-credentials/webhook \
  "$(jq -nc '{credentials:{secret:"rotated-action-secret",callback_secret:"rotated-callback-secret"}}')" >/dev/null
rotated_action_reference="$(
  psql_value "SELECT COALESCE(settings_json__jsonb, settings_json::jsonb) #>> '{action_credentials,webhook,encrypted_secret}' FROM graph_settings WHERE project_id = 'project-default'"
)"
[[ "$rotated_action_reference" == "$action_reference" ]]
action_v2="$(vault_document "$action_secret_id")"
jq -e '
  .data.data.secret == "rotated-action-secret"
  and .data.data.callback_secret == "rotated-callback-secret"
  and .data.metadata.version == 2
' <<<"$action_v2" >/dev/null
action_settings="$(api_request GET /api/v1/graph/settings)"
jq -e '.settings.action_credentials.webhook.configured == true' <<<"$action_settings" >/dev/null
if grep -Eq 'rotated-action-secret|rotated-callback-secret|gvsecret:' <<<"$action_settings"; then
  echo "Action credential material leaked through graph settings." >&2
  exit 1
fi

migration_account="$(
  api_request POST /api/v1/connector-accounts \
    "$(jq -nc '{kind:"repository",display_name:"Legacy credential migration acceptance"}')"
)"
migration_account_id="$(jq -er '.id | select(startswith("connacct_"))' <<<"$migration_account")"
[[ "$migration_account_id" =~ ^connacct_[A-Za-z0-9]+$ ]]
legacy_envelope="$(
  GRAPHVIEW_SECRET_KEY="$GRAPHVIEW_SECRET_KEY" uv run --package graphview-api python - <<'PY'
import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

key = hashlib.sha256(os.environ["GRAPHVIEW_SECRET_KEY"].encode()).digest()
nonce = os.urandom(12)
raw = json.dumps({"access_token": "legacy-database-secret"}, sort_keys=True, separators=(",", ":")).encode()
encrypted = AESGCM(key).encrypt(nonce, raw, b"graphview-secret-json-v2")
print("gvenc:aesgcm:v2:" + base64.urlsafe_b64encode(nonce + encrypted).decode())
PY
)"
[[ "$legacy_envelope" =~ ^gvenc:aesgcm:v2:[A-Za-z0-9_=-]+$ ]]
psql_value "UPDATE connector_accounts SET encrypted_token_json = '$legacy_envelope' WHERE id = '$migration_account_id'" >/dev/null

"${compose[@]}" restart api >/dev/null
ready=0
for _ in $(seq 1 60); do
  if curl -fsS "$base_url/ready" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "API did not recover after the credential migration restart." >&2
  exit 1
fi

migrated_reference="$(psql_value "SELECT encrypted_token_json FROM connector_accounts WHERE id = '$migration_account_id'")"
migrated_secret_id="$(vault_reference_id "$migrated_reference")"
migrated_document="$(vault_document "$migrated_secret_id")"
jq -e '.data.data.access_token == "legacy-database-secret" and .data.metadata.version == 1' <<<"$migrated_document" >/dev/null

api_request DELETE "/api/v1/connector-accounts/$connector_id/credentials" >/dev/null
api_request DELETE "/api/v1/connector-accounts/$migration_account_id/credentials" >/dev/null
api_request DELETE /api/v1/providers/openai/credentials >/dev/null
api_request DELETE /api/v1/action-credentials/webhook >/dev/null

for deleted_secret_id in "$connector_secret_id" "$migrated_secret_id" "$provider_secret_id" "$action_secret_id"; do
  if "${compose[@]}" exec -T \
    -e VAULT_ADDR=http://127.0.0.1:8200 \
    -e VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN" \
    vault vault kv metadata get "secret/graphview/$deleted_secret_id" >/dev/null 2>&1; then
    echo "Deleted credential remains in Vault metadata: $deleted_secret_id" >&2
    exit 1
  fi
done

cleared_connector="$(psql_value "SELECT (encrypted_token_json IS NULL)::text || '|' || status FROM connector_accounts WHERE id = '$connector_id'")"
cleared_migration="$(psql_value "SELECT (encrypted_token_json IS NULL)::text || '|' || status FROM connector_accounts WHERE id = '$migration_account_id'")"
[[ "$cleared_connector" == "true|error" ]]
[[ "$cleared_migration" == "true|error" ]]
[[ -z "$(psql_value "SELECT COALESCE(settings_json__jsonb, settings_json::jsonb) #>> '{action_credentials,webhook}' FROM graph_settings WHERE project_id = 'project-default'")" ]]

echo "Live secret lifecycle proof passed: connector, provider, and action Vault references rotated in place, legacy database credentials migrated, and deleted credentials were purged."
