from graphview_worker.pipeline import build_stage_plan


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
    ]
    assert all(stage.idempotency_key for stage in stages)
