import sys

from arq import run_worker

from graphview_worker.pipeline import WorkerSettingsForArq, build_stage_plan


def main() -> None:
    if "--describe" not in sys.argv:
        run_worker(WorkerSettingsForArq)
        return
    stages = build_stage_plan()
    print("graphview-worker stage plan")
    for stage in stages:
        print(f"- {stage.name}: {stage.idempotency_key}")


if __name__ == "__main__":
    main()
