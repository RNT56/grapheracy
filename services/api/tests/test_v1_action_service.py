from graphview_api.api_v1.action_service import V1ActionService
from graphview_api.schemas import OutcomeCreate


class SecretStore:
    def get(self, reference: str):
        assert reference == "secret://callback"
        return {"callback_secret": "signed-secret"}


class RecordingLegacy:
    secret_store = SecretStore()

    def get_action_proposal(self, proposal_id: str):
        return {"id": proposal_id, "project_id": "project-1", "status": "approved"}

    def get_action_run(self, action_run_id: str):
        return {"id": action_run_id, "project_id": "project-1", "action_proposal_id": "proposal-1"}

    def action_proposal_execution_bundle(self, *_args, **_kwargs):
        return {"action_type": "trigger_workflow"}, {"credential_ref": "secret://callback"}


class RecordingJobs:
    def __init__(self) -> None:
        self.calls = []

    def enqueue(self, payload, *, project_id: str):
        self.calls.append((payload.kind, payload.idempotency_key, project_id))
        return {"id": "job-1", "kind": payload.kind}


def test_v1_action_service_resolves_callback_secret_and_idempotent_run() -> None:
    jobs = RecordingJobs()
    service = V1ActionService(RecordingLegacy(), jobs)
    proposal = service.proposal("proposal-1")
    action_run = service.action_run("run-1")

    assert service.enqueue_run(proposal, actor_id="user-1")["kind"] == "action.run"
    assert service.callback_secret(action_run) == "signed-secret"
    assert jobs.calls == [("action.run", "action-run:proposal-1", "project-1")]


def test_v1_action_service_enqueues_outcome_by_callback_event_identity() -> None:
    jobs = RecordingJobs()
    service = V1ActionService(RecordingLegacy(), jobs)
    action_run = service.action_run("run-1")
    outcome = OutcomeCreate(status="succeeded", title="Workflow completed", summary="Workflow completed")

    result = service.enqueue_outcome(action_run, "run-1", "event-1", outcome)

    assert result["kind"] == "outcome.record"
    assert jobs.calls == [("outcome.record", "action-outcome:run-1:event-1", "project-1")]
