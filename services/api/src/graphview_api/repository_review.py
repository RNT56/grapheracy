from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, or_, select, update

from graphview_api import db
from graphview_api.json_compat import json_value, normalize_json_row
from graphview_api.lenses import normalize_graph_lens
from graphview_api.schemas import ProposalCreate, ReviewDecisionCreate

DEFAULT_PROJECT_ID = "project-default"
GRAPH_LENSES = ("research", "engineering", "ops")


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


def load_json(value: object | None, fallback: object):
    if value is None:
        return fallback
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


class ReviewRepositoryMixin:
    """Proposal projections, review authority transitions, coverage, activity, and decision persistence."""

    def create_proposal(self, payload: ProposalCreate, actor_id: str) -> dict:
        source = self.get_source(payload.source_id)
        if source is None:
            raise KeyError(payload.source_id)

        timestamp = now()
        ingestion_run = {
            "id": new_id("run"),
            "project_id": source["project_id"],
            "source_id": payload.source_id,
            "status": "proposal_ready",
            "stage": "propose",
            "trace_id": new_id("trace"),
            "started_at": timestamp,
            "finished_at": timestamp,
            "error_code": None,
        }
        provenance = [
            {
                "sourceId": payload.source_id,
                "sourceUri": source.get("uri"),
                "locator": payload.locator,
                "extractedBy": "human",
                "actorId": actor_id,
                "ingestionRunId": ingestion_run["id"],
                "observedAt": timestamp.isoformat(),
                "traceId": ingestion_run["trace_id"],
            }
        ]
        proposal = {
            "id": new_id("proposal"),
            "project_id": source["project_id"],
            "ingestion_run_id": ingestion_run["id"],
            "kind": payload.kind,
            "status": "pending_review",
            "proposed_value_json": dump_json(payload.proposed_value),
            "confidence": payload.confidence,
            "provenance_json": dump_json(provenance),
            "created_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.ingestion_runs).values(**ingestion_run))
            conn.execute(insert(db.extraction_proposals).values(**proposal))
            proposal_output = self._proposal_from_row(proposal)
            self._record_activity_event(
                conn,
                project_id=source["project_id"],
                event_type="ingestion.proposal_ready",
                actor_id=actor_id,
                summary=f"Created a manual proposal run for {source['title']}.",
                object_refs=[
                    self._activity_ref("source", source["id"], source["title"]),
                    self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run["stage"]),
                ],
                payload={
                    "source_id": source["id"],
                    "ingestion_run_id": ingestion_run["id"],
                    "proposal_count": 1,
                },
                lenses=self._activity_lenses_for_proposals([proposal_output]),
                timestamp=timestamp,
            )
            self._record_proposal_created_activity(
                conn,
                proposal=proposal_output,
                source=source,
                ingestion_run=ingestion_run,
                actor_id=actor_id,
                timestamp=timestamp,
            )
        return proposal_output

    def list_proposals(self, graph_id: str | None = None, lens: str | None = None) -> list[dict]:
        normalized_lens = normalize_graph_lens(lens)
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            proposals = [
                self._proposal_from_row(row)
                for row in conn.execute(
                    select(db.extraction_proposals)
                    .where(db.extraction_proposals.c.project_id == spec.project_id)
                    .order_by(db.extraction_proposals.c.created_at.desc())
                ).mappings()
            ]
            if not spec.source_ids:
                return [proposal for proposal in proposals if self._proposal_matches_lens(proposal, normalized_lens)]
            run_ids = {
                row["id"]
                for row in conn.execute(
                    select(db.ingestion_runs.c.id).where(
                        and_(
                            db.ingestion_runs.c.project_id == spec.project_id,
                            db.ingestion_runs.c.source_id.in_(spec.source_ids),
                        )
                    )
                ).mappings()
            }
        return [
            proposal
            for proposal in proposals
            if proposal["ingestion_run_id"] in run_ids and self._proposal_matches_lens(proposal, normalized_lens)
        ]

    def review_queue(self, *, limit: int = 25, graph_id: str | None = None, lens: str | None = None) -> dict:
        normalized_limit = min(100, max(1, limit))
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            proposals = [
                proposal for proposal in self.list_proposals(graph_id=graph_id, lens=lens)
                if proposal["status"] == "pending_review"
            ]
            runs_by_id = {
                row["id"]: normalize_json_row(row)
                for row in conn.execute(
                    select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                ).mappings()
            }
            sources_by_id = {
                row["id"]: self._source_from_row(row)
                for row in conn.execute(select(db.sources).where(db.sources.c.project_id == spec.project_id)).mappings()
            }
        _, nodes, _ = self.graph(graph_id, lens)
        reviewed_node_ids = {node["id"] for node in nodes}

        items: list[dict] = []
        for proposal in proposals:
            source = None
            if run := runs_by_id.get(proposal["ingestion_run_id"]):
                source = sources_by_id.get(run["source_id"])
            items.append(self._review_queue_item(proposal, source, reviewed_node_ids))

        items.sort(
            key=lambda item: (
                -item["priority_score"],
                item["proposal"]["created_at"],
                item["proposal"]["id"],
            )
        )
        return {
            "generated_at": now(),
            "pending_count": len(items),
            "ready_count": sum(1 for item in items if item["ready_to_commit"]),
            "blocked_count": sum(1 for item in items if item["blocked"]),
            "items": items[:normalized_limit],
        }

    def review_dashboard(self, graph_id: str | None = None, lens: str | None = None) -> dict:
        project, _, _ = self.graph(graph_id, lens)
        proposals = self.list_proposals(graph_id=graph_id, lens=lens)
        proposal_ids = {proposal["id"] for proposal in proposals}
        decisions = [
            decision
            for decision in self.list_review_decisions(graph_id=graph_id)
            if decision["proposal_id"] in proposal_ids
        ]

        queue = self.review_queue(limit=1, graph_id=graph_id, lens=lens)
        pending_proposals = [proposal for proposal in proposals if proposal["status"] == "pending_review"]
        oldest_pending = min(
            pending_proposals,
            key=lambda proposal: (proposal["created_at"], proposal["id"]),
            default=None,
        )
        accepted_count = sum(1 for decision in decisions if decision["decision"] == "accept")
        rejected_count = sum(1 for decision in decisions if decision["decision"] == "reject")
        edited_count = sum(1 for decision in decisions if decision["decision"] == "edit")
        deferred_count = sum(1 for decision in decisions if decision["decision"] == "defer")
        review_decision_count = len(decisions)
        committed_count = accepted_count + edited_count

        return {
            "project_id": project["id"],
            "generated_at": now(),
            "proposal_count": len(proposals),
            "pending_count": queue["pending_count"],
            "ready_count": queue["ready_count"],
            "blocked_count": queue["blocked_count"],
            "review_decision_count": review_decision_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "edited_count": edited_count,
            "deferred_count": deferred_count,
            "acceptance_rate": 0.0 if review_decision_count == 0 else round((accepted_count / review_decision_count) * 100, 2),
            "commit_rate": 0.0 if review_decision_count == 0 else round((committed_count / review_decision_count) * 100, 2),
            "proposal_kind_counts": self._count_by(proposals, "kind"),
            "pending_kind_counts": self._count_by(pending_proposals, "kind"),
            "decision_counts": self._count_by(decisions, "decision"),
            "reviewer_counts": self._count_by(decisions, "reviewer_id"),
            "oldest_pending_proposal_id": oldest_pending["id"] if oldest_pending else None,
            "oldest_pending_created_at": oldest_pending["created_at"] if oldest_pending else None,
        }

    def review_activity(self, *, limit: int = 10, graph_id: str | None = None, lens: str | None = None) -> dict:
        normalized_limit = min(100, max(1, limit))
        spec = self._graph_view_spec(graph_id)
        scoped_proposals = self.list_proposals(graph_id=graph_id, lens=lens)
        scoped_proposal_ids = {proposal["id"] for proposal in scoped_proposals}
        with self.engine.begin() as conn:
            decisions = [
                self._decision_from_row(row)
                for row in conn.execute(
                    select(db.review_decisions)
                    .where(db.review_decisions.c.project_id == spec.project_id)
                    .order_by(db.review_decisions.c.decided_at.desc(), db.review_decisions.c.id.desc())
                ).mappings()
                if row["proposal_id"] in scoped_proposal_ids
            ]
            proposal_ids = [decision["proposal_id"] for decision in decisions]
            proposals_by_id = {
                proposal["id"]: proposal
                for proposal in self._proposals_for_ids(conn, proposal_ids, spec.project_id)
            }
            runs_by_id = {
                row["id"]: normalize_json_row(row)
                for row in conn.execute(
                    select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                ).mappings()
            }
            sources_by_id = {
                row["id"]: self._source_from_row(row)
                for row in conn.execute(select(db.sources).where(db.sources.c.project_id == spec.project_id)).mappings()
            }

        items = []
        for decision in decisions[:normalized_limit]:
            proposal = proposals_by_id.get(decision["proposal_id"])
            source = None
            if proposal and (run := runs_by_id.get(proposal["ingestion_run_id"])):
                source = sources_by_id.get(run["source_id"])
            items.append(
                {
                    "decision": decision,
                    "proposal": proposal,
                    "source": source,
                    "summary": self._review_activity_summary(decision, proposal),
                }
            )

        return {
            "generated_at": now(),
            "review_decision_count": len(decisions),
            "returned_count": len(items),
            "items": items,
        }
    def source_review_coverage(self, *, limit: int = 25, graph_id: str | None = None, lens: str | None = None) -> dict:
        normalized_limit = min(100, max(1, limit))
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            sources = [
                self._source_from_row(row)
                for row in conn.execute(
                    select(db.sources)
                    .where(db.sources.c.project_id == spec.project_id)
                    .order_by(db.sources.c.created_at.desc(), db.sources.c.id.desc())
                ).mappings()
            ]
            if spec.source_ids:
                source_id_set = set(spec.source_ids)
                sources = [source for source in sources if source["id"] in source_id_set]
            runs_by_id = {
                row["id"]: normalize_json_row(row)
                for row in conn.execute(
                    select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                ).mappings()
            }
            proposals = self.list_proposals(graph_id=graph_id, lens=lens)
            decisions = [
                self._decision_from_row(row)
                for row in conn.execute(
                    select(db.review_decisions).where(db.review_decisions.c.project_id == spec.project_id)
                ).mappings()
            ]

        proposals_by_source_id: dict[str, list[dict]] = {source["id"]: [] for source in sources}
        for proposal in proposals:
            run = runs_by_id.get(proposal["ingestion_run_id"])
            if run and run["source_id"] in proposals_by_source_id:
                proposals_by_source_id[run["source_id"]].append(proposal)

        decisions_by_proposal_id: dict[str, list[dict]] = {}
        for decision in decisions:
            decisions_by_proposal_id.setdefault(decision["proposal_id"], []).append(decision)

        summaries = [
            self._source_review_summary(source, proposals_by_source_id.get(source["id"], []), decisions_by_proposal_id)
            for source in sources
        ]
        summaries.sort(
            key=lambda item: (
                -item["pending_count"],
                -item["proposal_count"],
                item["last_reviewed_at"] is None,
                item["last_reviewed_at"] or datetime.min.replace(tzinfo=UTC),
                item["source"]["title"],
                item["source"]["id"],
            )
        )

        return {
            "generated_at": now(),
            "source_count": len(sources),
            "proposal_count": len(proposals),
            "pending_count": sum(summary["pending_count"] for summary in summaries),
            "reviewed_count": sum(summary["reviewed_count"] for summary in summaries),
            "returned_count": min(len(summaries), normalized_limit),
            "sources": summaries[:normalized_limit],
        }

    def review(self, payload: ReviewDecisionCreate, reviewer_id: str) -> dict:
        with self.engine.begin() as conn:
            proposal_row = conn.execute(
                select(db.extraction_proposals).where(db.extraction_proposals.c.id == payload.proposal_id)
            ).mappings().first()
            if proposal_row is None:
                raise KeyError(payload.proposal_id)

            timestamp = now()
            edited = payload.edited_value
            project_id = proposal_row["project_id"]
            decision = {
                "id": new_id("review"),
                "project_id": project_id,
                "proposal_id": payload.proposal_id,
                "reviewer_id": reviewer_id,
                "decision": payload.decision,
                "edited_value_json": dump_json(edited) if edited is not None else None,
                "rationale": payload.rationale,
                "decided_at": timestamp,
            }
            self._record_review_decision(conn, proposal_row, decision, payload.decision, edited, timestamp)
        return self._decision_from_row(decision)

    def _record_review_decision(
        self,
        conn,
        proposal_row: dict,
        decision: dict,
        decision_value: str,
        edited: dict | None,
        timestamp: datetime,
    ) -> None:
        project_id = proposal_row["project_id"]
        proposal_id = proposal_row["id"]
        conn.execute(insert(db.review_decisions).values(**decision))
        conn.execute(
            update(db.extraction_proposals)
            .where(db.extraction_proposals.c.id == proposal_id)
            .values(status=self._proposal_status(decision_value))
        )
        proposal = self._proposal_from_row(proposal_row)
        proposal["status"] = self._proposal_status(decision_value)
        source = self._source_from_provenance(conn, proposal.get("provenance", []), project_id)
        self._record_activity_event(
            conn,
            project_id=project_id,
            event_type="proposal.reviewed",
            actor_id=decision["reviewer_id"],
            summary=self._review_activity_summary(self._decision_from_row(decision), proposal),
            object_refs=self._activity_refs_for_proposal(
                proposal,
                source=source,
                decision=self._decision_from_row(decision),
            ),
            payload={
                "proposal_id": proposal_id,
                "decision_id": decision["id"],
                "decision": decision_value,
                "status": proposal["status"],
                "rationale": decision.get("rationale"),
            },
            lenses=self._activity_lenses_for_proposal(proposal),
            timestamp=timestamp,
        )

        if decision_value not in {"accept", "edit"}:
            return

        value = edited if edited is not None else load_json(json_value(proposal_row, "proposed_value_json"), {})
        if proposal_row["kind"] == "content_node":
            node_id = value.get("id") or new_id("node")
            existing = conn.execute(
                select(db.content_nodes.c.id).where(
                    and_(db.content_nodes.c.id == node_id, db.content_nodes.c.project_id == project_id)
                )
            ).first()
            if existing is None:
                conn.execute(
                    insert(db.content_nodes).values(
                        id=node_id,
                        project_id=project_id,
                        label=value.get("label", "Untitled concept"),
                        kind=value.get("kind", "concept"),
                        summary=value.get("summary"),
                        topic_ids_json=dump_json(value.get("topicIds", [])),
                        metadata_json=dump_json(value.get("metadata") or {}),
                        provenance_json=json_value(proposal_row, "provenance_json"),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="graph.node_committed",
                    actor_id=decision["reviewer_id"],
                    summary=f"Committed node {value.get('label') or node_id}.",
                    object_refs=[
                        *self._activity_refs_for_proposal(
                            proposal,
                            source=source,
                            decision=self._decision_from_row(decision),
                        ),
                        self._activity_ref("node", node_id, value.get("label") or node_id),
                    ],
                    payload={
                        "proposal_id": proposal_id,
                        "decision_id": decision["id"],
                        "node_id": node_id,
                        "kind": value.get("kind", "concept"),
                    },
                    lenses=self._activity_lenses_for_proposal(proposal),
                    timestamp=timestamp,
                )
            conn.execute(
                update(db.content_embeddings)
                .where(db.content_embeddings.c.proposal_id == proposal_id)
                .values(content_node_id=node_id)
            )
            return

        if proposal_row["kind"] == "semantic_edge":
            if not self._nodes_exist(conn, [value["sourceNodeId"], value["targetNodeId"]], project_id=project_id):
                raise ValueError("Semantic edge endpoints must be accepted before the edge can be committed")
            edge_id = value.get("id") or new_id("edge")
            existing = conn.execute(
                select(db.semantic_edges.c.id).where(
                    and_(
                        db.semantic_edges.c.project_id == project_id,
                        or_(
                            db.semantic_edges.c.id == edge_id,
                            and_(
                                db.semantic_edges.c.source_node_id == value["sourceNodeId"],
                                db.semantic_edges.c.target_node_id == value["targetNodeId"],
                                db.semantic_edges.c.relation == value.get("relation", "relates_to"),
                            ),
                        ),
                    )
                )
            ).first()
            if existing is None:
                conn.execute(
                    insert(db.semantic_edges).values(
                        id=edge_id,
                        project_id=project_id,
                        source_node_id=value["sourceNodeId"],
                        target_node_id=value["targetNodeId"],
                        relation=value.get("relation", "relates_to"),
                        weight=value.get("weight"),
                        metadata_json=dump_json(value.get("metadata") or {}),
                        provenance_json=json_value(proposal_row, "provenance_json"),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="graph.edge_committed",
                    actor_id=decision["reviewer_id"],
                    summary=(
                        f"Committed relationship {value.get('sourceLabel') or value.get('sourceNodeId')} "
                        f"{value.get('relation', 'relates_to')} {value.get('targetLabel') or value.get('targetNodeId')}."
                    ),
                    object_refs=[
                        *self._activity_refs_for_proposal(
                            proposal,
                            source=source,
                            decision=self._decision_from_row(decision),
                        ),
                        self._activity_ref("edge", edge_id, value.get("label") or value.get("relation", "relates_to")),
                    ],
                    payload={
                        "proposal_id": proposal_id,
                        "decision_id": decision["id"],
                        "edge_id": edge_id,
                        "source_node_id": value["sourceNodeId"],
                        "target_node_id": value["targetNodeId"],
                        "relation": value.get("relation", "relates_to"),
                    },
                    lenses=self._activity_lenses_for_proposal(proposal),
                    timestamp=timestamp,
                )
    def _record_proposal_created_activity(
        self,
        conn,
        *,
        proposal: dict,
        source: dict | None,
        ingestion_run: dict | None,
        actor_id: str,
        timestamp: datetime,
    ) -> None:
        self._record_activity_event(
            conn,
            project_id=proposal["project_id"],
            event_type="proposal.created",
            actor_id=actor_id,
            summary=self._proposal_activity_summary("Created", proposal),
            object_refs=self._activity_refs_for_proposal(proposal, source=source, ingestion_run=ingestion_run),
            payload={
                "proposal_id": proposal["id"],
                "kind": proposal["kind"],
                "status": proposal["status"],
                "confidence": proposal.get("confidence"),
                "source_id": source["id"] if source else None,
                "ingestion_run_id": ingestion_run["id"] if ingestion_run else proposal.get("ingestion_run_id"),
            },
            lenses=self._activity_lenses_for_proposal(proposal),
            timestamp=timestamp,
        )

    def _activity_ref(self, kind: str, object_id: str | None, label: str | None = None) -> dict:
        return {"kind": kind, "id": object_id or "", "label": label}

    def _activity_refs_for_proposal(
        self,
        proposal: dict,
        *,
        source: dict | None = None,
        ingestion_run: dict | None = None,
        decision: dict | None = None,
    ) -> list[dict]:
        value = proposal.get("proposed_value", {})
        refs = []
        if source is not None:
            refs.append(self._activity_ref("source", source["id"], source["title"]))
        if ingestion_run is not None:
            refs.append(self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run.get("stage")))
        refs.append(self._activity_ref("proposal", proposal["id"], self._proposal_activity_label(proposal)))
        if decision is not None:
            refs.append(self._activity_ref("review_decision", decision["id"], decision["decision"]))
        if proposal.get("kind") == "content_node" and isinstance(value.get("id"), str):
            refs.append(self._activity_ref("node", value["id"], value.get("label") or value["id"]))
        if proposal.get("kind") == "semantic_edge" and isinstance(value.get("id"), str):
            refs.append(self._activity_ref("edge", value["id"], value.get("label") or value.get("relation", "relates_to")))
        return refs

    def _activity_refs_from_agent_payload(self, input_payload: dict, output_payload: dict) -> list[dict]:
        refs: list[dict] = []
        for key, kind in [
            ("source_id", "source"),
            ("node_id", "node"),
            ("proposal_id", "proposal"),
            ("research_task_id", "research_task"),
            ("action_proposal_id", "agent_action_proposal"),
        ]:
            value = output_payload.get(key) or input_payload.get(key)
            if isinstance(value, str) and value:
                refs.append(self._activity_ref(kind, value, None))
        for proposal_id in output_payload.get("proposal_ids") or input_payload.get("proposal_ids") or []:
            if isinstance(proposal_id, str) and proposal_id:
                refs.append(self._activity_ref("proposal", proposal_id, None))
        return refs

    def _activity_lenses_from_agent_payload(self, input_payload: dict, output_payload: dict) -> list[str]:
        lens = normalize_graph_lens(input_payload.get("lens") if isinstance(input_payload.get("lens"), str) else None)
        if lens != "all":
            return [lens]
        output_lens = normalize_graph_lens(output_payload.get("lens") if isinstance(output_payload.get("lens"), str) else None)
        return [] if output_lens == "all" else [output_lens]

    def _activity_lenses_for_proposals(self, proposals: list[dict]) -> list[str]:
        lenses: set[str] = set()
        for proposal in proposals:
            lenses.update(self._activity_lenses_for_proposal(proposal))
        return sorted(lenses)

    def _activity_lenses_for_proposal(self, proposal: dict) -> list[str]:
        return [lens for lens in GRAPH_LENSES if self._proposal_matches_lens(proposal, lens)]

    def _proposal_activity_label(self, proposal: dict) -> str:
        value = proposal.get("proposed_value", {})
        if proposal.get("kind") == "semantic_edge":
            return (
                f"{value.get('sourceLabel') or value.get('sourceNodeId') or 'source'} "
                f"{value.get('relation') or 'relates_to'} "
                f"{value.get('targetLabel') or value.get('targetNodeId') or 'target'}"
            )
        return str(value.get("label") or value.get("id") or "Untitled proposal")

    def _proposal_activity_summary(self, verb: str, proposal: dict) -> str:
        if proposal.get("kind") == "semantic_edge":
            return f"{verb} relationship proposal {self._proposal_activity_label(proposal)}."
        return f"{verb} node proposal {self._proposal_activity_label(proposal)}."

    def _activity_event_matches_scope(self, event: dict, source_ids: tuple[str, ...]) -> bool:
        scoped_source_ids = set(source_ids)
        for ref in event.get("object_refs", []):
            if ref.get("kind") == "source" and ref.get("id") in scoped_source_ids:
                return True
        payload = event.get("payload", {})
        return payload.get("source_id") in scoped_source_ids

    def _review_activity_summary(self, decision: dict, proposal: dict | None) -> str:
        action = {
            "accept": "Accepted",
            "reject": "Rejected",
            "edit": "Edited",
            "defer": "Deferred",
        }.get(decision["decision"], "Reviewed")
        if proposal is None:
            return f"{action} unavailable proposal {decision['proposal_id']}."

        value = proposal["proposed_value"]
        if proposal["kind"] == "semantic_edge":
            source_label = value.get("sourceLabel") or value.get("sourceNodeId") or "source node"
            target_label = value.get("targetLabel") or value.get("targetNodeId") or "target node"
            relation = value.get("relation", "relates_to")
            return f"{action} relationship proposal {source_label} {relation} {target_label}."

        label = value.get("label") or value.get("id") or "Untitled node"
        return f"{action} node proposal {label}."

    def _source_review_summary(
        self,
        source: dict,
        proposals: list[dict],
        decisions_by_proposal_id: dict[str, list[dict]],
    ) -> dict:
        decisions = [
            decision
            for proposal in proposals
            for decision in decisions_by_proposal_id.get(proposal["id"], [])
        ]
        proposal_count = len(proposals)
        pending_count = sum(1 for proposal in proposals if proposal["status"] == "pending_review")
        reviewed_count = proposal_count - pending_count
        if proposal_count == 0:
            status = "no_proposals"
        elif pending_count == proposal_count:
            status = "pending_review"
        elif pending_count > 0:
            status = "mixed"
        else:
            status = "reviewed"

        return {
            "source": source,
            "status": status,
            "proposal_count": proposal_count,
            "pending_count": pending_count,
            "reviewed_count": reviewed_count,
            "decision_count": len(decisions),
            "accepted_count": sum(1 for decision in decisions if decision["decision"] == "accept"),
            "rejected_count": sum(1 for decision in decisions if decision["decision"] == "reject"),
            "edited_count": sum(1 for decision in decisions if decision["decision"] == "edit"),
            "deferred_count": sum(1 for decision in decisions if decision["decision"] == "defer"),
            "last_reviewed_at": max((decision["decided_at"] for decision in decisions), default=None),
        }

    def _review_queue_item(self, proposal: dict, source: dict | None, reviewed_node_ids: set[str]) -> dict:
        value = proposal["proposed_value"]
        source_title = source["title"] if source else None
        source_id = source["id"] if source else None
        locator = proposal["provenance"][0].get("locator") if proposal.get("provenance") else proposal.get("locator")
        citation = {
            "id": f"citation-{proposal['id']}",
            "label": source_title or "Proposal evidence",
            "source_id": source_id,
            "source_title": source_title,
            "proposal_id": proposal["id"],
            "locator": locator,
            "quote": value.get("summary") or value.get("label") or value.get("relation"),
            "confidence": proposal.get("confidence"),
        }
        if proposal["kind"] == "semantic_edge":
            endpoint_ids = [
                node_id
                for node_id in [value.get("sourceNodeId"), value.get("targetNodeId")]
                if isinstance(node_id, str) and node_id
            ]
            missing_endpoint_ids = [node_id for node_id in endpoint_ids if node_id not in reviewed_node_ids]
            blocked = bool(missing_endpoint_ids) or len(endpoint_ids) < 2
            return {
                "proposal": proposal,
                "source": source,
                "priority_score": 30 if blocked else 90,
                "action": "accept_endpoints" if blocked else "review_relationship",
                "work_item_kind": "new_relation",
                "change_summary": f"{value.get('sourceLabel') or value.get('sourceNodeId') or 'Source'} {value.get('relation') or 'relates_to'} {value.get('targetLabel') or value.get('targetNodeId') or 'target'}",
                "evidence_summary": source_title or "Relationship proposal evidence",
                "affected_graph_ids": endpoint_ids,
                "citations": [citation],
                "blocked": blocked,
                "ready_to_commit": not blocked,
                "reason": (
                    "Accept endpoint nodes before this relationship can be committed."
                    if blocked
                    else "Relationship endpoints are reviewed and ready for decision."
                ),
                "endpoint_node_ids": endpoint_ids,
                "missing_endpoint_node_ids": missing_endpoint_ids,
            }

        confidence = proposal.get("confidence") or 0
        return {
            "proposal": proposal,
            "source": source,
            "priority_score": 80 if confidence >= 0.75 else 60,
            "action": "review_node",
            "work_item_kind": "new_entity",
            "change_summary": f"Create {value.get('kind') or 'concept'}: {value.get('label') or 'Untitled proposal'}",
            "evidence_summary": source_title or "Source extraction proposal",
            "affected_graph_ids": [value["id"]] if isinstance(value.get("id"), str) else [],
            "citations": [citation],
            "blocked": False,
            "ready_to_commit": True,
            "reason": "High-confidence node proposal is ready for review." if confidence >= 0.75 else "Node proposal is ready for review.",
            "endpoint_node_ids": [],
            "missing_endpoint_node_ids": [],
        }

    def list_review_decisions(self, graph_id: str | None = None) -> list[dict]:
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            return [
                self._decision_from_row(row)
                for row in conn.execute(
                    select(db.review_decisions)
                    .where(db.review_decisions.c.project_id == spec.project_id)
                    .order_by(db.review_decisions.c.decided_at.desc())
                ).mappings()
            ]
