from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path
from typing import Any

import httpx


parser = argparse.ArgumentParser(description="Benchmark Graphview V1 projections against a seeded production stack.")
parser.add_argument("--base-url", default=os.getenv("GRAPHVIEW_PUBLIC_URL", "http://127.0.0.1:8080"))
parser.add_argument("--requests", type=int, default=40)
parser.add_argument("--warmup", type=int, default=5)
parser.add_argument("--p95-ms", type=float, default=250)
parser.add_argument("--bearer-token", default=os.getenv("GRAPHVIEW_BENCHMARK_TOKEN"))
parser.add_argument("--client-id", default="graphview-service")
parser.add_argument("--client-secret", default=os.getenv("GRAPHVIEW_SERVICE_CLIENT_SECRET"))
parser.add_argument("--token-url")
parser.add_argument("--development-auth", action="store_true")
parser.add_argument("--output")
arguments = parser.parse_args()

if arguments.requests < 2 or arguments.warmup < 0:
    raise SystemExit("--requests must be at least 2 and --warmup cannot be negative")

base_url = arguments.base_url.rstrip("/")
token_url = arguments.token_url or f"{base_url}/identity/realms/graphview/protocol/openid-connect/token"
bearer_token = arguments.bearer_token
if not bearer_token and arguments.client_secret:
    token_response = httpx.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": arguments.client_id,
            "client_secret": arguments.client_secret,
        },
        timeout=30,
    )
    token_response.raise_for_status()
    bearer_token = token_response.json()["access_token"]

if bearer_token:
    headers = {"Authorization": f"Bearer {bearer_token}"}
elif arguments.development_auth:
    headers = {"X-Graphview-User": "maintainer"}
else:
    raise SystemExit(
        "Production performance proof requires GRAPHVIEW_BENCHMARK_TOKEN or "
        "GRAPHVIEW_SERVICE_CLIENT_SECRET; use --development-auth only for an explicit developer adapter."
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


cases = [
    {
        "name": "viewport-overview",
        "path": "/api/v1/graphs/project-performance/viewport",
        "params": {"zoom": 0.25, "max_nodes": 2_000, "max_edges": 8_000},
        "validate": lambda body: require(
            body["level"] == "clusters"
            and len(body["clusters"]) > 0
            and body["page"]["total_count"] == 100_000,
            "overview did not return the complete clustered production projection",
        ),
    },
    {
        "name": "viewport-detail",
        "path": "/api/v1/graphs/project-performance/viewport",
        "params": {
            "zoom": 4,
            "min_x": -1,
            "min_y": -1,
            "max_x": -0.88,
            "max_y": -0.88,
            "max_nodes": 5_000,
            "max_edges": 20_000,
        },
        "validate": lambda body: require(
            body["level"] == "nodes" and len(body["nodes"]) > 0 and not body["clusters"],
            "detail viewport did not progressively replace clusters with concrete nodes",
        ),
    },
    {
        "name": "focused-subgraph",
        "path": "/api/v1/graphs/project-performance/subgraph",
        "params": {"focus_node_id": "perf-node-000001", "depth": 2, "max_nodes": 100},
        "validate": lambda body: require(
            body["focus_node_id"] == "perf-node-000001"
            and any(node["id"] == "perf-node-000001" for node in body["nodes"])
            and len(body["nodes"]) <= 100,
            "focused subgraph is missing its anchor or exceeded its node bound",
        ),
    },
    {
        "name": "hybrid-search",
        "path": "/api/v1/graphs/project-performance/search",
        "params": {"q": "Benchmark node 4242", "limit": 25},
        "validate": lambda body: require(
            len(body["anchors"]) > 0 and len(body["anchors"]) <= 25,
            "hybrid search did not return a bounded graph anchor",
        ),
    },
]

results: list[dict[str, Any]] = []
with httpx.Client(base_url=base_url, headers=headers, timeout=30) as client:
    for case in cases:
        durations = []
        response_size = 0
        for index in range(arguments.requests + arguments.warmup):
            started = time.perf_counter()
            response = client.get(case["path"], params=case["params"])
            duration_ms = (time.perf_counter() - started) * 1_000
            response.raise_for_status()
            body = response.json()
            case["validate"](body)
            response_size = len(response.content)
            if index >= arguments.warmup:
                durations.append(duration_ms)
        p95 = statistics.quantiles(durations, n=100, method="inclusive")[94]
        result = {
            "name": case["name"],
            "requests": len(durations),
            "p50_ms": round(statistics.median(durations), 3),
            "p95_ms": round(p95, 3),
            "max_ms": round(max(durations), 3),
            "response_bytes": response_size,
            "threshold_ms": arguments.p95_ms,
            "passed": p95 <= arguments.p95_ms,
        }
        results.append(result)
        print(
            f"{result['name']}: p50={result['p50_ms']:.1f}ms p95={result['p95_ms']:.1f}ms "
            f"max={result['max_ms']:.1f}ms bytes={response_size}"
        )

receipt = {
    "schema_version": 1,
    "graph_id": "project-performance",
    "dataset": {"nodes": 100_000, "edges": 500_000},
    "reference_machine": {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    },
    "results": results,
    "passed": all(result["passed"] for result in results),
}
if arguments.output:
    output_path = Path(arguments.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{json.dumps(receipt, indent=2)}\n")
if not receipt["passed"]:
    failed = ", ".join(result["name"] for result in results if not result["passed"])
    raise SystemExit(f"Performance p95 exceeded {arguments.p95_ms:.1f}ms: {failed}")
print("Live production-size viewport, progressive expansion, subgraph, and hybrid-search performance passed.")
