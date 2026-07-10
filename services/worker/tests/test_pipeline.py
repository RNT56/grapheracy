import asyncio

import pytest

from graphview_api.db import create_app_engine
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository
from graphview_worker.jobs import DurableJobCancelled, _execute_with_cancellation
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
