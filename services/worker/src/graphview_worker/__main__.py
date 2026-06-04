from graphview_worker.pipeline import build_stage_plan


def main() -> None:
    stages = build_stage_plan()
    print("graphview-worker ready")
    for stage in stages:
        print(f"- {stage.name}: {stage.idempotency_key}")


if __name__ == "__main__":
    main()
