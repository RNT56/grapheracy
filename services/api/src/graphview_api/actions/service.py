from __future__ import annotations

from graphview_api.actions.repository import ActionsRepositoryPort
from graphview_api.schemas import (
    ActionProposalCreate,
    ActionProposalDecision,
    ActionRunCreate,
    DecisionRecordCreate,
    FeedbackEventCreate,
    OutcomeCreate,
)


class ActionsService:
    def __init__(self, repository: ActionsRepositoryPort) -> None:
        self.repository = repository

    def decisions(self, *, limit: int) -> dict[str, list[dict]]:
        return {"decision_records": self.repository.list_decision_records(limit=limit)}

    def create_decision(self, payload: DecisionRecordCreate, *, actor_id: str) -> dict:
        return self.repository.create_decision_record(payload, actor_id)

    def proposals(self, *, status_filter: str | None, limit: int) -> dict[str, list[dict]]:
        return {"action_proposals": self.repository.list_action_proposals(status=status_filter, limit=limit)}

    def create_proposal(self, payload: ActionProposalCreate, *, actor_id: str) -> dict:
        return self.repository.create_action_proposal(payload, actor_id)

    def decide_proposal(
        self,
        action_proposal_id: str,
        decision: str,
        payload: ActionProposalDecision,
        *,
        actor_id: str,
    ) -> dict:
        value = self.repository.decide_action_proposal(action_proposal_id, decision, payload, actor_id)
        if value is None:
            raise KeyError(action_proposal_id)
        return value

    def runs(self, *, status_filter: str | None, limit: int) -> dict[str, list[dict]]:
        return {"action_runs": self.repository.list_action_runs(status=status_filter, limit=limit)}

    def create_run(self, payload: ActionRunCreate, *, actor_id: str) -> dict:
        return self.repository.create_action_run(payload, actor_id)

    def outcomes(self, *, status_filter: str | None, limit: int) -> dict[str, list[dict]]:
        return {"outcomes": self.repository.list_outcomes(status=status_filter, limit=limit)}

    def create_outcome(self, action_run_id: str, payload: OutcomeCreate, *, actor_id: str) -> dict:
        return self.repository.create_outcome(payload, actor_id, action_run_id=action_run_id)

    def create_feedback(self, payload: FeedbackEventCreate, *, actor_id: str) -> dict:
        return self.repository.create_feedback_event(payload, actor_id)

    def feedback(self, *, kind: str | None, limit: int) -> dict[str, list[dict]]:
        return {"feedback_events": self.repository.list_feedback_events(kind=kind, limit=limit)}
