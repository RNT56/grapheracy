from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from opentelemetry import metrics, trace
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


def configure_telemetry(app, engine, settings) -> None:
    if not settings.otel_exporter_otlp_endpoint:
        return
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
                    )
                )
            ],
        )
    )

    def server_request_hook(span, scope) -> None:
        if span and span.is_recording():
            span.set_attribute("graphview.request.path", scope.get("path", ""))
            span.set_attribute("graphview.request.method", scope.get("method", ""))

    FastAPIInstrumentor.instrument_app(app, server_request_hook=server_request_hook, excluded_urls="health,observability/ready")
    SQLAlchemyInstrumentor().instrument(engine=engine)
    HTTPXClientInstrumentor().instrument()


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
                    )
                )
            ],
        )
    )
    SQLAlchemyInstrumentor().instrument(engine=engine)
    HTTPXClientInstrumentor().instrument()
    return trace.get_tracer("graphview.worker"), metrics.get_meter("graphview.worker")


def telemetry_resource(settings) -> Resource:
    return Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "1.0.0",
            "deployment.environment.name": settings.environment,
        }
    )
