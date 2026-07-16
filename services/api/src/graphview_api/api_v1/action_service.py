from __future__ import annotations

from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository
from graphview_api.schemas import OutcomeCreate


class V1ActionService:
    def __init__(self, legacy: GraphRepository, jobs: JobRepository):
        self.legacy = legacy
        self.jobs = jobs

    def proposal(self, proposal_id: str) -> dict | None:
        return self.legacy.get_action_proposal(proposal_id)

    def enqueue_run(self, proposal: dict, *, actor_id: str) -> dict:
        return self.jobs.enqueue(
            JobCreate(
                kind="action.run",
                queue="actions",
                idempotency_key=f"action-run:{proposal['id']}",
                payload={"project_id": proposal["project_id"], "action_proposal_id": proposal["id"], "actor_id": actor_id},
            ),
            project_id=proposal["project_id"],
        )

    def action_run(self, action_run_id: str) -> dict | None:
        return self.legacy.get_action_run(action_run_id)

    def callback_secret(self, action_run: dict) -> str | None:
        bundle = self.legacy.action_proposal_execution_bundle(
            action_run["action_proposal_id"],
            project_id=action_run["project_id"],
        )
        if bundle is None or bundle[0]["action_type"] != "trigger_workflow":
            raise ValueError("Action run does not accept workflow callbacks")
        _, action_payload = bundle
        credential_ref = str(action_payload.get("credential_ref") or "")
        if not credential_ref or self.legacy.secret_store is None:
            return None
        credential = self.legacy.secret_store.get(credential_ref)
        return str(credential.get("callback_secret") or credential.get("secret") or "") or None

    def enqueue_outcome(
        self,
        action_run: dict,
        action_run_id: str,
        event_id: str,
        outcome: OutcomeCreate,
    ) -> dict:
        return self.jobs.enqueue(
            JobCreate(
                kind="outcome.record",
                queue="outcomes",
                idempotency_key=f"action-outcome:{action_run_id}:{event_id}",
                payload={
                    "project_id": action_run["project_id"],
                    "action_run_id": action_run_id,
                    "actor_id": "workflow-callback",
                    "outcome": outcome.model_dump(mode="json"),
                    "callback_event_id": event_id,
                },
            ),
            project_id=action_run["project_id"],
        )
