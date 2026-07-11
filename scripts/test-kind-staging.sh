#!/usr/bin/env bash
set -euo pipefail

: "${GRAPHVIEW_STAGING_WEB_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_API_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_WORKER_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_OTEL_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_OPS_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_KEYCLOAK_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_CLAMAV_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_MINIO_IMAGE:?required}"
: "${GRAPHVIEW_STAGING_IMAGE_MANIFEST:?required}"
: "${POSTGRES_PASSWORD:?required}"
: "${REDIS_PASSWORD:?required}"
: "${MINIO_ROOT_USER:?required}"
: "${MINIO_ROOT_PASSWORD:?required}"
: "${KEYCLOAK_ADMIN_PASSWORD:?required}"
: "${VAULT_DEV_ROOT_TOKEN:?required}"
: "${GRAPHVIEW_SECRET_KEY:?required}"
: "${GRAPHVIEW_SERVICE_CLIENT_SECRET:?required}"

namespace="${GRAPHVIEW_STAGING_NAMESPACE:-graphview-staging}"
release="${GRAPHVIEW_STAGING_RELEASE:-graphview}"
chart="${GRAPHVIEW_STAGING_CHART:-infra/helm/graphview}"
base_url="${GRAPHVIEW_STAGING_BASE_URL:-http://127.0.0.1:18080}"
receipt_path="${GRAPHVIEW_STAGING_RECEIPT_PATH:-artifacts/staging-smoke-receipt.json}"
temporary_directory="$(mktemp -d -t graphview-staging.XXXXXX)"
port_forward_pid=""

cleanup() {
  if [[ -n "$port_forward_pid" ]]; then
    kill "$port_forward_pid" >/dev/null 2>&1 || true
    wait "$port_forward_pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$namespace" create secret generic graphview-runtime \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=REDIS_PASSWORD="$REDIS_PASSWORD" \
  --from-literal=MINIO_ROOT_USER="$MINIO_ROOT_USER" \
  --from-literal=MINIO_ROOT_PASSWORD="$MINIO_ROOT_PASSWORD" \
  --from-literal=KEYCLOAK_ADMIN_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" \
  --from-literal=GRAPHVIEW_SECRET_KEY="$GRAPHVIEW_SECRET_KEY" \
  --from-literal=GRAPHVIEW_SERVICE_CLIENT_SECRET="$GRAPHVIEW_SERVICE_CLIENT_SECRET" \
  --from-literal=VAULT_DEV_ROOT_TOKEN="$VAULT_DEV_ROOT_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

helm_arguments=(
  "$release" "$chart"
  --namespace "$namespace"
  --install
  --wait
  --timeout 15m
  --set-string image.web="$GRAPHVIEW_STAGING_WEB_IMAGE"
  --set-string image.api="$GRAPHVIEW_STAGING_API_IMAGE"
  --set-string image.worker="$GRAPHVIEW_STAGING_WORKER_IMAGE"
  --set-string image.otel="$GRAPHVIEW_STAGING_OTEL_IMAGE"
  --set-string backup.image="$GRAPHVIEW_STAGING_OPS_IMAGE"
  --set-string minio.image="$GRAPHVIEW_STAGING_MINIO_IMAGE"
  --set-string minio.clientImage="$GRAPHVIEW_STAGING_OPS_IMAGE"
  --set-string keycloak.image="$GRAPHVIEW_STAGING_KEYCLOAK_IMAGE"
  --set-string clamav.image="$GRAPHVIEW_STAGING_CLAMAV_IMAGE"
  --set image.pullPolicy=IfNotPresent
  --set replicas.web=1
  --set replicas.api=1
  --set replicas.worker=1
  --set autoscaling.enabled=false
  --set backup.enabled=false
  --set ingress.enabled=false
  --set database.persistence.enabled=false
  --set redis.persistence.enabled=false
  --set minio.persistence.enabled=false
  --set clamav.persistence.enabled=false
  --set vault.server.dataStorage.enabled=false
  --set-string publicUrl="$base_url"
  --set-string oidcIssuerUrl="$base_url/identity/realms/graphview"
)

wait_for_release() {
  kubectl -n "$namespace" wait --for=condition=complete job \
    -l app.kubernetes.io/name=graphview-migrate --timeout=15m
  local resource
  while IFS= read -r resource; do
    [[ -n "$resource" ]] && kubectl -n "$namespace" rollout status "$resource" --timeout=15m
  done < <(kubectl -n "$namespace" get deployments -o name)
  while IFS= read -r resource; do
    [[ -z "$resource" ]] && continue
    desired="$(kubectl -n "$namespace" get "$resource" -o jsonpath='{.spec.replicas}')"
    for _ in $(seq 1 180); do
      ready="$(kubectl -n "$namespace" get "$resource" -o jsonpath='{.status.readyReplicas}')"
      [[ "${ready:-0}" == "$desired" ]] && break
      sleep 5
    done
    ready="$(kubectl -n "$namespace" get "$resource" -o jsonpath='{.status.readyReplicas}')"
    if [[ "${ready:-0}" != "$desired" ]]; then
      echo "$resource has ${ready:-0}/$desired ready replicas." >&2
      return 1
    fi
  done < <(kubectl -n "$namespace" get statefulsets -o name)
}

start_port_forward() {
  kubectl -n "$namespace" port-forward "service/$release-web" 18080:8080 \
    >"$temporary_directory/port-forward.log" 2>&1 &
  port_forward_pid="$!"
  for _ in $(seq 1 120); do
    if curl -fsS "$base_url/health" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$port_forward_pid" >/dev/null 2>&1; then
      cat "$temporary_directory/port-forward.log" >&2
      return 1
    fi
    sleep 1
  done
  cat "$temporary_directory/port-forward.log" >&2
  return 1
}

service_token() {
  curl -fsS -X POST "$base_url/identity/realms/graphview/protocol/openid-connect/token" \
    -H 'content-type: application/x-www-form-urlencoded' \
    --data-urlencode grant_type=client_credentials \
    --data-urlencode client_id=graphview-service \
    --data-urlencode client_secret="$GRAPHVIEW_SERVICE_CLIENT_SECRET" \
  | jq -er .access_token
}

api_request() {
  local method="$1"
  local path="$2"
  curl -fsS -X "$method" "$base_url$path" -H "authorization: Bearer $token"
}

helm upgrade "${helm_arguments[@]}"
wait_for_release
actual_images="$(kubectl -n "$namespace" get pods -o json | jq -r '.items[].spec.containers[].image' | sort -u)"
for expected_image in \
  "$GRAPHVIEW_STAGING_WEB_IMAGE" "$GRAPHVIEW_STAGING_API_IMAGE" \
  "$GRAPHVIEW_STAGING_WORKER_IMAGE" "$GRAPHVIEW_STAGING_OTEL_IMAGE" \
  "$GRAPHVIEW_STAGING_OPS_IMAGE" "$GRAPHVIEW_STAGING_KEYCLOAK_IMAGE" \
  "$GRAPHVIEW_STAGING_CLAMAV_IMAGE" "$GRAPHVIEW_STAGING_MINIO_IMAGE"; do
  grep -Fx "$expected_image" <<<"$actual_images" >/dev/null || {
    echo "Expected candidate image did not run in staging: $expected_image" >&2
    exit 1
  }
done
start_port_forward

curl -fsS "$base_url/health" | jq -e '.status == "ok"' >/dev/null
curl -fsS "$base_url/ready" | jq -e '.status == "ready"' >/dev/null
token="$(service_token)"
api_request GET /api/v1/graphs | jq -e 'any(.[]; .id == "project-default")' >/dev/null

run_id="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
source_title="Kind staging evidence $run_id"
fixture="$temporary_directory/staging-evidence.md"
printf '# %s\nGraphview staging traverses the API, ClamAV, MinIO, Redis, and the durable worker.\n' \
  "$source_title" > "$fixture"
accepted="$(
  curl -fsS -X POST "$base_url/api/v1/uploads" \
    -H "authorization: Bearer $token" \
    -F "title=$source_title" \
    -F graph_id=project-default \
    -F "file=@$fixture;type=text/markdown"
)"
job_id="$(jq -er .job_id <<<"$accepted")"

job=""
for _ in $(seq 1 120); do
  job="$(api_request GET "/api/v1/jobs/$job_id")"
  status="$(jq -er .status <<<"$job")"
  case "$status" in
    succeeded) break ;;
    failed|cancelled|dead_letter) jq . <<<"$job" >&2; exit 1 ;;
  esac
  sleep 1
done
jq -e --arg title "$source_title" \
  '.status == "succeeded" and .kind == "upload.ingest" and .attempt == 1 and .result.source.title == $title' \
  <<<"$job" >/dev/null
api_request GET '/api/v1/review-queue?graph_id=project-default&limit=100' \
  | jq -e --arg title "$source_title" \
      '.pending_count > 0 and any(.items[]; .source.title == $title)' >/dev/null

helm upgrade "${helm_arguments[@]}"
wait_for_release
curl -fsS "$base_url/health" | jq -e '.status == "ok"' >/dev/null
curl -fsS "$base_url/ready" | jq -e '.status == "ready"' >/dev/null
api_request GET "/api/v1/jobs/$job_id" | jq -e '.status == "succeeded"' >/dev/null

mkdir -p "$(dirname "$receipt_path")"
image_manifest="$(jq -e --arg commit "${GRAPHVIEW_STAGING_COMMIT:-${GITHUB_SHA:-local}}" \
  '.schema_version == 1 and .commit == $commit and (.images | length == 8) and all(.images[]; (.reference | type == "string") and (.digest | test("^sha256:[0-9a-f]{64}$")))' \
  "$GRAPHVIEW_STAGING_IMAGE_MANIFEST" >/dev/null && jq -c .images "$GRAPHVIEW_STAGING_IMAGE_MANIFEST")"
jq -n \
  --arg commit "${GRAPHVIEW_STAGING_COMMIT:-${GITHUB_SHA:-local}}" \
  --arg namespace "$namespace" \
  --arg release "$release" \
  --arg job_id "$job_id" \
  --arg source_title "$source_title" \
  --argjson images "$image_manifest" \
  '{schema_version:1,commit:$commit,namespace:$namespace,release:$release,job_id:$job_id,source_title:$source_title,images:$images,migration:"complete",helm_upgrade:"healthy",credentials_included:false}' \
  > "$receipt_path"

echo "Kind staging acceptance passed: exact candidate images survived install, authenticated ingestion, and no-op Helm upgrade."
