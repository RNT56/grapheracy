import pytest

from graphview_api.actions.service import ActionsService
from graphview_api.schemas import ActionProposalDecision, ActionRunCreate, OutcomeCreate


class RecordingActionsRepository:
    def __init__(self) -> None:
        self.proposal_value = {"id": "action-1", "status": "approved"}

    def list_decision_records(self, *, limit=50):
        return [{"id": "decision-1"}]

    def create_decision_record(self, payload, actor_id):
        return {"id": "decision-1", "actor_id": actor_id}

    def list_action_proposals(self, *, status=None, limit=50):
        return [{"id": "action-1", "status": status}]

    def create_action_proposal(self, payload, actor_id):
        return {"id": "action-1", "action_type": payload.action_type, "actor_id": actor_id}

    def decide_action_proposal(self, action_proposal_id, decision, payload, actor_id):
        if self.proposal_value is None:
            return None
        return {**self.proposal_value, "decision": decision, "actor_id": actor_id, "rationale": payload.rationale}

    def list_action_runs(self, *, status=None, limit=50):
        return [{"id": "run-1", "status": status}]

    def create_action_run(self, payload, actor_id):
        return {"id": "run-1", "action_proposal_id": payload.action_proposal_id, "actor_id": actor_id}

    def list_outcomes(self, *, status=None, limit=50):
        return [{"id": "outcome-1", "status": status}]

    def create_outcome(self, payload, actor_id, *, action_run_id=None):
        return {"id": "outcome-1", "action_run_id": action_run_id, "status": payload.status, "actor_id": actor_id}

    def create_feedback_event(self, payload, actor_id):
        return {"id": "feedback-1", "actor_id": actor_id}

    def list_feedback_events(self, *, kind=None, limit=50):
        return [{"id": "feedback-1", "kind": kind}]


def test_actions_service_preserves_reviewer_decision_authority() -> None:
    result = ActionsService(RecordingActionsRepository()).decide_proposal(
        "action-1",
        "approved",
        ActionProposalDecision(rationale="Reviewed evidence"),
        actor_id="reviewer-1",
    )

    assert result["decision"] == "approved"
    assert result["actor_id"] == "reviewer-1"


def test_actions_service_exposes_missing_proposal_as_domain_error() -> None:
    repository = RecordingActionsRepository()
    repository.proposal_value = None

    with pytest.raises(KeyError):
        ActionsService(repository).decide_proposal(
            "missing",
            "rejected",
            ActionProposalDecision(),
            actor_id="reviewer-1",
        )


def test_actions_service_preserves_run_to_outcome_linkage() -> None:
    service = ActionsService(RecordingActionsRepository())
    run = service.create_run(ActionRunCreate(action_proposal_id="action-1"), actor_id="worker-1")
    outcome = service.create_outcome(
        run["id"],
        OutcomeCreate(status="succeeded", title="Delivered", summary="External action completed."),
        actor_id="worker-1",
    )

    assert outcome["action_run_id"] == "run-1"
    assert outcome["status"] == "succeeded"
