from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, or_, select, update

from graphview_api import db
from graphview_api.lenses import normalize_graph_lens
from graphview_api.schemas import (
    AgentActionApprovalCreate,
    AgentRunCreate,
    GraphBuildSpecCreate,
    GraphQueryCreate,
    GraphResearchCreate,
    PlanningMessageCreate,
    PlanningSessionCreate,
    ReviewDecisionCreate,
)

DEFAULT_PROJECT_ID = "project-default"


def now() -> datetime:
    return datetime.now(tz=UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


def dump_json(value: object) -> str:
    return json.dumps(_jsonable(value), sort_keys=True)


def _jsonable(value: object):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class AiPlanningRepositoryMixin:
    """Planning, research, agent-run, and review-gated agent-action persistence."""

    def create_planning_session(self, payload: PlanningSessionCreate, actor_id: str) -> dict:
        spec = self._graph_view_spec(payload.graph_id)
        timestamp = now()
        session = {
            "id": new_id("plan"),
            "project_id": spec.project_id,
            "graph_id": payload.graph_id,
            "lens": normalize_graph_lens(payload.lens),
            "title": payload.title,
            "goal": payload.goal,
            "status": "active",
            "provider": payload.provider,
            "model": payload.model,
            "created_by": actor_id,
            "metadata_json": dump_json(payload.metadata),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.planning_sessions).values(**session))
        return self.get_planning_session(session["id"]) or self._planning_session_from_row(session)

    def list_planning_sessions(self, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            sessions = [
                self._planning_session_from_row(row)
                for row in conn.execute(
                    select(db.planning_sessions)
                    .where(db.planning_sessions.c.project_id == spec.project_id)
                    .order_by(db.planning_sessions.c.updated_at.desc(), db.planning_sessions.c.id.desc())
                ).mappings()
            ]
        return [self._planning_session_with_children(session) for session in sessions]

    def get_planning_session(self, session_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.planning_sessions).where(db.planning_sessions.c.id == session_id)
            ).mappings().first()
            if row is None:
                return None
            session = self._planning_session_from_row(row)
        return self._planning_session_with_children(session)

    def add_planning_message(
        self,
        session_id: str,
        payload: PlanningMessageCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        assistant_content: str,
        assistant_metadata: dict,
        agent_run_output: dict,
    ) -> dict:
        session = self.get_planning_session(session_id)
        if session is None:
            raise KeyError(session_id)
        timestamp = now()
        trace_id = new_id("trace")
        agent_run = {
            "id": new_id("agent"),
            "project_id": session["project_id"],
            "planning_session_id": session_id,
            "kind": "planning",
            "status": "completed",
            "provider": provider,
            "model": model,
            "input_json": dump_json({"message": payload.content, "session_id": session_id}),
            "output_json": dump_json(agent_run_output),
            "trace_id": trace_id,
            "created_by": actor_id,
            "started_at": timestamp,
            "finished_at": timestamp,
            "error": None,
        }
        user_message = {
            "id": new_id("msg"),
            "project_id": session["project_id"],
            "session_id": session_id,
            "agent_run_id": agent_run["id"],
            "role": "user",
            "content": payload.content,
            "provider": provider,
            "model": model,
            "metadata_json": dump_json({}),
            "created_at": timestamp,
        }
        assistant_message = {
            "id": new_id("msg"),
            "project_id": session["project_id"],
            "session_id": session_id,
            "agent_run_id": agent_run["id"],
            "role": "assistant",
            "content": assistant_content,
            "provider": provider,
            "model": model,
            "metadata_json": dump_json(assistant_metadata),
            "created_at": timestamp,
        }
        step = self._agent_step_row(
            project_id=session["project_id"],
            agent_run_id=agent_run["id"],
            name="agent.plan",
            status="completed",
            input_summary=payload.content[:500],
            output_summary=assistant_content[:500],
            trace_id=trace_id,
            timestamp=timestamp,
        )
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_runs).values(**agent_run))
            conn.execute(insert(db.agent_steps).values(**step))
            conn.execute(insert(db.planning_messages), [user_message, assistant_message])
            conn.execute(
                update(db.planning_sessions)
                .where(db.planning_sessions.c.id == session_id)
                .values(updated_at=timestamp, provider=provider, model=model)
            )
            self._record_activity_event(
                conn,
                project_id=session["project_id"],
                event_type="agent.run.completed",
                actor_id=actor_id,
                summary="Completed planning agent run.",
                object_refs=[
                    self._activity_ref("agent_run", agent_run["id"], "planning"),
                    self._activity_ref("planning_session", session_id, session["title"]),
                ],
                payload={"agent_run_id": agent_run["id"], "kind": "planning", "status": "completed"},
                lenses=[] if normalize_graph_lens(session["lens"]) == "all" else [normalize_graph_lens(session["lens"])],
                timestamp=timestamp,
            )
        return self.get_planning_session(session_id) or session

    def upsert_graph_build_spec(self, session_id: str, payload: GraphBuildSpecCreate) -> dict:
        session = self.get_planning_session(session_id)
        if session is None:
            raise KeyError(session_id)
        timestamp = now()
        with self.engine.begin() as conn:
            current = conn.execute(
                select(db.graph_build_specs)
                .where(db.graph_build_specs.c.session_id == session_id)
                .order_by(db.graph_build_specs.c.version.desc())
            ).mappings().first()
            version = 1 if current is None else current["version"] + 1
            spec = {
                "id": new_id("buildspec"),
                "project_id": session["project_id"],
                "session_id": session_id,
                "version": version,
                "title": payload.title or session["title"],
                "objective": payload.objective or session["goal"],
                "status": payload.status,
                "spec_json": dump_json(payload.spec),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            conn.execute(insert(db.graph_build_specs).values(**spec))
            conn.execute(update(db.planning_sessions).where(db.planning_sessions.c.id == session_id).values(updated_at=timestamp))
        return self._graph_build_spec_from_row(spec)

    def create_agent_run(
        self,
        payload: AgentRunCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        output: dict | None = None,
        status: str = "completed",
        error: str | None = None,
    ) -> dict:
        project_id = DEFAULT_PROJECT_ID
        if payload.planning_session_id:
            session = self.get_planning_session(payload.planning_session_id)
            if session is None:
                raise KeyError(payload.planning_session_id)
            project_id = session["project_id"]
        elif isinstance(payload.input.get("graph_id"), str) and payload.input["graph_id"]:
            project_id = self._graph_view_spec(payload.input["graph_id"]).project_id
        timestamp = now()
        trace_id = new_id("trace")
        run_input = dict(payload.input)
        run_input.setdefault("_agent_mode", payload.mode)
        if payload.focus_target is not None:
            run_input.setdefault("_focus_target", payload.focus_target.model_dump(exclude_none=True))
        run = {
            "id": new_id("agent"),
            "project_id": project_id,
            "planning_session_id": payload.planning_session_id,
            "kind": payload.kind,
            "status": status,
            "provider": provider,
            "model": model,
            "input_json": dump_json(run_input),
            "output_json": dump_json(output or {}),
            "trace_id": trace_id,
            "created_by": actor_id,
            "started_at": timestamp,
            "finished_at": timestamp if status in {"completed", "failed", "waiting_for_review"} else None,
            "error": error,
        }
        step = self._agent_step_row(
            project_id=project_id,
            agent_run_id=run["id"],
            name=f"agent.{payload.kind}",
            status=status,
            input_summary=dump_json(run_input)[:500],
            output_summary=dump_json(output or {})[:500],
            error=error,
            trace_id=trace_id,
            timestamp=timestamp,
        )
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_runs).values(**run))
            conn.execute(insert(db.agent_steps).values(**step))
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type=f"agent.run.{status}",
                actor_id=actor_id,
                summary=f"{status.replace('_', ' ').title()} {payload.kind.replace('_', ' ')} agent run.",
                object_refs=[
                    self._activity_ref("agent_run", run["id"], payload.kind),
                    *self._activity_refs_from_agent_payload(run_input, output or {}),
                ],
                payload={
                    "agent_run_id": run["id"],
                    "kind": payload.kind,
                    "status": status,
                    "trace_id": trace_id,
                },
                lenses=self._activity_lenses_from_agent_payload(run_input, output or {}),
                timestamp=timestamp,
            )
        return self.get_agent_run(run["id"]) or self._agent_run_from_row(run)

    def get_agent_run(self, agent_run_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(db.agent_runs).where(db.agent_runs.c.id == agent_run_id)).mappings().first()
            if row is None:
                return None
            run = self._agent_run_from_row(row)
            run["steps"] = [
                self._agent_step_from_row(step)
                for step in conn.execute(
                    select(db.agent_steps)
                    .where(db.agent_steps.c.agent_run_id == agent_run_id)
                    .order_by(db.agent_steps.c.started_at, db.agent_steps.c.id)
                ).mappings()
            ]
            run["action_proposals"] = [
                self._agent_action_proposal_from_row(action)
                for action in conn.execute(
                    select(db.agent_action_proposals)
                    .where(db.agent_action_proposals.c.agent_run_id == agent_run_id)
                    .order_by(db.agent_action_proposals.c.created_at, db.agent_action_proposals.c.id)
                ).mappings()
            ]
            return run

    def graph_query_context(
        self,
        payload: GraphQueryCreate,
        *,
        actor_id: str | None = None,
    ) -> dict:
        spec = self._graph_view_spec(payload.graph_id)
        from graphview_api.repository_retrieval import RetrievalMatcher

        retrieval = RetrievalMatcher(self)
        with self.engine.begin() as conn:
            project = dict(
                conn.execute(
                    select(db.graph_projects).where(db.graph_projects.c.id == spec.project_id)
                ).mappings().one()
            )
            if self.engine.dialect.name == "postgresql":
                matches = retrieval.postgres(conn, spec=spec, payload=payload)
            else:
                matches = retrieval.portable(conn, spec=spec, payload=payload)

            node_ids = [match["id"] for match in matches if match["kind"] == "node"]
            source_ids = {match["source_id"] for match in matches if match.get("source_id")}
            chunk_ids = [match["id"] for match in matches if match["kind"] == "chunk"]
            if payload.node_id and payload.node_id not in node_ids:
                node_ids.insert(0, payload.node_id)
            if payload.source_id:
                source_ids.add(payload.source_id)
            if payload.source_chunk_id and payload.source_chunk_id not in chunk_ids:
                chunk_ids.insert(0, payload.source_chunk_id)

            node_stmt = select(db.content_nodes).where(db.content_nodes.c.project_id == spec.project_id)
            node_stmt = node_stmt.where(db.content_nodes.c.id.in_(node_ids[:12])) if node_ids else node_stmt.where(False)
            selected_nodes = [self._node_from_row(row) for row in conn.execute(node_stmt).mappings()]
            selected_nodes.sort(key=lambda item: node_ids.index(item["id"]) if item["id"] in node_ids else len(node_ids))
            if normalize_graph_lens(payload.lens) != "all":
                selected_nodes = [node for node in selected_nodes if self._node_matches_lens(node, normalize_graph_lens(payload.lens))]
            for node in selected_nodes:
                source_ids.update(
                    item["sourceId"]
                    for item in node.get("provenance", [])
                    if item.get("sourceId")
                )

            allowed_source_ids = set(spec.source_ids) if spec.source_ids else None
            if allowed_source_ids is not None:
                source_ids.intersection_update(allowed_source_ids)
            source_stmt = select(db.sources).where(db.sources.c.project_id == spec.project_id)
            source_stmt = source_stmt.where(db.sources.c.id.in_(source_ids)) if source_ids else source_stmt.where(False)
            sources = [self._source_from_row(row) for row in conn.execute(source_stmt).mappings()]
            sources.sort(key=lambda item: next((index for index, match in enumerate(matches) if match.get("source_id") == item["id"]), len(matches)))

            chunk_stmt = select(db.source_chunks).where(db.source_chunks.c.project_id == spec.project_id)
            chunk_stmt = chunk_stmt.where(db.source_chunks.c.id.in_(chunk_ids[:12])) if chunk_ids else chunk_stmt.where(False)
            chunks = [self._source_chunk_from_row(row) for row in conn.execute(chunk_stmt).mappings()]
            chunks.sort(key=lambda item: chunk_ids.index(item["id"]) if item["id"] in chunk_ids else len(chunk_ids))
            chunk_source_ids = {chunk["source_id"] for chunk in chunks}
            for source in sources:
                if source["id"] in chunk_source_ids or len(chunks) >= 8:
                    continue
                fallback_chunks = conn.execute(
                    select(db.source_chunks)
                    .where(
                        and_(
                            db.source_chunks.c.project_id == spec.project_id,
                            db.source_chunks.c.source_id == source["id"],
                        )
                    )
                    .order_by(db.source_chunks.c.ordinal, db.source_chunks.c.id)
                    .limit(2)
                ).mappings()
                chunks.extend(self._source_chunk_from_row(row) for row in fallback_chunks)

            selected_node_ids = [node["id"] for node in selected_nodes]
            edge_stmt = select(db.semantic_edges).where(db.semantic_edges.c.project_id == spec.project_id)
            if selected_node_ids:
                edge_stmt = edge_stmt.where(
                    or_(
                        db.semantic_edges.c.source_node_id.in_(selected_node_ids),
                        db.semantic_edges.c.target_node_id.in_(selected_node_ids),
                    )
                ).limit(8)
                edges = [self._edge_from_row(row) for row in conn.execute(edge_stmt).mappings()]
            else:
                edges = []

            timestamp = now()
            conn.execute(
                insert(db.audit_events).values(
                    id=new_id("audit"),
                    project_id=spec.project_id,
                    actor_id=actor_id,
                    action="ai.retrieval",
                    resource_type="graph",
                    resource_id=spec.id,
                    outcome="succeeded",
                    summary=f"Retrieved {len(matches)} bounded graph anchors for cited AI context.",
                    metadata_json=dump_json(
                        {
                            "query_sha256": hashlib.sha256(payload.question.encode("utf-8")).hexdigest(),
                            "lens": payload.lens,
                            "node_id": payload.node_id,
                            "source_id": payload.source_id,
                            "source_chunk_id": payload.source_chunk_id,
                            "match_count": len(matches),
                            "citation_candidate_count": len(selected_nodes) + len(chunks),
                        }
                    ),
                    trace_id=new_id("trace"),
                    occurred_at=timestamp,
                )
            )

        chunks = chunks[:8]
        sources = sources[:6]
        selected_nodes = selected_nodes[:6]
        citations = self._agent_citations_from_context(nodes=selected_nodes, sources=sources, chunks=chunks)
        return {
            "project": project,
            "question": payload.question,
            "nodes": selected_nodes,
            "edges": edges,
            "sources": sources,
            "chunks": chunks,
            "citations": citations,
        }

    def create_research_task(
        self,
        payload: GraphResearchCreate,
        *,
        actor_id: str,
        provider: str,
        model: str,
        agent_run_id: str | None,
        result: dict,
    ) -> dict:
        spec = self._graph_view_spec(payload.graph_id)
        timestamp = now()
        idempotency_key = hashlib.sha256(
            f"{spec.project_id}:{payload.query}:{payload.lens}:{provider}:{model}:{payload.source_policy}".encode("utf-8")
        ).hexdigest()[:40]
        existing = self.get_research_task_by_key(idempotency_key)
        if existing:
            return existing
        task = {
            "id": new_id("research"),
            "project_id": spec.project_id,
            "agent_run_id": agent_run_id,
            "planning_session_id": None,
            "query": payload.query,
            "status": "proposal_ready",
            "provider": provider,
            "model": model,
            "source_policy": payload.source_policy,
            "idempotency_key": idempotency_key,
            "result_json": dump_json(result),
            "created_by": actor_id,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.research_tasks).values(**task))
            self._record_activity_event(
                conn,
                project_id=spec.project_id,
                event_type="research.proposal_ready",
                actor_id=actor_id,
                summary=f"Prepared research proposals for {payload.query}.",
                object_refs=[
                    self._activity_ref("research_task", task["id"], payload.query),
                    *([self._activity_ref("agent_run", agent_run_id, "research")] if agent_run_id else []),
                    *self._activity_refs_from_agent_payload({"lens": payload.lens}, result),
                ],
                payload={
                    "research_task_id": task["id"],
                    "agent_run_id": agent_run_id,
                    "query": payload.query,
                    "source_policy": payload.source_policy,
                    "proposal_ids": result.get("proposal_ids", []),
                    "source_id": result.get("source_id"),
                },
                lenses=[] if normalize_graph_lens(payload.lens) == "all" else [normalize_graph_lens(payload.lens)],
                timestamp=timestamp,
            )
        return self._research_task_from_row(task)

    def get_research_task_by_key(self, idempotency_key: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.research_tasks).where(db.research_tasks.c.idempotency_key == idempotency_key)
            ).mappings().first()
            return self._research_task_from_row(row) if row else None

    def create_agent_action_proposal(
        self,
        *,
        agent_run_id: str,
        action_type: str,
        title: str,
        summary: str,
        payload: dict,
        citations: list[dict] | None = None,
        confidence: float | None = None,
    ) -> dict:
        run = self.get_agent_run(agent_run_id)
        if run is None:
            raise KeyError(agent_run_id)
        timestamp = now()
        action = {
            "id": new_id("action"),
            "project_id": run["project_id"],
            "agent_run_id": agent_run_id,
            "action_type": action_type,
            "status": "pending_review",
            "title": title,
            "summary": summary,
            "payload_json": dump_json(payload),
            "citations_json": dump_json(citations or []),
            "confidence": confidence,
            "created_at": timestamp,
            "updated_at": timestamp,
            "applied_at": None,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.agent_action_proposals).values(**action))
            conn.execute(
                update(db.agent_runs)
                .where(db.agent_runs.c.id == agent_run_id)
                .values(status="waiting_for_review", finished_at=timestamp)
            )
            self._record_activity_event(
                conn,
                project_id=run["project_id"],
                event_type="agent.action_proposed",
                actor_id=run.get("created_by"),
                summary=f"Proposed agent action {title}.",
                object_refs=[
                    self._activity_ref("agent_action_proposal", action["id"], title),
                    self._activity_ref("agent_run", agent_run_id, run["kind"]),
                    *self._activity_refs_from_agent_payload(run.get("input", {}), payload),
                ],
                payload={
                    "action_proposal_id": action["id"],
                    "agent_run_id": agent_run_id,
                    "action_type": action_type,
                    "status": "pending_review",
                },
                lenses=self._activity_lenses_from_agent_payload(run.get("input", {}), payload),
                timestamp=timestamp,
            )
        return self._agent_action_proposal_from_row(action)

    def approve_agent_action(self, payload: AgentActionApprovalCreate, reviewer_id: str) -> dict:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_action_proposals).where(db.agent_action_proposals.c.id == payload.action_proposal_id)
            ).mappings().first()
            if row is None:
                raise KeyError(payload.action_proposal_id)
            action = self._agent_action_proposal_from_row(row)
            if action["status"] != "pending_review":
                return action
            timestamp = now()
            if payload.decision == "reject":
                conn.execute(
                    update(db.agent_action_proposals)
                    .where(db.agent_action_proposals.c.id == payload.action_proposal_id)
                    .values(status="rejected", updated_at=timestamp)
                )
                self._record_activity_event(
                    conn,
                    project_id=action["project_id"],
                    event_type="agent.action_rejected",
                    actor_id=reviewer_id,
                    summary=f"Rejected agent action {action['title']}.",
                    object_refs=[
                        self._activity_ref("agent_action_proposal", action["id"], action["title"]),
                        self._activity_ref("agent_run", action["agent_run_id"], action["action_type"]),
                    ],
                    payload={
                        "action_proposal_id": action["id"],
                        "agent_run_id": action["agent_run_id"],
                        "decision": payload.decision,
                        "rationale": payload.rationale,
                    },
                    lenses=[],
                    timestamp=timestamp,
                )
                return self.get_agent_action(payload.action_proposal_id) or action

        action_payload = action["payload"]
        if action["action_type"] == "review_decision":
            self.review(
                ReviewDecisionCreate(
                    proposal_id=action_payload["proposal_id"],
                    decision=action_payload.get("decision", "accept"),
                    rationale=payload.rationale or action_payload.get("rationale") or "Approved by AI action review.",
                ),
                reviewer_id,
            )
        with self.engine.begin() as conn:
            conn.execute(
                update(db.agent_action_proposals)
                .where(db.agent_action_proposals.c.id == payload.action_proposal_id)
                .values(status="applied", updated_at=timestamp, applied_at=timestamp)
            )
            self._record_activity_event(
                conn,
                project_id=action["project_id"],
                event_type="agent.action_applied",
                actor_id=reviewer_id,
                summary=f"Applied agent action {action['title']}.",
                object_refs=[
                    self._activity_ref("agent_action_proposal", action["id"], action["title"]),
                    self._activity_ref("agent_run", action["agent_run_id"], action["action_type"]),
                    *self._activity_refs_from_agent_payload({}, action.get("payload", {})),
                ],
                payload={
                    "action_proposal_id": action["id"],
                    "agent_run_id": action["agent_run_id"],
                    "decision": payload.decision,
                    "rationale": payload.rationale,
                },
                lenses=self._activity_lenses_from_agent_payload({}, action.get("payload", {})),
                timestamp=timestamp,
            )
        return self.get_agent_action(payload.action_proposal_id) or action

    def get_agent_action(self, action_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.agent_action_proposals).where(db.agent_action_proposals.c.id == action_id)
            ).mappings().first()
            return self._agent_action_proposal_from_row(row) if row else None
