#!/usr/bin/env bash
set -euo pipefail

project_name="${GRAPHVIEW_COMPOSE_PROJECT:-graphview-live-ci}"
base_url="${GRAPHVIEW_PUBLIC_URL:-http://127.0.0.1:8080}"
requests="${GRAPHVIEW_PERFORMANCE_REQUESTS:-40}"
receipt="${GRAPHVIEW_PERFORMANCE_RECEIPT:-tmp/performance/live-production.json}"

: "${GRAPHVIEW_SERVICE_CLIENT_SECRET:?required}"
: "${POSTGRES_PASSWORD:?required}"

postgres_id="$(
  docker ps -q \
    --filter "label=com.docker.compose.project=$project_name" \
    --filter "label=com.docker.compose.service=postgres" \
  | head -n 1
)"
if [[ -z "$postgres_id" ]]; then
  echo "The Graphview PostgreSQL service is not running for project $project_name." >&2
  exit 1
fi

docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" "$postgres_id" \
  psql -U graphview -d graphview -v ON_ERROR_STOP=1 < infra/performance/seed-production.sql >/dev/null

GRAPHVIEW_PUBLIC_URL="$base_url" \
GRAPHVIEW_SERVICE_CLIENT_SECRET="$GRAPHVIEW_SERVICE_CLIENT_SECRET" \
  uv run --package graphview-api python scripts/benchmark-viewport.py \
    --requests "$requests" \
    --output "$receipt"

jq -e '
  .passed == true
  and .dataset == {nodes:100000,edges:500000}
  and ([.results[].name] == ["viewport-overview","viewport-detail","focused-subgraph","hybrid-search"])
  and all(.results[]; .p95_ms <= .threshold_ms)
' "$receipt" >/dev/null

echo "Live performance proof passed and wrote $receipt."
