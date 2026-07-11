from __future__ import annotations

import hashlib
import json

from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate
from graphview_api.repository import GraphRepository
from graphview_api.schemas import AgentRunCreate, GraphQueryCreate, GraphResearchCreate, IngestionCreate, PlanningMessageCreate

SUPPORTED_DURABLE_JOBS = {
    "ingestion.run": "ingestion",
    "upload.ingest": "ingestion",
    "connector.sync": "connectors",
    "action.run": "actions",
    "outcome.record": "outcomes",
    "agent_context.retention": "maintenance",
    "ai.planning": "agents",
    "ai.query": "agents",
    "ai.research": "agents",
    "ai.agent": "agents",
}


class JobService:
    def __init__(self, jobs: JobRepository, legacy: GraphRepository):
        self.jobs = jobs
        self.legacy = legacy

    @staticmethod
    def project_id(graph_id: str | None) -> str:
        return (graph_id or "project-default").split(":", 1)[0]

    def project_for_create(self, payload: JobCreate) -> str:
        expected_queue = SUPPORTED_DURABLE_JOBS.get(payload.kind)
        if expected_queue is None or payload.queue != expected_queue:
            raise ValueError("Unsupported durable job kind or queue")
        return str(payload.payload.get("project_id") or "project-default")

    def create(self, payload: JobCreate, *, project_id: str) -> dict:
        return self.jobs.enqueue(payload, project_id=project_id)

    def enqueue_ingestion(self, payload: IngestionCreate, graph_id: str | None, *, actor_id: str) -> dict:
        project_id = self.project_id(graph_id)
        body = payload.model_dump(mode="json")
        digest = self._digest(body)
        return self.jobs.enqueue(
            JobCreate(
                kind="ingestion.run",
                queue="ingestion",
                idempotency_key=f"ingestion:{project_id}:{digest}",
                payload={"project_id": project_id, "graph_id": graph_id, "actor_id": actor_id, "ingestion": body},
            ),
            project_id=project_id,
        )

    def planning_project_id(self, session_id: str) -> str | None:
        session = self.legacy.get_planning_session(session_id)
        return None if session is None else session["project_id"]

    def enqueue_planning(
        self,
        session_id: str,
        project_id: str,
        payload: PlanningMessageCreate,
        *,
        actor_id: str,
    ) -> dict:
        body = payload.model_dump(mode="json")
        return self.jobs.enqueue(
            JobCreate(
                kind="ai.planning",
                queue="agents",
                idempotency_key=f"ai-planning:{session_id}:{self._digest(body)}",
                payload={"project_id": project_id, "actor_id": actor_id, "session_id": session_id, "message": body},
            ),
            project_id=project_id,
        )

    def enqueue_query(self, payload: GraphQueryCreate, *, actor_id: str) -> dict:
        project_id = self.project_id(payload.graph_id)
        body = payload.model_dump(mode="json")
        return self.jobs.enqueue(
            JobCreate(
                kind="ai.query",
                queue="agents",
                idempotency_key=f"ai-query:{project_id}:{self._digest(body)}",
                payload={"project_id": project_id, "actor_id": actor_id, "query": body},
            ),
            project_id=project_id,
        )

    def enqueue_research(self, payload: GraphResearchCreate, *, actor_id: str) -> dict:
        project_id = self.project_id(payload.graph_id)
        body = payload.model_dump(mode="json")
        return self.jobs.enqueue(
            JobCreate(
                kind="ai.research",
                queue="agents",
                idempotency_key=f"ai-research:{project_id}:{self._digest(body)}",
                payload={"project_id": project_id, "actor_id": actor_id, "research": body},
            ),
            project_id=project_id,
        )

    def enqueue_agent(self, payload: AgentRunCreate, *, actor_id: str) -> dict:
        project_id = self.project_id(str(payload.input.get("project_id") or payload.input.get("graph_id") or "project-default"))
        body = payload.model_dump(mode="json")
        return self.jobs.enqueue(
            JobCreate(
                kind="ai.agent",
                queue="agents",
                idempotency_key=f"ai-agent:{project_id}:{self._digest(body)}",
                payload={"project_id": project_id, "actor_id": actor_id, "agent_run": body},
            ),
            project_id=project_id,
        )

    def list(self, *, project_id: str, status: str | None, cursor: str | None, limit: int) -> list[dict]:
        return self.jobs.list(project_id=project_id, status=status, cursor=cursor, limit=limit)

    def get(self, job_id: str, *, project_id: str | None = None) -> dict | None:
        return self.jobs.get(job_id, project_id=project_id)

    def cancel(self, job_id: str, *, project_id: str) -> dict | None:
        return self.jobs.cancel(job_id, project_id=project_id)

    def retry(self, job_id: str, *, project_id: str) -> dict | None:
        return self.jobs.retry(job_id, project_id=project_id)

    @staticmethod
    def _digest(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
