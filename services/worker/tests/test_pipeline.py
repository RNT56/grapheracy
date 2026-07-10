import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from arq import Retry
from sqlalchemy import update

from graphview_api import db
from graphview_api.action_adapters import ActionAdapterResult
from graphview_api.db import create_app_engine
from graphview_api.jobs.executor import GraphJobExecutor
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository
from graphview_api.schemas import ActionProposalCreate, ActionProposalDecision
from graphview_api.settings import Settings
from graphview_worker.jobs import DurableJobCancelled, _execute_with_cancellation, execute_durable_job
from graphview_worker.pipeline import WorkerSettingsForArq, build_stage_plan


def test_stage_plan_is_idempotent_and_ordered() -> None:
    stages = build_stage_plan()

    assert [stage.name for stage in stages] == [
        "connector.fetch",
        "source.extract",
        "chunk.normalize",
        "hierarchy.build",
        "entity.resolve",
        "relation.propose",
        "content.embed",
        "proposal.generate",
        "autocommit.evaluate",
        "review.commit",
        "agent.plan",
        "agent.retrieve",
        "agent.reason",
        "agent.research.fetch",
        "agent.propose",
        "agent.action.await_review",
        "agent.action.apply",
        "agent_context.normalize",
        "agent_context.enrich",
        "agent_context.retention",
    ]
    assert all(stage.idempotency_key for stage in stages)
    assert {function.__name__ for function in WorkerSettingsForArq.functions} >= {
        "execute_durable_job",
        "dispatch_outbox",
        "enqueue_scheduled_connector_syncs",
        "run_context_retention",
    }
    assert WorkerSettingsForArq.cron_jobs


def test_running_worker_task_is_cooperatively_cancelled() -> None:
    repository = GraphRepository(create_app_engine("sqlite://"))
    repository.initialize()
    jobs = JobRepository(repository.engine)
    job = jobs.enqueue(
        JobCreate(
            kind="ai.agent",
            queue="agents",
            idempotency_key="worker-cancellation-test",
            payload={"project_id": "project-default"},
        )
    )
    claimed = jobs.claim(job["id"], worker_id="worker-test")
    started = asyncio.Event()
    interrupted = asyncio.Event()

    class SlowExecutor:
        async def execute(self, _job):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                interrupted.set()

    async def scenario() -> None:
        task = asyncio.create_task(_execute_with_cancellation({"jobs": jobs, "executor": SlowExecutor()}, claimed))
        await started.wait()
        assert jobs.cancel(job["id"])["status"] == "cancelling"
        with pytest.raises(DurableJobCancelled):
            await task
        assert interrupted.is_set()
        assert jobs.finish_cancellation(job["id"])["status"] == "cancelled"

    asyncio.run(scenario())


def test_external_action_retry_reuses_visible_run_and_finishes_with_receipt() -> None:
    repository = GraphRepository(create_app_engine("sqlite://"))
    repository.initialize()
    proposal = repository.create_action_proposal(
        ActionProposalCreate(
            action_type="trigger_workflow",
            title="Trigger reviewed workflow",
            summary="Send a signed reviewed event.",
            payload={"credential_ref": "workflow-secret", "destination": "https://hooks.example.test/run"},
        ),
        "reviewer",
    )
    repository.decide_action_proposal(
        proposal["id"],
        "approved",
        ActionProposalDecision(rationale="Reviewed external side effect"),
        "reviewer",
    )
    jobs = JobRepository(repository.engine)
    job = jobs.enqueue(
        JobCreate(
            kind="action.run",
            queue="actions",
            idempotency_key=f"action-run:{proposal['id']}",
            payload={
                "project_id": "project-default",
                "action_proposal_id": proposal["id"],
                "actor_id": "reviewer",
            },
            max_attempts=2,
        )
    )

    class Adapter:
        should_fail = True

        async def execute(self, _proposal, _payload):
            if self.should_fail:
                raise RuntimeError("provider timeout secret=must-not-leak")
            return ActionAdapterResult("receipt-1", {"status_code": 202})

    class NullSpan:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def record_exception(self, _error):
            return None

    class NullTracer:
        def start_as_current_span(self, *_args, **_kwargs):
            return NullSpan()

    class NullMetric:
        def record(self, *_args, **_kwargs):
            return None

        def add(self, *_args, **_kwargs):
            return None

    adapter = Adapter()
    context = {
        "jobs": jobs,
        "repository": repository,
        "executor": GraphJobExecutor(repository, Settings(), action_executor=adapter),
        "worker_id": "action-worker",
        "tracer": NullTracer(),
        "queue_latency": NullMetric(),
        "job_counter": NullMetric(),
    }

    with pytest.raises(Retry):
        asyncio.run(execute_durable_job(context, job["id"]))
    queued_run = repository.list_action_runs()[0]
    assert queued_run["status"] == "queued"
    assert queued_run["error_code"] == "RuntimeError"
    assert "must-not-leak" not in queued_run["error"]
    assert repository.get_action_proposal(proposal["id"])["status"] == "queued"

    with repository.engine.begin() as conn:
        conn.execute(
            update(db.durable_jobs)
            .where(db.durable_jobs.c.id == job["id"])
            .values(available_at=datetime.now(tz=UTC) - timedelta(seconds=1))
        )
    adapter.should_fail = False
    completed = asyncio.run(execute_durable_job(context, job["id"]))

    assert completed["status"] == "succeeded"
    runs = repository.list_action_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == queued_run["id"]
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["external_id"] == "receipt-1"
    assert repository.get_action_proposal(proposal["id"])["status"] == "succeeded"
    event_types = {
        event["event_type"]
        for event in repository.list_graph_activity_events(graph_id=None, limit=100)
    }
    assert {"action.run.started", "action.run.retry_scheduled", "action.run.resumed", "action.run.succeeded"} <= event_types
