from __future__ import annotations

import asyncio
from contextlib import suppress
import socket
from datetime import UTC, datetime, timedelta
from time import perf_counter

from arq import Retry
import httpx
from opentelemetry.trace import Status, StatusCode

from graphview_api.db import create_app_engine
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository
from graphview_api.redaction import redact_sensitive_text
from graphview_api.settings import Settings
from graphview_api.secret_store import build_secret_store
from graphview_api.object_store import build_object_store
from graphview_api.observability import configure_worker_telemetry, extract_trace_context
from graphview_api.action_adapters import ActionExecutor
from graphview_api.connector_state import ConnectorStateRepository


class DurableJobCancelled(Exception):
    pass


def _transition_external_action(ctx: dict, job: dict, *, status: str, error_code: str, error: str) -> None:
    if job.get("kind") != "action.run":
        return
    payload = job.get("payload") or {}
    action_proposal_id = payload.get("action_proposal_id")
    if not action_proposal_id:
        return
    ctx["repository"].transition_external_action_run(
        str(action_proposal_id),
        status=status,
        actor_id=str(payload.get("actor_id") or "system-worker"),
        error_code=error_code,
        error=error,
    )


async def _execute_with_cancellation(ctx: dict, claimed: dict) -> dict:
    jobs: JobRepository = ctx["jobs"]
    task = asyncio.create_task(ctx["executor"].execute(claimed))
    while True:
        done, _ = await asyncio.wait({task}, timeout=0.25)
        if task in done:
            return task.result()
        if jobs.cancellation_requested(claimed["id"]):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise DurableJobCancelled


async def startup(ctx: dict) -> None:
    settings = Settings()
    secret_store = build_secret_store(settings)
    object_store = build_object_store(settings)
    repository = GraphRepository(
        create_app_engine(settings.database_url),
        secret_key=settings.secret_key,
        auto_commit_threshold=settings.auto_commit_threshold,
        safe_action_types=settings.safe_action_types,
        agent_context_max_blob_bytes=settings.agent_context_max_blob_bytes,
        agent_context_retention_days=settings.agent_context_retention_days,
        secret_store=secret_store,
        object_store=object_store,
    )
    is_development = settings.environment in {"local", "test", "development"}
    repository.initialize(create_schema=is_development)
    ctx["settings"] = settings
    ctx["repository"] = repository
    ctx["jobs"] = JobRepository(repository.engine)
    ctx["executor"] = GraphJobExecutor(
        repository,
        settings,
        object_store=object_store,
        action_executor=ActionExecutor(settings, secret_store=secret_store),
    )
    ctx["worker_id"] = f"{socket.gethostname()}:{id(ctx)}"
    ctx["tracer"], meter = configure_worker_telemetry(settings, repository.engine)
    ctx["job_counter"] = meter.create_counter("graphview.worker.jobs")
    ctx["queue_latency"] = meter.create_histogram("graphview.worker.queue_latency", unit="s")
    ctx["execution_duration"] = meter.create_histogram("graphview.worker.job.duration", unit="s")
    ctx["active_jobs"] = meter.create_up_down_counter("graphview.worker.active_jobs", unit="{job}")
    ctx["outbox_counter"] = meter.create_counter("graphview.worker.outbox.dispatched", unit="{event}")


async def shutdown(ctx: dict) -> None:
    repository = ctx.get("repository")
    if repository is not None:
        repository.engine.dispose()


async def dispatch_outbox(ctx: dict) -> int:
    jobs: JobRepository = ctx["jobs"]
    dispatched = 0
    with ctx["tracer"].start_as_current_span("graphview.outbox.dispatch") as span:
        for event in jobs.pending_outbox(limit=100):
            job_id = str(event["payload"].get("job_id") or event["aggregate_id"])
            await ctx["redis"].enqueue_job("execute_durable_job", job_id, _job_id=job_id)
            jobs.mark_outbox_published(event["id"])
            dispatched += 1
        span.set_attribute("graphview.outbox.dispatched", dispatched)
        ctx["outbox_counter"].add(dispatched)
    return dispatched


async def execute_durable_job(ctx: dict, job_id: str) -> dict:
    jobs: JobRepository = ctx["jobs"]
    claimed = jobs.claim(job_id, worker_id=ctx["worker_id"])
    if claimed is None:
        current = jobs.get(job_id)
        if current and current.get("status") == "failed" and current.get("error_code") == "WorkerLeaseExpired":
            _transition_external_action(
                ctx,
                current,
                status="failed",
                error_code="WorkerLeaseExpired",
                error=str(current.get("error") or "Worker lease expired"),
            )
        return current or {"id": job_id, "status": "missing"}
    attributes = {
        "graphview.job.kind": claimed["kind"],
        "graphview.job.queue": claimed["queue"],
        "graphview.project.id": claimed["project_id"],
        "graphview.job.attempt": claimed["attempt"],
    }
    metric_attributes = {
        "graphview.job.kind": claimed["kind"],
        "graphview.job.queue": claimed["queue"],
    }
    created_at = claimed["created_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    ctx["queue_latency"].record(max(0.0, (datetime.now(tz=UTC) - created_at).total_seconds()), metric_attributes)
    started = perf_counter()
    ctx["active_jobs"].add(1, metric_attributes)
    parent_context = extract_trace_context(claimed.get("trace_id"))
    try:
        with ctx["tracer"].start_as_current_span(
            "graphview.job.execute",
            context=parent_context,
            attributes=attributes,
        ) as span:
            try:
                result = await _execute_with_cancellation(ctx, claimed)
            except DurableJobCancelled:
                span.set_attribute("graphview.job.status", "cancelled")
                _transition_external_action(
                    ctx,
                    claimed,
                    status="cancelled",
                    error_code="CancelledByUser",
                    error="External action execution was cancelled by user request",
                )
                cancelled = jobs.finish_cancellation(job_id)
                ctx["job_counter"].add(1, {**metric_attributes, "graphview.job.status": "cancelled"})
                return cancelled
            except Exception as error:
                span.record_exception(RuntimeError(redact_sensitive_text(error)))
                retry_delay = 30
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
                    try:
                        retry_delay = min(3600, max(1, int(error.response.headers.get("Retry-After", "30"))))
                    except ValueError:
                        retry_delay = 30
                failed = jobs.fail(
                    job_id,
                    error_code=type(error).__name__,
                    error=str(error),
                    retry_delay_seconds=retry_delay,
                )
                action_status = "queued" if failed["status"] == "retry" else (
                    "cancelled" if failed["status"] == "cancelled" else "failed"
                )
                _transition_external_action(
                    ctx,
                    claimed,
                    status=action_status,
                    error_code=type(error).__name__,
                    error=str(error),
                )
                span.set_attribute("graphview.job.status", failed["status"])
                span.set_status(Status(StatusCode.ERROR, type(error).__name__))
                ctx["job_counter"].add(1, {**metric_attributes, "graphview.job.status": failed["status"]})
                if failed["status"] == "retry":
                    raise Retry(defer=retry_delay) from error
                return failed
            completed = jobs.complete(job_id, result)
            span.set_attribute("graphview.job.status", completed["status"])
            ctx["job_counter"].add(1, {**metric_attributes, "graphview.job.status": completed["status"]})
            return completed
    finally:
        ctx["active_jobs"].add(-1, metric_attributes)
        ctx["execution_duration"].record(max(0.0, perf_counter() - started), metric_attributes)


async def run_context_retention(ctx: dict) -> dict:
    return ctx["repository"].run_agent_context_retention()


async def enqueue_scheduled_connector_syncs(ctx: dict) -> int:
    repository: GraphRepository = ctx["repository"]
    jobs: JobRepository = ctx["jobs"]
    timestamp = datetime.now(tz=UTC)
    enqueued = 0
    for target in repository.list_connector_targets(project_id=None):
        settings = target.get("sync_settings", {})
        interval_minutes = int(settings.get("interval_minutes") or 0)
        if interval_minutes <= 0 or settings.get("schedule_enabled", True) is False:
            continue
        last_synced_at = target.get("last_synced_at")
        if isinstance(last_synced_at, str):
            last_synced_at = datetime.fromisoformat(last_synced_at.replace("Z", "+00:00"))
        if last_synced_at and last_synced_at.tzinfo is None:
            last_synced_at = last_synced_at.replace(tzinfo=UTC)
        if last_synced_at and last_synced_at + timedelta(minutes=interval_minutes) > timestamp:
            continue
        bucket = int(timestamp.timestamp() // (interval_minutes * 60))
        jobs.enqueue(
            JobCreate(
                kind="connector.sync",
                queue="connectors",
                idempotency_key=f"connector-schedule:{target['id']}:{bucket}",
                payload={"project_id": target["project_id"], "target_id": target["id"], "actor_id": "system-scheduler"},
            ),
            project_id=target["project_id"],
        )
        ConnectorStateRepository(repository.engine).mark_queued(
            target["id"],
            next_scheduled_at=timestamp + timedelta(minutes=interval_minutes),
        )
        enqueued += 1
    return enqueued


async def worker_health(ctx: dict) -> dict:
    return {"status": "ok", "worker_id": ctx["worker_id"]}
