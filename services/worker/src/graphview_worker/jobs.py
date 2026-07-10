from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta

from arq import Retry
import httpx

from graphview_api.db import create_app_engine
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository
from graphview_api.settings import Settings
from graphview_api.secret_store import build_secret_store
from graphview_api.object_store import build_object_store
from graphview_api.observability import configure_worker_telemetry
from graphview_api.action_adapters import ActionExecutor


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
    return dispatched


async def execute_durable_job(ctx: dict, job_id: str) -> dict:
    jobs: JobRepository = ctx["jobs"]
    claimed = jobs.claim(job_id, worker_id=ctx["worker_id"])
    if claimed is None:
        current = jobs.get(job_id)
        return current or {"id": job_id, "status": "missing"}
    attributes = {"graphview.job.kind": claimed["kind"], "graphview.job.queue": claimed["queue"]}
    created_at = claimed["created_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    ctx["queue_latency"].record(max(0.0, (datetime.now(tz=UTC) - created_at).total_seconds()), attributes)
    with ctx["tracer"].start_as_current_span("graphview.job.execute", attributes=attributes) as span:
        try:
            result = await ctx["executor"].execute(claimed)
        except Exception as error:
            span.record_exception(error)
            retry_delay = 30
            if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
                try:
                    retry_delay = min(3600, max(1, int(error.response.headers.get("Retry-After", "30"))))
                except ValueError:
                    retry_delay = 30
            failed = jobs.fail(job_id, error_code=type(error).__name__, error=str(error), retry_delay_seconds=retry_delay)
            ctx["job_counter"].add(1, {**attributes, "graphview.job.status": failed["status"]})
            if failed["status"] == "retry":
                raise Retry(defer=retry_delay) from error
            return failed
        completed = jobs.complete(job_id, result)
        ctx["job_counter"].add(1, {**attributes, "graphview.job.status": "succeeded"})
        return completed


async def run_context_retention(ctx: dict) -> dict:
    return ctx["repository"].run_agent_context_retention()


async def enqueue_scheduled_connector_syncs(ctx: dict) -> int:
    repository: GraphRepository = ctx["repository"]
    jobs: JobRepository = ctx["jobs"]
    timestamp = datetime.now(tz=UTC)
    enqueued = 0
    for target in repository.list_connector_targets():
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
        enqueued += 1
    return enqueued


async def worker_health(ctx: dict) -> dict:
    return {"status": "ok", "worker_id": ctx["worker_id"]}
