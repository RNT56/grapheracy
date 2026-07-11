#!/usr/bin/env bash
set -euo pipefail

project_name="${GRAPHVIEW_COMPOSE_PROJECT:-graphview-live-ci}"
: "${GRAPHVIEW_SERVICE_CLIENT_SECRET:?required}"

compose=(docker compose -p "$project_name" -f infra/compose/docker-compose.production.yml)
"${compose[@]}" exec -T \
  -e "GRAPHVIEW_SERVICE_CLIENT_SECRET=$GRAPHVIEW_SERVICE_CLIENT_SECRET" \
  api python - <<'PY'
import json
import os
import urllib.error
import urllib.parse
import urllib.request

api_base = "http://127.0.0.1:8000"
issuer = os.environ["GRAPHVIEW_OIDC_BACKCHANNEL_URL"].rstrip("/")
token_request = urllib.request.Request(
    f"{issuer}/protocol/openid-connect/token",
    data=urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": "graphview-service",
            "client_secret": os.environ["GRAPHVIEW_SERVICE_CLIENT_SECRET"],
        }
    ).encode(),
    headers={"content-type": "application/x-www-form-urlencoded"},
    method="POST",
)
with urllib.request.urlopen(token_request, timeout=10) as response:
    access_token = json.load(response)["access_token"]


def fetch(path: str, *, stream: bool = False):
    request = urllib.request.Request(
        f"{api_base}{path}",
        headers={"authorization": f"Bearer {access_token}", "accept": "application/json, text/event-stream"},
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = b"" if stream else response.read()
        return response.status, {key.lower(): value for key, value in response.headers.items()}, body


with urllib.request.urlopen(f"{api_base}/openapi.json", timeout=10) as response:
    specification = json.load(response)


def contract(value):
    if isinstance(value, list):
        return [contract(item) for item in value]
    if isinstance(value, dict):
        ignored = {"operationId", "summary", "tags", "title"}
        return {key: contract(item) for key, item in value.items() if key not in ignored}
    return value


paths = specification["paths"]
legacy_paths = {
    path: operations
    for path, operations in paths.items()
    if not path.startswith("/api/v1") and path not in {"/health", "/version"}
}
if len(legacy_paths) < 78:
    raise SystemExit(f"Expected at least 78 compatibility paths, found {len(legacy_paths)}")

operation_count = 0
for legacy_path, legacy_operations in legacy_paths.items():
    successor_path = f"/api/v1{legacy_path}"
    if successor_path not in paths:
        raise SystemExit(f"Missing compatibility successor for {legacy_path}")
    for method, legacy_operation in legacy_operations.items():
        operation_count += 1
        successor_operation = paths[successor_path].get(method)
        if successor_operation is None:
            raise SystemExit(f"Missing {method.upper()} compatibility successor for {legacy_path}")
        if contract(successor_operation) != contract(legacy_operation):
            raise SystemExit(f"Contract drift for {method.upper()} {legacy_path}")

graph_status, _, graph_body = fetch("/api/v1/graph")
if graph_status != 200:
    raise SystemExit(f"Unable to resolve graph anchors: HTTP {graph_status}")
graph = json.loads(graph_body)
node_ids = [node["id"] for node in graph.get("nodes", [])]
source_node_id = node_ids[0] if node_ids else "missing-alias-node-a"
target_node_id = node_ids[1] if len(node_ids) > 1 else "missing-alias-node-b"

substitutions = {
    "{agent_run_id}": "missing-alias-agent-run",
    "{artifact_id}": "missing-alias-artifact",
    "{entity_id}": source_node_id,
    "{entity_kind}": "node",
    "{node_id}": source_node_id,
    "{session_id}": "missing-alias-session",
    "{signal_id}": "missing-alias-signal",
    "{sync_run_id}": "missing-alias-sync-run",
}
queries = {
    "/graph/path": {"source_node_id": source_node_id, "target_node_id": target_node_id},
    "/search": {"q": "Graphview"},
}
stream_paths = {"/graph/activity/stream", "/agent-context/sessions/{session_id}/stream"}
volatile_paths = {"/backup", "/export", "/observability/metrics"}


def normalized_json(body: bytes):
    value = json.loads(body)

    def normalize(item):
        if isinstance(item, list):
            return [normalize(entry) for entry in item]
        if isinstance(item, dict):
            return {
                key: normalize(entry)
                for key, entry in item.items()
                if key not in {"exported_at", "generated_at", "instance", "request_id"}
            }
        return item

    return normalize(value)


replayed = 0
for template, operations in sorted(legacy_paths.items()):
    if "get" not in operations and "head" not in operations:
        continue
    path = template
    for placeholder, value in substitutions.items():
        path = path.replace(placeholder, urllib.parse.quote(value, safe=""))
    if "{" in path:
        raise SystemExit(f"Missing compatibility replay substitution for {template}")
    query = queries.get(template)
    if query:
        path = f"{path}?{urllib.parse.urlencode(query)}"

    stream = template in stream_paths
    legacy_status, legacy_headers, legacy_body = fetch(path, stream=stream)
    successor_path = f"/api/v1{path}"
    successor_status, successor_headers, successor_body = fetch(successor_path, stream=stream)
    replayed += 1

    if legacy_status != successor_status:
        raise SystemExit(f"Status drift for {template}: {legacy_status} != {successor_status}")
    if legacy_headers.get("deprecation") != "true":
        raise SystemExit(f"Missing Deprecation header for {template}")
    if not legacy_headers.get("sunset"):
        raise SystemExit(f"Missing Sunset header for {template}")
    expected_link = f'</api/v1{path.split("?", 1)[0]}>; rel="successor-version"'
    if legacy_headers.get("link") != expected_link:
        raise SystemExit(f"Incorrect successor Link for {template}: {legacy_headers.get('link')}")
    if "deprecation" in successor_headers:
        raise SystemExit(f"Canonical V1 route is marked deprecated for {template}")
    legacy_content_type = legacy_headers.get("content-type", "").split(";", 1)[0]
    successor_content_type = successor_headers.get("content-type", "").split(";", 1)[0]
    if legacy_content_type != successor_content_type:
        raise SystemExit(f"Content type drift for {template}: {legacy_content_type} != {successor_content_type}")
    if not stream and template not in volatile_paths:
        if legacy_content_type == "application/json" or legacy_content_type.endswith("+json"):
            if normalized_json(legacy_body) != normalized_json(successor_body):
                raise SystemExit(f"Response drift for {template}")
        elif legacy_body != successor_body:
            raise SystemExit(f"Response drift for {template}")

print(
    "Graphview live compatibility proof passed "
    f"({len(legacy_paths)} paths, {operation_count} operations, {replayed} safe read replays)."
)
PY
