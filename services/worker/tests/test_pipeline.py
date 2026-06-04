from graphview_worker.pipeline import build_stage_plan


def test_stage_plan_is_idempotent_and_ordered() -> None:
    stages = build_stage_plan()

    assert [stage.name for stage in stages] == [
        "source.fetch",
        "source.extract",
        "content.analyze",
        "content.embed",
        "proposal.generate",
        "review.commit",
    ]
    assert all(stage.idempotency_key for stage in stages)
