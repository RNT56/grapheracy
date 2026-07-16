import pytest

from graphview_api.api_v1.job_service import JobService
from graphview_api.jobs.schemas import JobCreate


class RecordingJobs:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def enqueue(self, payload, *, project_id: str):
        self.calls.append(("enqueue", payload.kind, payload.idempotency_key, project_id))
        return {"id": "job-1", "project_id": project_id, "kind": payload.kind}

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return [{"id": "job-1", "project_id": kwargs["project_id"]}]

    def get(self, job_id: str, *, project_id: str | None = None):
        self.calls.append(("get", job_id, project_id))
        return {"id": job_id, "project_id": project_id or "project-default"}

    def cancel(self, job_id: str, *, project_id: str):
        self.calls.append(("cancel", job_id, project_id))
        return {"id": job_id, "status": "cancelled"}

    def retry(self, job_id: str, *, project_id: str):
        self.calls.append(("retry", job_id, project_id))
        return {"id": job_id, "status": "queued"}


class RecordingLegacy:
    def get_planning_session(self, session_id: str):
        return None if session_id == "missing" else {"project_id": "project-1"}


def test_v1_job_service_validates_public_job_kind_and_queue_before_enqueue() -> None:
    jobs = RecordingJobs()
    service = JobService(jobs, RecordingLegacy())
    accepted = JobCreate(kind="ai.query", queue="agents", idempotency_key="query-1", payload={"project_id": "project-1"})
    rejected = accepted.model_copy(update={"queue": "actions"})

    assert service.project_for_create(accepted) == "project-1"
    assert service.create(accepted, project_id="project-1")["id"] == "job-1"
    with pytest.raises(ValueError, match="Unsupported durable job"):
        service.project_for_create(rejected)
    assert jobs.calls == [("enqueue", "ai.query", "query-1", "project-1")]


def test_v1_job_service_owns_project_scoped_lifecycle_and_planning_resolution() -> None:
    jobs = RecordingJobs()
    service = JobService(jobs, RecordingLegacy())

    assert service.planning_project_id("session-1") == "project-1"
    assert service.planning_project_id("missing") is None
    assert service.list(project_id="project-1", status="failed", cursor="job-0", limit=10)[0]["id"] == "job-1"
    assert service.get("job-1", project_id="project-1")["project_id"] == "project-1"
    assert service.cancel("job-1", project_id="project-1")["status"] == "cancelled"
    assert service.retry("job-1", project_id="project-1")["status"] == "queued"
