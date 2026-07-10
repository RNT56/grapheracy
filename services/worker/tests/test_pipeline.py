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
