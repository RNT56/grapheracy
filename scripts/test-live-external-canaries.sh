#!/usr/bin/env bash
set -euo pipefail

base_url="${GRAPHVIEW_PUBLIC_URL:-http://127.0.0.1:8080}"
temporary_directory="$(mktemp -d -t graphview-external-canaries.XXXXXX)"
receipt_path="${GRAPHVIEW_CANARY_RECEIPT_PATH:-artifacts/external-canary-receipt.json}"
run_id="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"

required_variables=(
  GRAPHVIEW_SERVICE_CLIENT_SECRET
  GRAPHVIEW_CANARY_GITHUB_TOKEN
  GRAPHVIEW_CANARY_GITHUB_REPOSITORY
  GRAPHVIEW_CANARY_GOOGLE_CLIENT_ID
  GRAPHVIEW_CANARY_GOOGLE_CLIENT_SECRET
  GRAPHVIEW_CANARY_GOOGLE_REFRESH_TOKEN
  GRAPHVIEW_CANARY_GOOGLE_FOLDER_ID
  GRAPHVIEW_CANARY_NOTION_TOKEN
  GRAPHVIEW_CANARY_NOTION_TARGET_ID
  GRAPHVIEW_CANARY_OPENAI_API_KEY
  GRAPHVIEW_CANARY_OPENAI_MODEL
  GRAPHVIEW_CANARY_SMTP_RECIPIENT
  GRAPHVIEW_CANARY_WEBHOOK_URL
  GRAPHVIEW_CANARY_WEBHOOK_SECRET
)
for variable in "${required_variables[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    echo "$variable is required for the protected external canary." >&2
    exit 1
  fi
done

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

cleanup() {
  api_request DELETE /api/v1/action-credentials/github >/dev/null 2>&1 || true
  api_request DELETE /api/v1/action-credentials/smtp >/dev/null 2>&1 || true
  api_request DELETE /api/v1/action-credentials/webhook >/dev/null 2>&1 || true
  api_request DELETE /api/v1/providers/openai/credentials >/dev/null 2>&1 || true
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

wait_for_job() {
  job_id="$1"
  for _ in $(seq 1 180); do
    job="$(api_request GET "/api/v1/jobs/$job_id")"
    status_value="$(jq -er .status <<<"$job")"
    case "$status_value" in
      succeeded)
        printf '%s' "$job"
        return 0
        ;;
      failed|cancelled)
        jq -c '{id,status,error_code,attempt,max_attempts}' <<<"$job" >&2
        return 1
        ;;
    esac
    sleep 1
  done
  echo "Timed out waiting for durable job $job_id." >&2
  return 1
}

create_connector() {
  kind="$1"
  target_type="$2"
  remote_id="$3"
  title="$4"
  token_json="$5"
  sync_settings="$6"
  account="$(
    api_request POST /api/v1/connector-accounts \
      "$(jq -nc --arg kind "$kind" --arg title "$title" --argjson token "$token_json" \
        '{kind:$kind,display_name:$title,token_json:$token,scopes:[],settings:{canary:true}}')"
  )"
  account_id="$(jq -er .id <<<"$account")"
  target="$(
    api_request POST /api/v1/connector-targets \
      "$(jq -nc --arg account "$account_id" --arg type "$target_type" --arg remote "$remote_id" \
        --arg title "$title" --argjson settings "$sync_settings" \
        '{account_id:$account,target_type:$type,remote_id:$remote,title:$title,sync_settings:$settings}')"
  )"
  jq -er .id <<<"$target"
}

sync_connector() {
  target_id="$1"
  job_id="$(api_request POST "/api/v1/connectors/$target_id/sync" '{}' | jq -er .id)"
  wait_for_job "$job_id" >/dev/null
  health="$(api_request GET "/api/v1/connectors/$target_id/health")"
  jq -e '.status == "healthy" and .last_success_at != null and .actionable_failure == null' <<<"$health" >/dev/null
  printf '%s' "$health"
}

create_action() {
  action_type="$1"
  title="$2"
  summary="$3"
  payload="$4"
  proposal="$(
    api_request POST /api/v1/action-proposals \
      "$(jq -nc --arg type "$action_type" --arg title "$title" --arg summary "$summary" --argjson payload "$payload" \
        '{action_type:$type,title:$title,summary:$summary,payload:$payload,approval_required:true}')"
  )"
  proposal_id="$(jq -er .id <<<"$proposal")"
  api_request POST "/api/v1/action-proposals/$proposal_id/approve" \
    "$(jq -nc '{rationale:"Approved by protected Graphview 1.0 external canary."}')" >/dev/null
  job_id="$(api_request POST "/api/v1/action-proposals/$proposal_id/run" '{}' | jq -er .id)"
  job="$(wait_for_job "$job_id")"
  action_run_id="$(jq -er '.result.id' <<<"$job")"
  jq -e '.result.status == "succeeded" and (.result.external_id | length) > 0' <<<"$job" >/dev/null
  jq -nc --arg proposal_id "$proposal_id" --arg job_id "$job_id" --arg action_run_id "$action_run_id" \
    --arg external_id "$(jq -er '.result.external_id' <<<"$job")" \
    '{proposal_id:$proposal_id,job_id:$job_id,action_run_id:$action_run_id,external_id:$external_id}'
}

record_confirmed_outcome() {
  action_run_id="$1"
  title="$2"
  outcome="$(
    api_request POST "/api/v1/action-runs/$action_run_id/outcome" \
      "$(jq -nc --arg title "$title" '{status:"succeeded",title:$title,summary:"External canary receipt was verified.",result:{canary:true}}')"
  )"
  outcome_id="$(jq -er .id <<<"$outcome")"
  feedback="$(
    api_request POST /api/v1/feedback-events \
      "$(jq -nc --arg outcome "$outcome_id" --arg run "$action_run_id" \
        '{outcome_id:$outcome,action_run_id:$run,kind:"graph_memory_proposal",summary:"External canary succeeded.",effect:{verified:true},proposed_value:{kind:"canary_receipt"}}')"
  )"
  jq -e '.proposed_value.kind == "canary_receipt"' <<<"$feedback" >/dev/null
  printf '%s' "$outcome"
}

github_token_json="$(jq -nc --arg token "$GRAPHVIEW_CANARY_GITHUB_TOKEN" '{access_token:$token}')"
github_settings="$(jq -nc --arg repository "$GRAPHVIEW_CANARY_GITHUB_REPOSITORY" \
  '{provider:"github",repository:$repository,allowed_suffixes:[".md"],max_files:25,include_issues:true,schedule_enabled:false}')"
github_target_id="$(create_connector repository repository "$GRAPHVIEW_CANARY_GITHUB_REPOSITORY" \
  "Graphview GitHub canary $run_id" "$github_token_json" "$github_settings")"
github_initial_health="$(sync_connector "$github_target_id")"
jq -e '.imported_count > 0 and (.cursor.cursor | startswith("github:"))' <<<"$github_initial_health" >/dev/null

google_token_json="$(jq -nc --arg refresh "$GRAPHVIEW_CANARY_GOOGLE_REFRESH_TOKEN" \
  --arg client "$GRAPHVIEW_CANARY_GOOGLE_CLIENT_ID" --arg secret "$GRAPHVIEW_CANARY_GOOGLE_CLIENT_SECRET" \
  '{refresh_token:$refresh,client_id:$client,client_secret:$secret}')"
google_settings='{"schedule_enabled":false}'
google_target_id="$(create_connector google-workspace folder "$GRAPHVIEW_CANARY_GOOGLE_FOLDER_ID" \
  "Graphview Google canary $run_id" "$google_token_json" "$google_settings")"
google_initial_health="$(sync_connector "$google_target_id")"
jq -e '.imported_count > 0 and (.cursor.cursor | startswith("google:"))' <<<"$google_initial_health" >/dev/null

notion_token_json="$(jq -nc --arg token "$GRAPHVIEW_CANARY_NOTION_TOKEN" '{access_token:$token,notion_version:"2026-03-11"}')"
notion_target_type="${GRAPHVIEW_CANARY_NOTION_TARGET_TYPE:-page}"
notion_settings='{"schedule_enabled":false,"notion_version":"2026-03-11"}'
notion_target_id="$(create_connector notion "$notion_target_type" "$GRAPHVIEW_CANARY_NOTION_TARGET_ID" \
  "Graphview Notion canary $run_id" "$notion_token_json" "$notion_settings")"
notion_initial_health="$(sync_connector "$notion_target_id")"
jq -e '.imported_count > 0 and (.cursor.cursor | startswith("notion:"))' <<<"$notion_initial_health" >/dev/null

api_request PATCH /api/v1/providers/openai/credentials \
  "$(jq -nc --arg key "$GRAPHVIEW_CANARY_OPENAI_API_KEY" '{api_key:$key,make_default:true}')" >/dev/null
ai_job_id="$(
  api_request POST /api/v1/ai/query \
    "$(jq -nc --arg model "$GRAPHVIEW_CANARY_OPENAI_MODEL" \
      '{question:"Which imported canary sources are present? Cite the source evidence.",graph_id:"project-default",lens:"all",provider:"openai",model:$model}')" \
  | jq -er .id
)"
ai_job="$(wait_for_job "$ai_job_id")"
jq -e '.result.citations | length > 0' <<<"$ai_job" >/dev/null
jq -e '.result.agent_run.provider == "openai" and .result.agent_run.status == "completed"' <<<"$ai_job" >/dev/null

api_request PUT /api/v1/action-credentials/github \
  "$(jq -nc --arg token "$GRAPHVIEW_CANARY_GITHUB_TOKEN" '{credentials:{token:$token}}')" >/dev/null
smtp_credentials="$(jq -nc --arg username "${GRAPHVIEW_CANARY_SMTP_USERNAME:-}" --arg password "${GRAPHVIEW_CANARY_SMTP_PASSWORD:-}" \
  'if ($username | length) > 0 then {username:$username,password:$password} else {} end')"
api_request PUT /api/v1/action-credentials/smtp "$(jq -nc --argjson credentials "$smtp_credentials" '{credentials:$credentials}')" >/dev/null
api_request PUT /api/v1/action-credentials/webhook \
  "$(jq -nc --arg secret "$GRAPHVIEW_CANARY_WEBHOOK_SECRET" '{credentials:{secret:$secret,callback_secret:$secret}}')" >/dev/null

github_action="$(create_action create_external_ticket "Graphview 1.0 canary $run_id" \
  "Close after verifying the GitHub Issue adapter receipt and idempotency marker." \
  "$(jq -nc --arg repository "$GRAPHVIEW_CANARY_GITHUB_REPOSITORY" --arg run "$run_id" \
    '{credential_id:"github",repository:$repository,title:("Graphview 1.0 canary " + $run),body:"Protected external action acceptance.",labels:[]}')")"
github_marker="<!-- graphview-action:$(jq -er .proposal_id <<<"$github_action") -->"
github_issue="$(
  curl -fsS "https://api.github.com/repos/$GRAPHVIEW_CANARY_GITHUB_REPOSITORY/issues?state=all&per_page=100" \
    -H "authorization: Bearer $GRAPHVIEW_CANARY_GITHUB_TOKEN" \
    -H 'accept: application/vnd.github+json' \
  | jq -ec --arg marker "$github_marker" '[.[] | select((.body // "") | contains($marker))] | first'
)"
github_issue_number="$(jq -er .number <<<"$github_issue")"
curl -fsS -X PATCH "https://api.github.com/repos/$GRAPHVIEW_CANARY_GITHUB_REPOSITORY/issues/$github_issue_number" \
  -H "authorization: Bearer $GRAPHVIEW_CANARY_GITHUB_TOKEN" \
  -H 'accept: application/vnd.github+json' -H 'content-type: application/json' --data '{"state":"closed"}' >/dev/null
github_outcome="$(record_confirmed_outcome "$(jq -er .action_run_id <<<"$github_action")" "GitHub canary receipt verified")"
github_delta_health="$(sync_connector "$github_target_id")"
jq -e '.status == "healthy" and (.cursor.cursor | startswith("github:"))' <<<"$github_delta_health" >/dev/null

smtp_action="$(create_action create_notification "Graphview 1.0 SMTP canary $run_id" \
  "Verify SMTP acceptance through the configured protected relay." \
  "$(jq -nc --arg recipient "$GRAPHVIEW_CANARY_SMTP_RECIPIENT" --arg run "$run_id" \
    '{credential_id:"smtp",to:$recipient,subject:("Graphview 1.0 SMTP canary " + $run),body:"Protected SMTP adapter acceptance."}')")"
smtp_outcome="$(record_confirmed_outcome "$(jq -er .action_run_id <<<"$smtp_action")" "SMTP canary accepted")"

webhook_action="$(create_action trigger_workflow "Graphview 1.0 webhook canary $run_id" \
  "Verify allowlisted HMAC delivery and signed outcome callback." \
  "$(jq -nc --arg destination "$GRAPHVIEW_CANARY_WEBHOOK_URL" --arg run "$run_id" \
    '{credential_id:"webhook",destination:$destination,event:{kind:"graphview.release.canary",run_id:$run}}')")"
webhook_run_id="$(jq -er .action_run_id <<<"$webhook_action")"
callback_body="$(jq -nc '{status:"succeeded",title:"Webhook canary callback",summary:"Protected receiver accepted the signed workflow.",result:{verified:true}}')"
callback_timestamp="$(date +%s)"
callback_signature="v1=$(printf '%s.%s' "$callback_timestamp" "$callback_body" | openssl dgst -sha256 -hmac "$GRAPHVIEW_CANARY_WEBHOOK_SECRET" | awk '{print $NF}')"
callback_job_id="$(
  curl -fsS -X POST "$base_url/api/v1/action-runs/$webhook_run_id/callback" \
    -H 'content-type: application/json' \
    -H "X-Graphview-Event-Id: canary-callback-$run_id" \
    -H "X-Graphview-Timestamp: $callback_timestamp" \
    -H "X-Graphview-Signature: $callback_signature" \
    --data "$callback_body" | jq -er .id
)"
callback_job="$(wait_for_job "$callback_job_id")"
webhook_outcome_id="$(jq -er '.result.id' <<<"$callback_job")"
api_request POST /api/v1/feedback-events \
  "$(jq -nc --arg outcome "$webhook_outcome_id" --arg run "$webhook_run_id" \
    '{outcome_id:$outcome,action_run_id:$run,kind:"graph_memory_proposal",summary:"Signed workflow and callback canary succeeded.",effect:{verified:true},proposed_value:{kind:"canary_receipt"}}')" >/dev/null

google_delta_health="$(sync_connector "$google_target_id")"
notion_delta_health="$(sync_connector "$notion_target_id")"
jq -e '.status == "healthy" and (.cursor.cursor | startswith("google:"))' <<<"$google_delta_health" >/dev/null
jq -e '.status == "healthy" and (.cursor.cursor | startswith("notion:"))' <<<"$notion_delta_health" >/dev/null

mkdir -p "$(dirname "$receipt_path")"
jq -n \
  --arg run_id "$run_id" \
  --arg github_target_id "$github_target_id" \
  --arg google_target_id "$google_target_id" \
  --arg notion_target_id "$notion_target_id" \
  --arg ai_job_id "$ai_job_id" \
  --arg github_action_run_id "$(jq -er .action_run_id <<<"$github_action")" \
  --arg smtp_action_run_id "$(jq -er .action_run_id <<<"$smtp_action")" \
  --arg webhook_action_run_id "$webhook_run_id" \
  --arg github_outcome_id "$(jq -er .id <<<"$github_outcome")" \
  --arg smtp_outcome_id "$(jq -er .id <<<"$smtp_outcome")" \
  --arg webhook_outcome_id "$webhook_outcome_id" \
  '{schema_version:1,run_id:$run_id,connectors:{github:$github_target_id,google:$google_target_id,notion:$notion_target_id},ai_job_id:$ai_job_id,actions:{github:$github_action_run_id,smtp:$smtp_action_run_id,webhook:$webhook_action_run_id},outcomes:{github:$github_outcome_id,smtp:$smtp_outcome_id,webhook:$webhook_outcome_id},status:"passed"}' \
  > "$receipt_path"

echo "Protected external canaries passed: GitHub/Google/Notion sync and cursor replay, cited OpenAI query, GitHub Issue, SMTP, signed webhook callback, outcomes, and feedback."
