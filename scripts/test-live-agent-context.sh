#!/usr/bin/env bash
set -euo pipefail

project_name="${GRAPHVIEW_COMPOSE_PROJECT:-graphview-live-ci}"
base_url="${GRAPHVIEW_PUBLIC_URL:-http://127.0.0.1:8080}"
temporary_directory="$(mktemp -d -t graphview-context-proof.XXXXXX)"
outbox_path="$temporary_directory/outbox.jsonl"
trap 'rm -rf "$temporary_directory"' EXIT

: "${GRAPHVIEW_SERVICE_CLIENT_SECRET:?required}"
: "${POSTGRES_PASSWORD:?required}"

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

client_response="$(
  api_request POST /api/v1/agent-context/clients \
    "$(jq -nc '{display_name:"Production context acceptance",runtime_kind:"codex",scopes:["context:read","context:capture"],settings:{workspace_roots:["/workspace"]}}')"
)"
adapter_token="$(jq -er '.token | select(startswith("gvctx_"))' <<<"$client_response")"
jq -e '.client.scopes == ["context:capture"] and (.client | has("token_hash") | not)' <<<"$client_response" >/dev/null

gateway() {
  gateway_payload="${2-}"
  if [[ -z "$gateway_payload" ]]; then
    gateway_payload='{}'
  fi
  GRAPHVIEW_API_BASE_URL="$base_url" \
  GRAPHVIEW_AGENT_CONTEXT_TOKEN="$adapter_token" \
  GRAPHVIEW_AGENT_CONTEXT_OUTBOX="$outbox_path" \
  GRAPHVIEW_AGENT_CONTEXT_SESSION_ID="${session_id:-}" \
    node services/agent-gateway/src/index.mjs "$1" "$gateway_payload"
}

session_response="$(
  gateway start-session \
    "$(jq -nc '{title:"Production context acceptance",runtime_kind:"codex",authority:"gateway",workspace_root:"/workspace",repository_uri:"local://graphview",branch:"codex/graphview-1-0"}')"
)"
session_id="$(jq -er '.id | select(startswith("ctxsession_"))' <<<"$session_response")"

offline_prompt="$(
  GRAPHVIEW_API_BASE_URL=http://127.0.0.1:1 \
  GRAPHVIEW_AGENT_CONTEXT_TOKEN="$adapter_token" \
  GRAPHVIEW_AGENT_CONTEXT_OUTBOX="$outbox_path" \
  GRAPHVIEW_AGENT_CONTEXT_SESSION_ID="$session_id" \
    node services/agent-gateway/src/index.mjs report-prompt \
      "$(jq -nc '{sequence:1,title:"Offline prompt",text:"token=must-not-survive",summary:"Queued while offline."}')"
)"
jq -e '.queued == true' <<<"$offline_prompt" >/dev/null

offline_model="$(
  GRAPHVIEW_API_BASE_URL=http://127.0.0.1:1 \
  GRAPHVIEW_AGENT_CONTEXT_TOKEN="$adapter_token" \
  GRAPHVIEW_AGENT_CONTEXT_OUTBOX="$outbox_path" \
  GRAPHVIEW_AGENT_CONTEXT_SESSION_ID="$session_id" \
    node services/agent-gateway/src/index.mjs report-model-call \
      "$(jq -nc '{sequence:2,provider:"openai-compatible",model:"acceptance-model",response_text:"api_key=must-not-survive",summary:"Queued model response."}')"
)"
jq -e '.queued == true' <<<"$offline_model" >/dev/null
[[ "$(wc -l < "$outbox_path" | tr -d ' ')" == "2" ]]

flush_result="$(gateway flush-outbox '{}')"
jq -e '.flushed == 2' <<<"$flush_result" >/dev/null
[[ -s "$outbox_path.flushed" ]]

live_edit="$(
  gateway report-edit \
    "$(jq -nc '{sequence:3,path:"README.md",diff:"+GRAPHVIEW_CONTEXT_PROOF=complete",summary:"Captured live edit."}')"
)"
jq -e '.accepted_count == 1 and .duplicate_count == 0' <<<"$live_edit" >/dev/null

events_response="$(api_request GET "/api/v1/agent-context/sessions/$session_id/events?limit=25")"
jq -e '
  [.events[].sequence] == [1,2,3]
  and ([.events[].event_kind] == ["prompt_built","model_response","edit_applied"])
  and (tostring | contains("must-not-survive") | not)
  and all(.events[]; (.checksum | length) == 64)
' <<<"$events_response" >/dev/null

graph_response="$(api_request GET "/api/v1/agent-context/sessions/$session_id/graph")"
jq -e '.session.status == "running" and (.nodes | length) >= 4 and (.edges | length) >= 5' <<<"$graph_response" >/dev/null
artifact_id="$(jq -er '.artifacts[] | select(.kind == "prompt") | .id' <<<"$graph_response")"

content_response="$(api_request GET "/api/v1/agent-context/artifacts/$artifact_id/content")"
jq -e '.text | contains("[redacted]")' <<<"$content_response" >/dev/null
jq -e '.text | contains("must-not-survive") | not' <<<"$content_response" >/dev/null
blob_id="$(jq -er '.blob.id | select(startswith("ctxblob_"))' <<<"$content_response")"
[[ "$blob_id" =~ ^ctxblob_[A-Za-z0-9]+$ ]]

stream_payload="$(api_request GET "/api/v1/agent-context/sessions/$session_id/stream?limit=25")"
first_event_id="$(jq -er '.events[0].id' <<<"$events_response")"
second_event_id="$(jq -er '.events[1].id' <<<"$events_response")"
grep -Fq "id: $first_event_id" <<<"$stream_payload"
grep -Fq 'event: agent-context.event' <<<"$stream_payload"

replay_payload="$(
  curl -fsS "$base_url/api/v1/agent-context/sessions/$session_id/stream?limit=25" \
    -H "authorization: Bearer $service_token" \
    -H "Last-Event-ID: $first_event_id"
)"
if grep -Fq "id: $first_event_id" <<<"$replay_payload"; then
  echo "Agent context SSE replay repeated the acknowledged event." >&2
  exit 1
fi
grep -Fq "id: $second_event_id" <<<"$replay_payload"

missing_cursor_status="$(
  curl -sS -o "$temporary_directory/missing-cursor.json" -w '%{http_code}' \
    "$base_url/api/v1/agent-context/sessions/$session_id/stream" \
    -H "authorization: Bearer $service_token" \
    -H 'Last-Event-ID: ctxevent_missing'
)"
[[ "$missing_cursor_status" == "409" ]]

object_key="$(
  "${compose[@]}" exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    psql -U graphview -d graphview -At \
      --command "SELECT object_key FROM agent_context_blobs WHERE id = '$blob_id'"
)"
[[ "$object_key" == project-default/agent-context/*/*.gvenc ]]

"${compose[@]}" exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
  psql -U graphview -d graphview --set ON_ERROR_STOP=1 \
    --command "UPDATE agent_context_blobs SET expires_at=now() - interval '1 second' WHERE id = '$blob_id'" >/dev/null

retention_response="$(api_request POST /api/v1/agent-context/retention/run '{}')"
jq -e '.purged_blob_count >= 1 and .retained_blob_count >= 1' <<<"$retention_response" >/dev/null

retained_content="$(api_request GET "/api/v1/agent-context/artifacts/$artifact_id/content")"
jq -e '.text == null and .blob.encryption_status == "metadata_only" and .blob.redaction_status == "metadata_only"' \
  <<<"$retained_content" >/dev/null

"${compose[@]}" run --rm --no-deps --entrypoint /bin/sh -e "OBJECT_KEY=$object_key" ops -ec \
  'if mc stat "graphview/graphview/$OBJECT_KEY" >/dev/null 2>&1; then echo "purged context object still exists" >&2; exit 1; fi'

retained_row="$(
  "${compose[@]}" exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    psql -U graphview -d graphview -At \
      --command "SELECT (object_key IS NULL)::text || '|' || redaction_status || '|' || (COALESCE(metadata_json__jsonb, metadata_json::jsonb) ? 'retention_purged_at')::text FROM agent_context_blobs WHERE id = '$blob_id'"
)"
[[ "$retained_row" == "true|metadata_only|true" ]]

completed_response="$(gateway end-session "$(jq -nc --arg id "$session_id" '{session_id:$id}')")"
jq -e '.status == "completed"' <<<"$completed_response" >/dev/null

echo "Live agent-context proof passed: OIDC service auth, ordered offline replay, S3-encrypted capture, resumable SSE, redaction, and retention purge are production-proven."
