import asyncio
from contextlib import nullcontext

import httpx
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState

from graphview_api import db
from graphview_api.db import create_app_engine
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.observability import (
    TelemetryRuntime,
    current_trace_id,
    observe_sse_stream,
    sanitize_httpx_span,
    sanitize_server_span,
    sanitized_outbound_url,
)


class RecordingMetric:
    def __init__(self):
        self.values = []

    def add(self, value, attributes=None):
        self.values.append((value, attributes or {}))

    def record(self, value, attributes=None):
        self.values.append((value, attributes or {}))


class RecordingSpan:
    def __init__(self):
        self.attributes = {}

    def is_recording(self):
        return True

    def set_attribute(self, name, value):
        self.attributes[name] = value


class RecordingTracer:
    def __init__(self):
        self.span = RecordingSpan()

    def start_as_current_span(self, *_args, **_kwargs):
        return nullcontext(self.span)


def runtime():
    metric = RecordingMetric()
    return TelemetryRuntime(
        tracer=RecordingTracer(),
        request_counter=RecordingMetric(),
        request_duration=RecordingMetric(),
        sse_connections=RecordingMetric(),
        sse_events=RecordingMetric(),
        sse_duration=metric,
    )


def test_outbound_trace_url_drops_query_and_fragment() -> None:
    url = httpx.URL("https://api.example.test/v1/items?access_token=secret&query=private#fragment")
    assert sanitized_outbound_url(url) == "https://api.example.test/v1/items"

    span = RecordingSpan()
    request_info = type("RequestInfo", (), {"url": url})()
    sanitize_httpx_span(span, request_info)
    assert span.attributes["url.full"] == "https://api.example.test/v1/items"
    assert span.attributes["http.url"] == "https://api.example.test/v1/items"
    assert span.attributes["http.target"] == "/v1/items"
    assert "secret" not in str(span.attributes)
    assert "private" not in str(span.attributes)


def test_server_trace_query_is_redacted() -> None:
    span = RecordingSpan()
    sanitize_server_span(
        span,
        {"method": "GET", "path": "/api/v1/graphs/project-default/search", "query_string": b"q=private"},
    )
    assert span.attributes == {
        "graphview.request.method": "GET",
        "url.path": "/api/v1/graphs/project-default/search",
        "url.full": "http://graphview.invalid/api/v1/graphs/project-default/search",
        "http.url": "http://graphview.invalid/api/v1/graphs/project-default/search",
        "http.target": "/api/v1/graphs/project-default/search",
        "url.query": "<redacted>",
    }


def test_sse_runtime_records_connections_events_and_duration() -> None:
    telemetry = runtime()

    async def source():
        yield ": heartbeat\n\n"
        yield "id: 1\nevent: graph.activity\ndata: {}\n\n"

    async def collect():
        return [item async for item in observe_sse_stream(source(), telemetry, stream_kind="graph.activity")]

    assert asyncio.run(collect()) == [": heartbeat\n\n", "id: 1\nevent: graph.activity\ndata: {}\n\n"]
    assert [value for value, _ in telemetry.sse_connections.values] == [1, -1]
    assert [value for value, _ in telemetry.sse_events.values] == [1]
    assert len(telemetry.sse_duration.values) == 1
    assert telemetry.tracer.span.attributes["graphview.sse.events"] == 1


def test_durable_job_captures_w3c_trace_context() -> None:
    engine = create_app_engine("sqlite://")
    db.metadata.create_all(engine)
    jobs = JobRepository(engine)
    span_context = SpanContext(
        trace_id=int("1234567890abcdef1234567890abcdef", 16),
        span_id=int("1234567890abcdef", 16),
        is_remote=False,
        trace_flags=TraceFlags.SAMPLED,
        trace_state=TraceState(),
    )
    with trace.use_span(NonRecordingSpan(span_context)):
        assert current_trace_id() == "1234567890abcdef1234567890abcdef"
        job = jobs.enqueue(
            JobCreate(
                kind="ingestion.run",
                queue="ingestion",
                idempotency_key="otel-trace-job",
                payload={"project_id": "project-default"},
            )
        )

    assert job["trace_id"] == "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
