from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, and_, delete, insert, or_, select, update

from graphview_api import db
from graphview_api.schemas import ProposalCreate, ReviewDecisionCreate, SourceCreate, SourceUpdate

DEFAULT_PROJECT_ID = "project-default"


def now() -> datetime:
    return datetime.now(tz=UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


def dump_json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def load_json(value: str | None, fallback: object):
    if value is None:
        return fallback
    return json.loads(value)


class GraphRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def initialize(self) -> None:
        db.metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(db.graph_projects.c.id).where(db.graph_projects.c.id == DEFAULT_PROJECT_ID)
            ).first()
            if existing is None:
                timestamp = now()
                conn.execute(
                    insert(db.graph_projects).values(
                        id=DEFAULT_PROJECT_ID,
                        name="Research Knowledge Map",
                        description="Default internal knowledge graph project.",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )

    def project(self) -> dict:
        with self.engine.begin() as conn:
            return dict(
                conn.execute(
                    select(db.graph_projects).where(db.graph_projects.c.id == DEFAULT_PROJECT_ID)
                ).mappings().one()
            )

    def graph(self) -> tuple[dict, list[dict], list[dict]]:
        with self.engine.begin() as conn:
            project = dict(
                conn.execute(
                    select(db.graph_projects).where(db.graph_projects.c.id == DEFAULT_PROJECT_ID)
                ).mappings().one()
            )
            nodes = [
                self._node_from_row(row)
                for row in conn.execute(
                    select(db.content_nodes).where(db.content_nodes.c.project_id == DEFAULT_PROJECT_ID)
                ).mappings()
            ]
            edges = [
                self._edge_from_row(row)
                for row in conn.execute(
                    select(db.semantic_edges).where(db.semantic_edges.c.project_id == DEFAULT_PROJECT_ID)
                ).mappings()
            ]
            return project, nodes, edges

    def list_sources(self, query: str | None = None) -> list[dict]:
        stmt = select(db.sources).where(db.sources.c.project_id == DEFAULT_PROJECT_ID)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(db.sources.c.title.like(like), db.sources.c.uri.like(like)))
        stmt = stmt.order_by(db.sources.c.created_at.desc())
        with self.engine.begin() as conn:
            return [dict(row) for row in conn.execute(stmt).mappings()]

    def create_source(self, payload: SourceCreate) -> dict:
        timestamp = now()
        source = {
            "id": new_id("src"),
            "project_id": DEFAULT_PROJECT_ID,
            "kind": payload.kind,
            "title": payload.title,
            "uri": payload.uri,
            "object_key": payload.object_key,
            "checksum": payload.checksum,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(db.sources).values(**source))
        return source

    def update_source(self, source_id: str, payload: SourceUpdate) -> dict | None:
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return self.get_source(source_id)
        values["updated_at"] = now()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(db.sources)
                .where(and_(db.sources.c.id == source_id, db.sources.c.project_id == DEFAULT_PROJECT_ID))
                .values(**values)
            )
            if result.rowcount == 0:
                return None
        return self.get_source(source_id)

    def get_source(self, source_id: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.sources).where(
                    and_(db.sources.c.id == source_id, db.sources.c.project_id == DEFAULT_PROJECT_ID)
                )
            ).mappings().first()
            return dict(row) if row else None

    def delete_source(self, source_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                delete(db.sources).where(
                    and_(db.sources.c.id == source_id, db.sources.c.project_id == DEFAULT_PROJECT_ID)
                )
            )
            return result.rowcount > 0

    def list_ingestion_runs(self) -> list[dict]:
        with self.engine.begin() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(db.ingestion_runs)
                    .where(db.ingestion_runs.c.project_id == DEFAULT_PROJECT_ID)
                    .order_by(db.ingestion_runs.c.started_at.desc())
                ).mappings()
            ]

    def create_proposal(self, payload: ProposalCreate, actor_id: str) -> dict:
        source = self.get_source(payload.source_id)
        if source is None:
            raise KeyError(payload.source_id)

        timestamp = now()
        ingestion_run = {
            "id": new_id("run"),
            "project_id": DEFAULT_PROJECT_ID,
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
            "project_id": DEFAULT_PROJECT_ID,
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
        return self._proposal_from_row(proposal)

    def list_proposals(self) -> list[dict]:
        with self.engine.begin() as conn:
            return [
                self._proposal_from_row(row)
                for row in conn.execute(
                    select(db.extraction_proposals)
                    .where(db.extraction_proposals.c.project_id == DEFAULT_PROJECT_ID)
                    .order_by(db.extraction_proposals.c.created_at.desc())
                ).mappings()
            ]

    def review(self, payload: ReviewDecisionCreate, reviewer_id: str) -> dict:
        with self.engine.begin() as conn:
            proposal_row = conn.execute(
                select(db.extraction_proposals).where(
                    and_(
                        db.extraction_proposals.c.id == payload.proposal_id,
                        db.extraction_proposals.c.project_id == DEFAULT_PROJECT_ID,
                    )
                )
            ).mappings().first()
            if proposal_row is None:
                raise KeyError(payload.proposal_id)

            timestamp = now()
            edited = payload.edited_value
            decision = {
                "id": new_id("review"),
                "project_id": DEFAULT_PROJECT_ID,
                "proposal_id": payload.proposal_id,
                "reviewer_id": reviewer_id,
                "decision": payload.decision,
                "edited_value_json": dump_json(edited) if edited is not None else None,
                "rationale": payload.rationale,
                "decided_at": timestamp,
            }
            conn.execute(insert(db.review_decisions).values(**decision))
            conn.execute(
                update(db.extraction_proposals)
                .where(db.extraction_proposals.c.id == payload.proposal_id)
                .values(status=self._proposal_status(payload.decision))
            )

            if payload.decision in {"accept", "edit"}:
                value = edited if edited is not None else load_json(proposal_row["proposed_value_json"], {})
                if proposal_row["kind"] == "content_node":
                    node_id = value.get("id") or new_id("node")
                    conn.execute(
                        insert(db.content_nodes).values(
                            id=node_id,
                            project_id=DEFAULT_PROJECT_ID,
                            label=value.get("label", "Untitled concept"),
                            kind=value.get("kind", "concept"),
                            summary=value.get("summary"),
                            topic_ids_json=dump_json(value.get("topicIds", [])),
                            provenance_json=proposal_row["provenance_json"],
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                    )
                elif proposal_row["kind"] == "semantic_edge":
                    conn.execute(
                        insert(db.semantic_edges).values(
                            id=value.get("id") or new_id("edge"),
                            project_id=DEFAULT_PROJECT_ID,
                            source_node_id=value["sourceNodeId"],
                            target_node_id=value["targetNodeId"],
                            relation=value.get("relation", "relates_to"),
                            weight=value.get("weight"),
                            provenance_json=proposal_row["provenance_json"],
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                    )
        return self._decision_from_row(decision)

    def list_review_decisions(self) -> list[dict]:
        with self.engine.begin() as conn:
            return [
                self._decision_from_row(row)
                for row in conn.execute(
                    select(db.review_decisions)
                    .where(db.review_decisions.c.project_id == DEFAULT_PROJECT_ID)
                    .order_by(db.review_decisions.c.decided_at.desc())
                ).mappings()
            ]

    def search(self, query: str) -> dict[str, list[dict]]:
        like = f"%{query}%"
        with self.engine.begin() as conn:
            sources = [
                dict(row)
                for row in conn.execute(
                    select(db.sources).where(
                        and_(
                            db.sources.c.project_id == DEFAULT_PROJECT_ID,
                            or_(db.sources.c.title.like(like), db.sources.c.uri.like(like)),
                        )
                    )
                ).mappings()
            ]
            nodes = [
                self._node_from_row(row)
                for row in conn.execute(
                    select(db.content_nodes).where(
                        and_(
                            db.content_nodes.c.project_id == DEFAULT_PROJECT_ID,
                            or_(db.content_nodes.c.label.like(like), db.content_nodes.c.summary.like(like)),
                        )
                    )
                ).mappings()
            ]
        return {"sources": sources, "nodes": nodes}

    def export_bundle(self) -> dict:
        project, nodes, edges = self.graph()
        with self.engine.begin() as conn:
            return {
                "project": project,
                "sources": [dict(row) for row in conn.execute(select(db.sources)).mappings()],
                "nodes": nodes,
                "edges": edges,
                "ingestion_runs": [dict(row) for row in conn.execute(select(db.ingestion_runs)).mappings()],
                "proposals": [
                    self._proposal_from_row(row)
                    for row in conn.execute(select(db.extraction_proposals)).mappings()
                ],
                "review_decisions": [
                    self._decision_from_row(row) for row in conn.execute(select(db.review_decisions)).mappings()
                ],
            }

    def _proposal_status(self, decision: str) -> str:
        return {
            "accept": "accepted",
            "reject": "rejected",
            "edit": "edited",
            "defer": "deferred",
        }[decision]

    def _proposal_from_row(self, row) -> dict:
        data = dict(row)
        data["proposed_value"] = load_json(data.pop("proposed_value_json"), {})
        data["provenance"] = load_json(data.pop("provenance_json"), [])
        return data

    def _decision_from_row(self, row) -> dict:
        data = dict(row)
        data["edited_value"] = load_json(data.pop("edited_value_json"), None)
        return data

    def _node_from_row(self, row) -> dict:
        data = dict(row)
        data["topic_ids"] = load_json(data.pop("topic_ids_json"), [])
        data["provenance"] = load_json(data.pop("provenance_json"), [])
        return data

    def _edge_from_row(self, row) -> dict:
        data = dict(row)
        data["provenance"] = load_json(data.pop("provenance_json"), [])
        return data
