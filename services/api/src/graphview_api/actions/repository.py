from __future__ import annotations

from typing import Protocol

from graphview_api.schemas import (
    ActionCredentialKind,
    ActionCredentialOut,
    ActionProposalCreate,
    ActionProposalDecision,
    ActionRunCreate,
    DecisionRecordCreate,
    FeedbackEventCreate,
    OutcomeCreate,
)


class ActionsRepositoryPort(Protocol):
    def list_action_credentials(self) -> list[ActionCredentialOut]: ...

    def upsert_action_credential(self, kind: ActionCredentialKind, credentials: dict) -> ActionCredentialOut: ...

    def delete_action_credential(self, kind: ActionCredentialKind) -> ActionCredentialOut: ...

    def list_decision_records(self, *, limit: int = 50) -> list[dict]: ...

    def create_decision_record(self, payload: DecisionRecordCreate, actor_id: str) -> dict: ...

    def list_action_proposals(self, *, status: str | None = None, limit: int = 50) -> list[dict]: ...

    def create_action_proposal(self, payload: ActionProposalCreate, actor_id: str) -> dict: ...

    def decide_action_proposal(
        self,
        action_proposal_id: str,
        decision: str,
        payload: ActionProposalDecision,
        actor_id: str,
    ) -> dict | None: ...

    def list_action_runs(self, *, status: str | None = None, limit: int = 50) -> list[dict]: ...

    def create_action_run(self, payload: ActionRunCreate, actor_id: str) -> dict: ...

    def list_outcomes(self, *, status: str | None = None, limit: int = 50) -> list[dict]: ...

    def create_outcome(self, payload: OutcomeCreate, actor_id: str, *, action_run_id: str | None = None) -> dict: ...

    def create_feedback_event(self, payload: FeedbackEventCreate, actor_id: str) -> dict: ...

    def list_feedback_events(self, *, kind: str | None = None, limit: int = 50) -> list[dict]: ...
