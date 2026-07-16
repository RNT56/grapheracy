#!/usr/bin/env bash
set -euo pipefail

project_name="${GRAPHVIEW_COMPOSE_PROJECT:-graphview-live-ci}"
base_url="${GRAPHVIEW_PUBLIC_URL:-http://127.0.0.1:8080}"
temporary_directory="$(mktemp -d -t graphview-failure-proof.XXXXXX)"
run_id="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"

: "${GRAPHVIEW_SERVICE_CLIENT_SECRET:?required}"
: "${POSTGRES_PASSWORD:?required}"

service_id() {
  docker ps -aq \
    --filter "label=com.docker.compose.project=$project_name" \
    --filter "label=com.docker.compose.service=$1" \
  | head -n 1
}

redis_id="$(service_id redis)"
minio_id="$(service_id minio)"
worker_id="$(service_id worker)"
postgres_id="$(service_id postgres)"
for service in redis minio worker postgres; do
  id_variable="${service}_id"
  if [[ -z "${!id_variable}" ]]; then
    echo "The Graphview $service service is not present for project $project_name." >&2
    exit 1
  fi
done

cleanup() {
  docker start "$redis_id" "$minio_id" "$worker_id" >/dev/null 2>&1 || true
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

wait_for_health() {
  container_id="$1"
  expected="${2:-healthy}"
  for _ in $(seq 1 90); do
    state="$(docker inspect "$container_id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')"
    [[ "$state" == "$expected" ]] && return 0
    sleep 1
  done
  docker logs --tail=120 "$container_id" >&2 || true
  return 1
}

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
  docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$postgres_id" \
    psql -U graphview -d graphview -At --set ON_ERROR_STOP=1 --command "$1"
}

# Object-store loss must fail closed without creating a durable ingestion job, while liveness remains healthy.
upload_file="$temporary_directory/object-store-outage-$run_id.txt"
printf 'Graphview object-store failure proof %s\n' "$run_id" > "$upload_file"
upload_checksum="$(sha256sum "$upload_file" | awk '{print $1}')"
[[ "$(psql_value "SELECT count(*) FROM durable_jobs WHERE idempotency_key='upload:project-default:$upload_checksum'")" == "0" ]]
docker stop "$minio_id" >/dev/null
[[ "$(curl -fsS -o /dev/null -w '%{http_code}' "$base_url/health")" == "200" ]]
ready_status="$(curl -sS -o "$temporary_directory/object-ready.json" -w '%{http_code}' "$base_url/ready")"
[[ "$ready_status" == "503" ]]
jq -e '.status == "not_ready" and .database == "ok" and .session_store == "redis" and .object_store == "error"' \
  "$temporary_directory/object-ready.json" >/dev/null
upload_status="$(
  curl -sS -o "$temporary_directory/upload-failure.json" -w '%{http_code}' \
    -X POST "$base_url/api/v1/uploads" \
    -H "authorization: Bearer $service_token" \
    -F "file=@$upload_file;type=text/plain" \
    -F 'graph_id=project-default'
)"
[[ "$upload_status" == "500" ]]
jq -e '.type == "https://graphview.local/problems/internal" and .status == 500' \
  "$temporary_directory/upload-failure.json" >/dev/null
[[ "$(psql_value "SELECT count(*) FROM durable_jobs WHERE idempotency_key='upload:project-default:$upload_checksum'")" == "0" ]]
docker start "$minio_id" >/dev/null
wait_for_health "$minio_id"
jq -e '.status == "ready" and .object_store == "s3"' < <(curl -fsS "$base_url/ready") >/dev/null

# Redis loss must make readiness fail while liveness stays healthy, then recover without restarting the API.
docker stop "$redis_id" >/dev/null
[[ "$(curl -fsS -o /dev/null -w '%{http_code}' "$base_url/health")" == "200" ]]
ready_status="$(curl -sS -o "$temporary_directory/redis-ready.json" -w '%{http_code}' "$base_url/ready")"
[[ "$ready_status" == "503" ]]
jq -e '.status == "not_ready" and .database == "ok" and .session_store == "error" and .object_store == "s3"' \
  "$temporary_directory/redis-ready.json" >/dev/null
docker start "$redis_id" >/dev/null
wait_for_health "$redis_id"
jq -e '.status == "ready" and .session_store == "redis"' < <(curl -fsS "$base_url/ready") >/dev/null
docker start "$worker_id" >/dev/null 2>&1 || true
wait_for_health "$worker_id" running

# Graph activity SSE resumes strictly after Last-Event-ID.
activity_page="$(api_request GET '/api/v1/graphs/project-default/activity?limit=10')"
first_event_id="$(jq -er '.events[0].id' <<<"$activity_page")"
second_event_id="$(jq -er '.events[1].id' <<<"$activity_page")"
curl -fsS --max-time 3 "$base_url/api/v1/graphs/project-default/stream?limit=10" \
  -H "authorization: Bearer $service_token" \
  -H "Last-Event-ID: $first_event_id" \
  > "$temporary_directory/replay.sse" 2>/dev/null || true
if grep -Fq "id: $first_event_id" "$temporary_directory/replay.sse"; then
  echo "Graph activity replay repeated the acknowledged event." >&2
  exit 1
fi
grep -Fq "id: $second_event_id" "$temporary_directory/replay.sse"

# A stopped worker leaves one durable webhook delivery and one expired lease for recovery.
docker stop "$worker_id" >/dev/null
lease_job="$(
  api_request POST /api/v1/jobs \
    "$(jq -nc --arg key "failure-lease-$run_id" '{kind:"agent_context.retention",queue:"maintenance",idempotency_key:$key,payload:{project_id:"project-default"},max_attempts:3}')"
)"
lease_job_id="$(jq -er .id <<<"$lease_job")"
psql_value "UPDATE durable_jobs SET status='running',attempt=1,worker_id='injected-crashed-worker',leased_until=now()-interval '1 second' WHERE id='$lease_job_id'" >/dev/null

webhook_secret="failure-webhook-$run_id"
account="$(
  api_request POST /api/v1/connector-accounts \
    "$(jq -nc --arg secret "$webhook_secret" '{kind:"repository",display_name:"Failure injection GitHub",token_json:{webhook_secret:$secret,access_token:"failure-injection-token"}}')"
)"
account_id="$(jq -er .id <<<"$account")"
target="$(
  api_request POST /api/v1/connector-targets \
    "$(jq -nc --arg account "$account_id" --arg remote "failure/injection-$run_id" '{account_id:$account,target_type:"repository",remote_id:$remote,title:"Failure injection repository",sync_settings:{provider:"github"}}')"
)"
target_id="$(jq -er .id <<<"$target")"
webhook_payload='{"ref":"refs/heads/main"}'
webhook_signature="sha256=$(printf '%s' "$webhook_payload" | openssl dgst -sha256 -hmac "$webhook_secret" | awk '{print $NF}')"
post_webhook() {
  signature="$1"
  delivery="$2"
  curl -sS -o "$temporary_directory/webhook-$delivery.json" -w '%{http_code}' \
    -X POST "$base_url/api/v1/connectors/github/$target_id/webhook" \
    -H "X-Hub-Signature-256: $signature" \
    -H "X-GitHub-Delivery: $delivery" \
    -H 'X-GitHub-Event: push' \
    -H 'content-type: application/json' \
    --data "$webhook_payload"
}
delivery_id="failure-delivery-$run_id"
[[ "$(post_webhook "$webhook_signature" "$delivery_id-first")" == "202" ]]
mv "$temporary_directory/webhook-$delivery_id-first.json" "$temporary_directory/webhook-first.json"
[[ "$(post_webhook "$webhook_signature" "$delivery_id-second")" == "202" ]]
mv "$temporary_directory/webhook-$delivery_id-second.json" "$temporary_directory/webhook-second.json"

# Repeat the exact delivery ID, not merely the payload, and require the original durable job identity.
first_job_id="$(jq -er .id "$temporary_directory/webhook-first.json")"
duplicate_status="$(
  curl -sS -o "$temporary_directory/webhook-duplicate.json" -w '%{http_code}' \
    -X POST "$base_url/api/v1/connectors/github/$target_id/webhook" \
    -H "X-Hub-Signature-256: $webhook_signature" \
    -H "X-GitHub-Delivery: $delivery_id-first" \
    -H 'X-GitHub-Event: push' \
    -H 'content-type: application/json' \
    --data "$webhook_payload"
)"
[[ "$duplicate_status" == "202" ]]
[[ "$(jq -er .id "$temporary_directory/webhook-duplicate.json")" == "$first_job_id" ]]
invalid_status="$(post_webhook 'sha256=invalid' "failure-invalid-$run_id")"
[[ "$invalid_status" == "401" ]]
api_request POST "/api/v1/jobs/$first_job_id/cancel" '{}' | jq -e '.status == "cancelled"' >/dev/null
second_job_id="$(jq -er .id "$temporary_directory/webhook-second.json")"
api_request POST "/api/v1/jobs/$second_job_id/cancel" '{}' | jq -e '.status == "cancelled"' >/dev/null
api_request DELETE "/api/v1/connector-accounts/$account_id/credentials" | jq -e '.status == "error"' >/dev/null

docker start "$worker_id" >/dev/null
wait_for_health "$worker_id" running
lease_recovered=0
for _ in $(seq 1 90); do
  current="$(api_request GET "/api/v1/jobs/$lease_job_id")"
  if jq -e '.status == "succeeded" and .attempt == 2 and .worker_id != "injected-crashed-worker"' <<<"$current" >/dev/null; then
    lease_recovered=1
    break
  fi
  sleep 1
done
[[ "$lease_recovered" == "1" ]]

echo "Live failure proof passed: MinIO and Redis loss, liveness/readiness separation, inert upload failure, SSE resume, duplicate webhook rejection, and expired worker-lease recovery are production-proven."
