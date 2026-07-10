from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict
from time import perf_counter
from uuid import uuid4

from fastapi import Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from graphview_api.observability import current_trace_id


class RequestRateLimiter:
    def __init__(self, settings):
        self.settings = settings
        self.redis = None if settings.environment in {"local", "test", "development"} else Redis.from_url(
            settings.arq_redis_url, decode_responses=True
        )
        self.memory: dict[str, int] = defaultdict(int)

    async def allow(self, identity: str, *, mutation: bool) -> tuple[bool, int]:
        window = max(1, self.settings.rate_limit_window_seconds)
        limit = self.settings.rate_limit_mutations if mutation else self.settings.rate_limit_requests
        bucket = int(time.time() // window)
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
        key = f"graphview:rate:{'mutation' if mutation else 'request'}:{bucket}:{digest}"
        if self.redis is None:
            self.memory[key] += 1
            if len(self.memory) > 10_000:
                self.memory = {item: count for item, count in self.memory.items() if f":{bucket}:" in item}
            return self.memory[key] <= limit, window
        pipeline = self.redis.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, window + 1)
        count, _ = await pipeline.execute()
        return int(count) <= limit, window


def install_http_middleware(app, settings) -> None:
    limiter = RequestRateLimiter(settings)
    app.state.rate_limiter = limiter

    @app.middleware("http")
    async def enforce_and_observe(request: Request, call_next):
        trace_id = current_trace_id() or request.headers.get("X-Graphview-Trace-Id") or f"trace_{uuid4().hex[:20]}"
        request_id = request.headers.get("X-Request-Id") or f"request_{uuid4().hex[:20]}"
        started = perf_counter()
        status_code = 500
        response = None
        try:
            forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
            identity = forwarded or (request.client.host if request.client else "unknown")
            if request.url.path in {"/health", "/ready"}:
                allowed, retry_after = True, 1
            else:
                try:
                    allowed, retry_after = await limiter.allow(
                        f"{identity}:{request.url.path}", mutation=request.method not in {"GET", "HEAD", "OPTIONS"}
                    )
                except Exception:
                    if settings.environment not in {"local", "test", "development"}:
                        response = JSONResponse(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            content={"type": "https://graphview.local/problems/rate-limit-store", "title": "Request protection unavailable", "status": 503},
                            media_type="application/problem+json",
                        )
                        status_code = response.status_code
                        return response
                    allowed, retry_after = True, 1
            if not allowed:
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"type": "https://graphview.local/problems/rate-limit", "title": "Rate limit exceeded", "status": 429},
                    headers={"Retry-After": str(retry_after)},
                    media_type="application/problem+json",
                )
                status_code = response.status_code
                return response
            session_id = request.cookies.get(settings.session_cookie_name)
            if request.method not in {"GET", "HEAD", "OPTIONS"} and session_id:
                session = await app.state.identity.session(session_id)
                supplied_csrf = request.headers.get("X-CSRF-Token")
                if session is None or not supplied_csrf or not secrets.compare_digest(supplied_csrf, session["csrf_token"]):
                    response = JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"type": "https://graphview.local/problems/csrf", "title": "CSRF validation failed", "status": 403},
                        media_type="application/problem+json",
                    )
                    status_code = response.status_code
                    return response
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = perf_counter() - started
            route = request.scope.get("route")
            route_path = getattr(route, "path", None) or "unmatched"
            app.state.metrics.record(
                path=route_path,
                status_code=status_code,
                duration_ms=duration_seconds * 1000,
            )
            app.state.telemetry.record_request(
                route=route_path,
                method=request.method,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            if response is not None:
                response.headers["X-Graphview-Trace-Id"] = trace_id
                response.headers["X-Request-Id"] = request_id
                if not request.url.path.startswith("/api/v1") and request.url.path not in {
                    "/health", "/ready", "/version", "/openapi.json", "/docs", "/redoc"
                }:
                    response.headers["Deprecation"] = "true"
                    response.headers["Sunset"] = "Tue, 01 Dec 2026 00:00:00 GMT"
                    response.headers["Link"] = f'</api/v1{request.url.path}>; rel="successor-version"'
