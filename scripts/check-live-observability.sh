#!/usr/bin/env bash
set -euo pipefail

project_name="${GRAPHVIEW_COMPOSE_PROJECT:-graphview-live-ci}"
temporary_directory="$(mktemp -d -t graphview-otel-proof.XXXXXX)"
traces_file="$temporary_directory/traces.json"
metrics_file="$temporary_directory/metrics.json"
trap 'rm -rf "$temporary_directory"' EXIT

collector_id="$(
  docker ps -q \
    --filter "label=com.docker.compose.project=$project_name" \
    --filter "label=com.docker.compose.service=otel-collector" \
  | head -n 1
)"
if [[ -z "$collector_id" ]]; then
  echo "The Graphview OpenTelemetry Collector is not running for project $project_name." >&2
  exit 1
fi

ready=0
for _ in $(seq 1 30); do
  rm -f "$traces_file" "$metrics_file"
  docker cp "$collector_id:/var/lib/otel/traces.json" "$traces_file" >/dev/null 2>&1 || true
  docker cp "$collector_id:/var/lib/otel/metrics.json" "$metrics_file" >/dev/null 2>&1 || true
  if [[ -s "$traces_file" && -s "$metrics_file" ]] \
    && grep -q 'graphview.job.execute' "$traces_file" \
    && grep -q 'graphview.api.requests' "$metrics_file" \
    && grep -q 'graphview.worker.jobs' "$metrics_file" \
    && grep -q 'graphview.sse.events' "$metrics_file"; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" -ne 1 ]]; then
  echo "Graphview telemetry did not reach the Collector within 60 seconds." >&2
  docker logs --tail=200 "$collector_id" >&2
  exit 1
fi

python3 - "$traces_file" "$metrics_file" <<'PY'
import json
import os
import sys
from pathlib import Path


def documents(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def attribute_value(attributes: list[dict], key: str):
    for attribute in attributes:
        if attribute.get("key") != key:
            continue
        value = attribute.get("value") or {}
        return next(iter(value.values()), None)
    return None


trace_documents = documents(sys.argv[1])
metric_documents = documents(sys.argv[2])
spans: list[tuple[str | None, dict]] = []
for document in trace_documents:
    for resource_spans in document.get("resourceSpans", []):
        service_name = attribute_value(resource_spans.get("resource", {}).get("attributes", []), "service.name")
        for scope in resource_spans.get("scopeSpans", []):
            spans.extend((service_name, span) for span in scope.get("spans", []))

api_upload_trace_ids = {
    span.get("traceId")
    for service, span in spans
    if service == "graphview-api" and "/api/v1/uploads" in str(span.get("name"))
}
worker_job_trace_ids = {
    span.get("traceId")
    for service, span in spans
    if service == "graphview-worker" and span.get("name") == "graphview.job.execute"
}
if not api_upload_trace_ids:
    raise SystemExit("Collector proof is missing the upload API server span")
if not worker_job_trace_ids:
    raise SystemExit("Collector proof is missing the durable worker execution span")
if api_upload_trace_ids.isdisjoint(worker_job_trace_ids):
    raise SystemExit("The durable worker span is not linked to its originating API trace")
for _, span in spans:
    for attribute in span.get("attributes", []):
        key = str(attribute.get("key"))
        value = str(attribute_value([attribute], key) or "")
        if key == "url.query" and value not in {"", "<redacted>"}:
            raise SystemExit("Collector output contains an unredacted URL query")
        if key in {"url.full", "http.url"} and ("?" in value or "#" in value):
            raise SystemExit("Collector output contains a query or fragment in a traced URL")

metric_names: set[str] = set()
service_names: set[str] = set()
for document in metric_documents:
    for resource_metrics in document.get("resourceMetrics", []):
        service_names.add(
            str(attribute_value(resource_metrics.get("resource", {}).get("attributes", []), "service.name"))
        )
        for scope in resource_metrics.get("scopeMetrics", []):
            metric_names.update(str(metric.get("name")) for metric in scope.get("metrics", []))

required_metrics = {
    "graphview.api.requests",
    "graphview.api.request.duration",
    "graphview.sse.events",
    "graphview.sse.connection.duration",
    "graphview.worker.jobs",
    "graphview.worker.queue_latency",
    "graphview.worker.job.duration",
}
missing_metrics = sorted(required_metrics - metric_names)
if missing_metrics:
    raise SystemExit(f"Collector proof is missing metrics: {', '.join(missing_metrics)}")
if not {"graphview-api", "graphview-worker"}.issubset(service_names):
    raise SystemExit("Collector proof is missing API or worker service resources")

telemetry_text = Path(sys.argv[1]).read_text() + Path(sys.argv[2]).read_text()
for variable in (
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "MINIO_ROOT_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "VAULT_DEV_ROOT_TOKEN",
    "GRAPHVIEW_SECRET_KEY",
    "GRAPHVIEW_SERVICE_CLIENT_SECRET",
    "GRAPHVIEW_LIVE_PASSWORD",
):
    value = os.environ.get(variable, "")
    if value and value in telemetry_text:
        raise SystemExit(f"Collector output leaked {variable}")

print(
    "Collector proof passed: API-to-worker trace continuity, API/worker/SSE metrics, "
    "and acceptance-secret redaction are present."
)
PY
