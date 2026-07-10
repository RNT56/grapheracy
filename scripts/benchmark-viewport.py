from __future__ import annotations

import argparse
import statistics
import time

import httpx


parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--requests", type=int, default=40)
parser.add_argument("--p95-ms", type=float, default=250)
arguments = parser.parse_args()

durations = []
with httpx.Client(base_url=arguments.base_url, headers={"X-Graphview-User": "maintainer"}, timeout=30) as client:
    for index in range(arguments.requests + 5):
        started = time.perf_counter()
        response = client.get(
            "/api/v1/graphs/project-performance/viewport",
            params={"zoom": 0.25, "max_nodes": 2000, "max_edges": 8000},
        )
        response.raise_for_status()
        if index >= 5:
            durations.append((time.perf_counter() - started) * 1000)

p95 = statistics.quantiles(durations, n=100, method="inclusive")[94]
print(f"viewport p50={statistics.median(durations):.1f}ms p95={p95:.1f}ms max={max(durations):.1f}ms")
if p95 > arguments.p95_ms:
    raise SystemExit(f"viewport p95 {p95:.1f}ms exceeds {arguments.p95_ms:.1f}ms")
