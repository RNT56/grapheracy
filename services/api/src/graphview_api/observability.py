from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter
from typing import Any, AsyncIterable, AsyncIterator

from opentelemetry import metrics, propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


SENSITIVE_HEADERS = [
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-csrf-token",
    "x-vault-token",
]


@dataclass
class TelemetryRuntime:
    tracer: Any
    request_counter: Any
    request_duration: Any
    sse_connections: Any
    sse_events: Any
    sse_duration: Any

    def record_request(self, *, route: str, method: str, status_code: int, duration_seconds: float) -> None:
        attributes = {
            "http.route": route,
            "http.request.method": method,
            "http.response.status_code": status_code,
        }
        self.request_counter.add(1, attributes)
        self.request_duration.record(max(0.0, duration_seconds), attributes)


def telemetry_runtime(service_name: str) -> TelemetryRuntime:
    tracer = trace.get_tracer(service_name)
    meter = metrics.get_meter(service_name)
    return TelemetryRuntime(
        tracer=tracer,
        request_counter=meter.create_counter("graphview.api.requests", unit="{request}"),
        request_duration=meter.create_histogram("graphview.api.request.duration", unit="s"),
        sse_connections=meter.create_up_down_counter("graphview.sse.connections", unit="{connection}"),
        sse_events=meter.create_counter("graphview.sse.events", unit="{event}"),
        sse_duration=meter.create_histogram("graphview.sse.connection.duration", unit="s"),
    )


async def observe_sse_stream(
    stream: AsyncIterable[str],
    telemetry: TelemetryRuntime,
    *,
    stream_kind: str,
) -> AsyncIterator[str]:
    attributes = {"graphview.sse.kind": stream_kind}
    started = perf_counter()
    telemetry.sse_connections.add(1, attributes)
    with telemetry.tracer.start_as_current_span("graphview.sse.stream", attributes=attributes) as span:
        event_count = 0
        try:
            async for item in stream:
                if item.lstrip().startswith("data:") or "\ndata:" in item:
                    event_count += 1
                    telemetry.sse_events.add(1, attributes)
                yield item
        finally:
            duration = max(0.0, perf_counter() - started)
            span.set_attribute("graphview.sse.events", event_count)
            span.set_attribute("graphview.sse.duration", duration)
            telemetry.sse_connections.add(-1, attributes)
            telemetry.sse_duration.record(duration, attributes)


def current_traceparent() -> str | None:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier.get("traceparent")


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return f"{context.trace_id:032x}"


def extract_trace_context(traceparent: object):
    if not isinstance(traceparent, str) or not traceparent.startswith("00-"):
        return None
    return propagate.extract({"traceparent": traceparent})


def sanitized_outbound_url(url: object) -> str:
    copy_with = getattr(url, "copy_with", None)
    if callable(copy_with):
        return str(copy_with(query=None, fragment=None))
    return str(url).split("?", 1)[0].split("#", 1)[0]


def sanitize_httpx_span(span, request_info) -> None:
    if not span or not span.is_recording():
        return
    safe_url = sanitized_outbound_url(request_info.url)
    span.set_attribute("url.full", safe_url)
    span.set_attribute("http.url", safe_url)
    span.set_attribute("http.target", request_info.url.path)


def sanitize_server_span(span, scope) -> None:
    if not span or not span.is_recording():
        return
    path = str(scope.get("path") or "/")
    scheme = str(scope.get("scheme") or "http")
    server = scope.get("server")
    host, port = server if isinstance(server, (tuple, list)) and len(server) == 2 else ("graphview.invalid", None)
    host = f"[{host}]" if ":" in str(host) and not str(host).startswith("[") else str(host)
    port_suffix = "" if port in {None, 80 if scheme == "http" else 443} else f":{port}"
    safe_url = f"{scheme}://{host}{port_suffix}{path}"
    span.set_attribute("graphview.request.method", str(scope.get("method") or ""))
    span.set_attribute("url.path", path)
    span.set_attribute("url.full", safe_url)
    span.set_attribute("http.url", safe_url)
    span.set_attribute("http.target", path)
    span.set_attribute("url.query", "<redacted>" if scope.get("query_string") else "")


@dataclass
class RequestMetrics:
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    total_requests: int = 0
    status_counts: Counter[str] = field(default_factory=Counter)
    path_counts: Counter[str] = field(default_factory=Counter)
    last_request_at: datetime | None = None
    last_status_code: int | None = None
    last_path: str | None = None
    last_duration_ms: float | None = None
    _lock: Lock = field(default_factory=Lock)

    def record(self, *, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            self.status_counts[str(status_code)] += 1
            self.path_counts[path] += 1
            self.last_request_at = datetime.now(tz=UTC)
            self.last_status_code = status_code
            self.last_path = path
            self.last_duration_ms = round(duration_ms, 3)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "started_at": self.started_at.isoformat(),
                "total_requests": self.total_requests,
                "status_counts": dict(self.status_counts),
                "path_counts": dict(self.path_counts),
                "last_request_at": self.last_request_at.isoformat() if self.last_request_at else None,
                "last_status_code": self.last_status_code,
                "last_path": self.last_path,
                "last_duration_ms": self.last_duration_ms,
            }


def configure_telemetry(app, engine, settings) -> TelemetryRuntime:
    if not settings.otel_exporter_otlp_endpoint:
        return telemetry_runtime(settings.otel_service_name)
    resource = telemetry_resource(settings)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=settings.otel_exporter_otlp_endpoint.startswith("http://")))
    )
    trace.set_tracer_provider(provider)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=settings.otel_exporter_otlp_endpoint,
                        insecure=settings.otel_exporter_otlp_endpoint.startswith("http://"),
                    ),
                    export_interval_millis=settings.otel_metric_export_interval_ms,
                )
            ],
        )
    )

    FastAPIInstrumentor.instrument_app(
        app,
        server_request_hook=sanitize_server_span,
        excluded_urls="health,ready,observability/ready",
        http_capture_headers_server_request=[],
        http_capture_headers_server_response=[],
        http_capture_headers_sanitize_fields=SENSITIVE_HEADERS,
    )
    SQLAlchemyInstrumentor().instrument(engine=engine)
    HTTPXClientInstrumentor().instrument(request_hook=sanitize_httpx_span)
    return telemetry_runtime(settings.otel_service_name)


def configure_worker_telemetry(settings, engine):
    if not settings.otel_exporter_otlp_endpoint:
        return trace.get_tracer("graphview.worker"), metrics.get_meter("graphview.worker")
    resource = telemetry_resource(settings)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint,
                insecure=settings.otel_exporter_otlp_endpoint.startswith("http://"),
            )
        )
    )
    trace.set_tracer_provider(provider)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=settings.otel_exporter_otlp_endpoint,
                        insecure=settings.otel_exporter_otlp_endpoint.startswith("http://"),
                    ),
                    export_interval_millis=settings.otel_metric_export_interval_ms,
                )
            ],
        )
    )
    SQLAlchemyInstrumentor().instrument(engine=engine)
    HTTPXClientInstrumentor().instrument(request_hook=sanitize_httpx_span)
    return trace.get_tracer("graphview.worker"), metrics.get_meter("graphview.worker")


def telemetry_resource(settings) -> Resource:
    return Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "1.0.0",
            "deployment.environment.name": settings.environment,
        }
    )
