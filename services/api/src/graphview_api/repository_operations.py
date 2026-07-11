from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, delete, insert, or_, select, update

from graphview_api import db
from graphview_api.json_compat import normalize_json_row
from graphview_api.schemas import ExportBundle

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


class DataOperationsRepositoryMixin:
    """Search, export, complete backup, and inert restore persistence operations."""

    def search(self, query: str, graph_id: str | None = None) -> dict[str, list[dict]]:
        like = f"%{query}%"
        spec = self._graph_view_spec(graph_id)
        with self.engine.begin() as conn:
            sources = [
                self._source_from_row(row)
                for row in conn.execute(
                    select(db.sources).where(
                        and_(
                            db.sources.c.project_id == spec.project_id,
                            or_(db.sources.c.title.like(like), db.sources.c.uri.like(like)),
                        )
                    )
                ).mappings()
            ]
            if spec.source_ids:
                source_id_set = set(spec.source_ids)
                sources = [source for source in sources if source["id"] in source_id_set]
            nodes = [
                self._node_from_row(row)
                for row in conn.execute(
                    select(db.content_nodes).where(
                        and_(
                            db.content_nodes.c.project_id == spec.project_id,
                            or_(db.content_nodes.c.label.like(like), db.content_nodes.c.summary.like(like)),
                        )
                    )
                ).mappings()
            ]
            if spec.source_ids:
                nodes = [node for node in nodes if self._item_matches_sources(node, spec.source_ids)]
        return {"sources": sources, "nodes": nodes}

    def export_bundle(self, graph_id: str | None = None, *, include_agent_context_content: bool = False) -> dict:
        from graphview_api.api_v1.repository import GraphProjectionRepository

        spec = self._graph_view_spec(graph_id)
        project, nodes, edges = self.graph(graph_id)
        proposals = self.list_proposals(graph_id=graph_id)
        proposal_ids = {proposal["id"] for proposal in proposals}
        projection = GraphProjectionRepository(self)
        graph_version = projection.graph_version(spec.project_id) if not spec.source_ids else None
        graph_layouts = projection.list_layouts(spec.project_id, include_positions=True) if not spec.source_ids else []
        with self.engine.begin() as conn:
            exported_at = now()
            source_ids = {source["id"] for source in self.list_sources(graph_id=graph_id)}
            return {
                "project": project,
                "sources": self.list_sources(graph_id=graph_id),
                "topics": [
                    self._topic_from_row(row)
                    for row in conn.execute(
                        select(db.topics).where(db.topics.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "nodes": nodes,
                "edges": edges,
                "ingestion_runs": [
                    normalize_json_row(row)
                    for row in conn.execute(
                        select(db.ingestion_runs).where(db.ingestion_runs.c.project_id == spec.project_id)
                    ).mappings()
                    if not spec.source_ids or row["source_id"] in set(spec.source_ids)
                ],
                "proposals": proposals,
                "embeddings": [
                    self._embedding_from_row(row)
                    for row in conn.execute(
                        select(db.content_embeddings).where(db.content_embeddings.c.project_id == spec.project_id)
                    ).mappings()
                    if row["proposal_id"] in proposal_ids
                ],
                "review_decisions": [
                    self._decision_from_row(row)
                    for row in conn.execute(
                        select(db.review_decisions).where(db.review_decisions.c.project_id == spec.project_id)
                    ).mappings()
                    if row["proposal_id"] in proposal_ids
                ],
                "connector_accounts": self.list_connector_accounts() if spec.project_id == DEFAULT_PROJECT_ID else [],
                "connector_targets": self.list_connector_targets() if spec.project_id == DEFAULT_PROJECT_ID else [],
                "connector_sync_runs": self.list_connector_sync_runs() if spec.project_id == DEFAULT_PROJECT_ID else [],
                "source_chunks": [
                    self._source_chunk_from_row(row)
                    for row in conn.execute(
                        select(db.source_chunks).where(db.source_chunks.c.project_id == spec.project_id)
                    ).mappings()
                    if row["source_id"] in source_ids
                ],
                "graph_version": graph_version,
                "graph_layouts": graph_layouts,
                "graph_settings": self.graph_settings() if spec.project_id == DEFAULT_PROJECT_ID else None,
                "planning_sessions": [
                    self._planning_session_from_row(row)
                    for row in conn.execute(
                        select(db.planning_sessions).where(db.planning_sessions.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_runs": [
                    self.get_agent_run(row["id"]) or self._agent_run_from_row(row)
                    for row in conn.execute(
                        select(db.agent_runs).where(db.agent_runs.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "research_tasks": [
                    self._research_task_from_row(row)
                    for row in conn.execute(
                        select(db.research_tasks).where(db.research_tasks.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_action_proposals": [
                    self._agent_action_proposal_from_row(row)
                    for row in conn.execute(
                        select(db.agent_action_proposals).where(db.agent_action_proposals.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "activity_events": [
                    event
                    for event in [
                        self._activity_event_from_row(row)
                        for row in conn.execute(
                            select(db.graph_activity_events)
                            .where(db.graph_activity_events.c.project_id == spec.project_id)
                            .order_by(db.graph_activity_events.c.created_at.desc(), db.graph_activity_events.c.id.desc())
                        ).mappings()
                    ]
                    if not spec.source_ids or self._activity_event_matches_scope(event, spec.source_ids)
                ],
                "signals": [
                    self._signal_from_row(row)
                    for row in conn.execute(
                        select(db.signals).where(db.signals.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "observations": [
                    self._observation_from_row(row)
                    for row in conn.execute(
                        select(db.observations).where(db.observations.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "owners": [
                    self._owner_from_row(row)
                    for row in conn.execute(select(db.owners).where(db.owners.c.project_id == spec.project_id)).mappings()
                ],
                "routing_policies": [
                    self._routing_policy_from_row(row)
                    for row in conn.execute(
                        select(db.routing_policies).where(db.routing_policies.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "alerts": [
                    self._alert_from_row(row)
                    for row in conn.execute(select(db.alerts).where(db.alerts.c.project_id == spec.project_id)).mappings()
                ],
                "attention_items": [
                    self._attention_item_from_row(row)
                    for row in conn.execute(
                        select(db.attention_items).where(db.attention_items.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "decision_records": [
                    self._decision_record_from_row(row)
                    for row in conn.execute(
                        select(db.decision_records).where(db.decision_records.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "action_proposals": [
                    self._action_proposal_from_row(row)
                    for row in conn.execute(
                        select(db.action_proposals).where(db.action_proposals.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "action_runs": [
                    self._action_run_from_row(row)
                    for row in conn.execute(select(db.action_runs).where(db.action_runs.c.project_id == spec.project_id)).mappings()
                ],
                "outcomes": [
                    self._outcome_from_row(row)
                    for row in conn.execute(select(db.outcomes).where(db.outcomes.c.project_id == spec.project_id)).mappings()
                ],
                "feedback_events": [
                    self._feedback_event_from_row(row)
                    for row in conn.execute(
                        select(db.feedback_events).where(db.feedback_events.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_clients": [
                    self._agent_context_client_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_clients).where(db.agent_context_clients.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_sessions": [
                    self._agent_context_session_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_sessions).where(db.agent_context_sessions.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_artifacts": [
                    self._agent_context_artifact_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_artifacts).where(db.agent_context_artifacts.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_blobs": [
                    self._agent_context_blob_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_blobs).where(db.agent_context_blobs.c.project_id == spec.project_id)
                    ).mappings()
                ],
                "agent_context_blob_contents": [
                    {
                        "blob_id": row["id"],
                        "encrypted_content": envelope,
                        "exported_at": exported_at,
                    }
                    for row in conn.execute(
                        select(db.agent_context_blobs).where(
                            and_(
                                db.agent_context_blobs.c.project_id == spec.project_id,
                                or_(
                                    db.agent_context_blobs.c.encrypted_content.is_not(None),
                                    db.agent_context_blobs.c.object_key.is_not(None),
                                ),
                            )
                        )
                    ).mappings()
                    if (envelope := self._agent_context_blob_envelope(row))
                ]
                if include_agent_context_content
                else [],
                "agent_context_events": [
                    self._agent_context_event_from_row(row)
                    for row in conn.execute(
                        select(db.agent_context_events).where(db.agent_context_events.c.project_id == spec.project_id)
                    ).mappings()
                ],
            }

    def backup_bundle(self, actor_id: str, *, include_agent_context_content: bool = False) -> dict:
        bundle = self.export_bundle(include_agent_context_content=include_agent_context_content)
        return {
            "metadata": {
                "schema_version": 1,
                "created_at": now(),
                "created_by": actor_id,
                "project_id": bundle["project"]["id"],
                "source_count": len(bundle["sources"]),
                "node_count": len(bundle["nodes"]),
                "edge_count": len(bundle["edges"]),
                "proposal_count": len(bundle["proposals"]),
                "agent_context_session_count": len(bundle.get("agent_context_sessions", [])),
                "agent_context_content_blob_count": len(bundle.get("agent_context_blob_contents", [])),
            },
            "bundle": bundle,
        }

    def restore_bundle(self, bundle: ExportBundle, *, actor_id: str = "system-restore") -> dict:
        project_id = bundle.project.id
        restore_timestamp = now()
        with self.engine.begin() as conn:
            conn.execute(
                delete(db.upload_parts).where(
                    db.upload_parts.c.session_id.in_(
                        select(db.upload_sessions.c.id).where(db.upload_sessions.c.project_id == project_id)
                    )
                )
            )
            conn.execute(
                delete(db.graph_layout_positions).where(
                    db.graph_layout_positions.c.layout_id.in_(
                        select(db.graph_layouts.c.id).where(db.graph_layouts.c.project_id == project_id)
                    )
                )
            )
            conn.execute(
                update(db.durable_jobs)
                .where(
                    and_(
                        db.durable_jobs.c.project_id == project_id,
                        db.durable_jobs.c.status.in_(["queued", "retry", "running", "cancelling"]),
                    )
                )
                .values(
                    status="cancelled",
                    leased_until=None,
                    worker_id=None,
                    error_code="RestoreSuppressed",
                    error="Suppressed during logical restore",
                    updated_at=restore_timestamp,
                    finished_at=restore_timestamp,
                )
            )
            conn.execute(
                update(db.event_outbox)
                .where(and_(db.event_outbox.c.project_id == project_id, db.event_outbox.c.status == "pending"))
                .values(status="suppressed", published_at=restore_timestamp)
            )
            for table in [
                db.agent_context_events,
                db.agent_context_blobs,
                db.agent_context_artifacts,
                db.agent_context_sessions,
                db.agent_context_clients,
                db.feedback_events,
                db.outcomes,
                db.action_runs,
                db.action_proposals,
                db.decision_records,
                db.attention_items,
                db.alerts,
                db.routing_policies,
                db.owners,
                db.observations,
                db.signals,
                db.graph_activity_events,
                db.agent_action_proposals,
                db.research_tasks,
                db.agent_steps,
                db.agent_runs,
                db.graph_build_specs,
                db.planning_messages,
                db.planning_sessions,
                db.review_decisions,
                db.content_embeddings,
                db.extraction_proposals,
                db.ingestion_runs,
                db.semantic_edges,
                db.content_nodes,
                db.source_chunks,
                db.sources,
                db.upload_sessions,
                db.connector_cursors,
                db.connector_sync_runs,
                db.connector_targets,
                db.connector_accounts,
                db.topics,
                db.graph_layouts,
                db.graph_versions,
                db.graph_settings,
            ]:
                conn.execute(delete(table).where(table.c.project_id == project_id))
            conn.execute(delete(db.graph_projects).where(db.graph_projects.c.id == project_id))

            conn.execute(insert(db.graph_projects).values(**bundle.project.model_dump()))
            connector_accounts = [
                {
                    "id": account.id,
                    "project_id": account.project_id,
                    "kind": account.kind,
                    "display_name": account.display_name,
                    "status": "error",
                    "created_by": account.created_by,
                    "encrypted_token_json": None,
                    "scopes_json": dump_json(account.scopes),
                    "settings_json": dump_json(account.settings),
                    "created_at": account.created_at,
                    "updated_at": restore_timestamp,
                }
                for account in bundle.connector_accounts
            ]
            connector_targets = [
                {
                    "id": target.id,
                    "project_id": target.project_id,
                    "account_id": target.account_id,
                    "connector_kind": target.connector_kind,
                    "target_type": target.target_type,
                    "remote_id": target.remote_id,
                    "title": target.title,
                    "parent_remote_id": target.parent_remote_id,
                    "sync_settings_json": dump_json(target.sync_settings),
                    "last_synced_at": target.last_synced_at,
                    "created_at": target.created_at,
                    "updated_at": restore_timestamp,
                }
                for target in bundle.connector_targets
            ]
            connector_sync_runs = [
                {
                    **sync_run.model_dump(),
                    "status": "failed" if sync_run.status == "running" else sync_run.status,
                    "stage": "restore_suppressed" if sync_run.status == "running" else sync_run.stage,
                    "error": "Suppressed during restore" if sync_run.status == "running" else sync_run.error,
                    "finished_at": restore_timestamp if sync_run.status == "running" else sync_run.finished_at,
                }
                for sync_run in bundle.connector_sync_runs
            ]
            graph_version = bundle.graph_version.model_dump() if bundle.graph_version else None
            graph_layouts = [
                {
                    "id": layout.id,
                    "project_id": layout.project_id,
                    "name": layout.name,
                    "algorithm": layout.algorithm,
                    "graph_version": layout.graph_version,
                    "settings_json": dump_json(layout.settings),
                    "created_by": layout.created_by,
                    "created_at": layout.created_at,
                    "updated_at": layout.updated_at,
                }
                for layout in bundle.graph_layouts
            ]
            graph_layout_positions = [
                {
                    "layout_id": layout.id,
                    "node_id": position.node_id,
                    "x": position.x,
                    "y": position.y,
                    "z": position.z,
                    "cluster_key": position.cluster_key,
                }
                for layout in bundle.graph_layouts
                for position in layout.positions
            ]
            sources = []
            for source in bundle.sources:
                dumped = source.model_dump()
                dumped["metadata_json"] = dump_json(dumped.pop("metadata") or {})
                sources.append(dumped)
            topics = [topic.model_dump() for topic in bundle.topics]
            nodes = [
                {
                    "id": node.id,
                    "project_id": node.project_id,
                    "label": node.label,
                    "kind": node.kind,
                    "summary": node.summary,
                    "topic_ids_json": dump_json(node.topic_ids),
                    "metadata_json": dump_json(node.metadata or {}),
                    "provenance_json": dump_json(node.provenance),
                    "created_at": node.created_at,
                    "updated_at": node.updated_at,
                }
                for node in bundle.nodes
            ]
            edges = [
                {
                    "id": edge.id,
                    "project_id": edge.project_id,
                    "source_node_id": edge.source_node_id,
                    "target_node_id": edge.target_node_id,
                    "relation": edge.relation,
                    "weight": edge.weight,
                    "metadata_json": dump_json(edge.metadata or {}),
                    "provenance_json": dump_json(edge.provenance),
                    "created_at": edge.created_at,
                    "updated_at": edge.updated_at,
                }
                for edge in bundle.edges
            ]
            ingestion_runs = [
                {
                    **run.model_dump(),
                    "status": "cancelled" if run.status in {"queued", "running"} else run.status,
                    "finished_at": restore_timestamp if run.status in {"queued", "running"} else run.finished_at,
                    "error_code": "RestoreSuppressed" if run.status in {"queued", "running"} else run.error_code,
                }
                for run in bundle.ingestion_runs
            ]
            proposals = [
                {
                    "id": proposal.id,
                    "project_id": proposal.project_id,
                    "ingestion_run_id": proposal.ingestion_run_id,
                    "kind": proposal.kind,
                    "status": proposal.status,
                    "proposed_value_json": dump_json(proposal.proposed_value),
                    "confidence": proposal.confidence,
                    "provenance_json": dump_json(proposal.provenance),
                    "created_at": proposal.created_at,
                }
                for proposal in bundle.proposals
            ]
            embeddings = [
                {
                    "id": embedding.id,
                    "project_id": embedding.project_id,
                    "proposal_id": embedding.proposal_id,
                    "content_node_id": embedding.content_node_id,
                    "embedding_model": embedding.embedding_model,
                    "vector_json": dump_json(embedding.vector),
                    "created_at": embedding.created_at,
                }
                for embedding in bundle.embeddings
            ]
            review_decisions = [
                {
                    "id": decision.id,
                    "project_id": decision.project_id,
                    "proposal_id": decision.proposal_id,
                    "reviewer_id": decision.reviewer_id,
                    "decision": decision.decision,
                    "edited_value_json": dump_json(decision.edited_value) if decision.edited_value is not None else None,
                    "rationale": decision.rationale,
                    "decided_at": decision.decided_at,
                }
                for decision in bundle.review_decisions
            ]
            source_chunks = [
                {
                    "id": chunk.id,
                    "project_id": chunk.project_id,
                    "source_id": chunk.source_id,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "heading_path_json": dump_json(chunk.heading_path),
                    "block_type": chunk.block_type,
                    "ordinal": chunk.ordinal,
                    "text": chunk.text,
                    "links_json": dump_json(chunk.links),
                    "mentions_json": dump_json(chunk.mentions),
                    "checksum": chunk.checksum,
                    "locator": chunk.locator,
                    "created_at": chunk.created_at,
                }
                for chunk in bundle.source_chunks
            ]
            graph_settings = None
            if bundle.graph_settings:
                graph_settings = bundle.graph_settings.model_dump()
                graph_settings["settings_json"] = dump_json(graph_settings.pop("settings") or {})
            planning_sessions = [
                {
                    "id": session.id,
                    "project_id": session.project_id,
                    "graph_id": session.graph_id,
                    "lens": session.lens,
                    "title": session.title,
                    "goal": session.goal,
                    "status": session.status,
                    "provider": session.provider,
                    "model": session.model,
                    "created_by": session.created_by,
                    "metadata_json": dump_json(session.metadata),
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                }
                for session in bundle.planning_sessions
            ]
            planning_messages = [
                {
                    "id": message.id,
                    "project_id": message.project_id,
                    "session_id": message.session_id,
                    "agent_run_id": message.agent_run_id,
                    "role": message.role,
                    "content": message.content,
                    "provider": message.provider,
                    "model": message.model,
                    "metadata_json": dump_json(message.metadata),
                    "created_at": message.created_at,
                }
                for session in bundle.planning_sessions
                for message in session.messages
            ]
            graph_build_specs = [
                {
                    "id": spec.id,
                    "project_id": spec.project_id,
                    "session_id": spec.session_id,
                    "version": spec.version,
                    "title": spec.title,
                    "objective": spec.objective,
                    "status": spec.status,
                    "spec_json": dump_json(spec.spec),
                    "created_at": spec.created_at,
                    "updated_at": spec.updated_at,
                }
                for session in bundle.planning_sessions
                for spec in ([session.build_spec] if session.build_spec else [])
            ]
            agent_runs = [
                {
                    "id": run.id,
                    "project_id": run.project_id,
                    "planning_session_id": run.planning_session_id,
                    "kind": run.kind,
                    "status": "cancelled" if run.status in {"queued", "running"} else run.status,
                    "provider": run.provider,
                    "model": run.model,
                    "input_json": dump_json(run.input),
                    "output_json": dump_json(run.output),
                    "trace_id": run.trace_id,
                    "created_by": run.created_by,
                    "started_at": run.started_at,
                    "finished_at": restore_timestamp if run.status in {"queued", "running"} else run.finished_at,
                    "error": "Suppressed during restore" if run.status in {"queued", "running"} else run.error,
                }
                for run in bundle.agent_runs
            ]
            agent_steps = [
                {
                    "id": step.id,
                    "project_id": step.project_id,
                    "agent_run_id": step.agent_run_id,
                    "name": step.name,
                    "status": "failed" if step.status == "running" else step.status,
                    "input_summary": step.input_summary,
                    "output_summary": step.output_summary,
                    "error": "Suppressed during restore" if step.status == "running" else step.error,
                    "trace_id": step.trace_id,
                    "metadata_json": dump_json(step.metadata),
                    "started_at": step.started_at,
                    "finished_at": restore_timestamp if step.status == "running" else step.finished_at,
                }
                for run in bundle.agent_runs
                for step in run.steps
            ]
            research_tasks = [
                {
                    "id": task.id,
                    "project_id": task.project_id,
                    "agent_run_id": task.agent_run_id,
                    "planning_session_id": task.planning_session_id,
                    "query": task.query,
                    "status": "failed" if task.status in {"queued", "running"} else task.status,
                    "provider": task.provider,
                    "model": task.model,
                    "source_policy": task.source_policy,
                    "idempotency_key": task.idempotency_key,
                    "result_json": dump_json({"restore_suppressed": True})
                    if task.status in {"queued", "running"}
                    else dump_json(task.result),
                    "created_by": task.created_by,
                    "created_at": task.created_at,
                    "updated_at": restore_timestamp if task.status in {"queued", "running"} else task.updated_at,
                }
                for task in bundle.research_tasks
            ]
            actions_by_id = {
                action.id: action
                for action in [
                    *bundle.agent_action_proposals,
                    *(action for run in bundle.agent_runs for action in run.action_proposals),
                ]
            }
            agent_action_proposals = [
                {
                    "id": action.id,
                    "project_id": action.project_id,
                    "agent_run_id": action.agent_run_id,
                    "action_type": action.action_type,
                    "status": action.status,
                    "title": action.title,
                    "summary": action.summary,
                    "payload_json": dump_json(action.payload),
                    "citations_json": dump_json(action.citations),
                    "confidence": action.confidence,
                    "created_at": action.created_at,
                    "updated_at": action.updated_at,
                    "applied_at": action.applied_at,
                }
                for action in actions_by_id.values()
            ]
            activity_events = [
                {
                    "id": event.id,
                    "project_id": event.project_id,
                    "event_type": event.event_type,
                    "actor_id": event.actor_id,
                    "summary": event.summary,
                    "object_refs_json": dump_json(event.object_refs),
                    "payload_json": dump_json(event.payload),
                    "lenses_json": dump_json(event.lenses),
                    "created_at": event.created_at,
                }
                for event in bundle.activity_events
            ]
            signals = [
                {
                    "id": signal.id,
                    "project_id": signal.project_id,
                    "graph_id": signal.graph_id,
                    "kind": signal.kind,
                    "status": signal.status,
                    "severity": signal.severity,
                    "source_kind": signal.source_kind,
                    "source_id": signal.source_id,
                    "title": signal.title,
                    "summary": signal.summary,
                    "payload_json": dump_json(signal.payload),
                    "checksum": signal.checksum,
                    "trace_id": signal.trace_id,
                    "actor_id": signal.actor_id,
                    "received_at": signal.received_at,
                    "created_at": signal.created_at,
                }
                for signal in bundle.signals
            ]
            observations = [
                {
                    "id": observation.id,
                    "project_id": observation.project_id,
                    "signal_id": observation.signal_id,
                    "kind": observation.kind,
                    "summary": observation.summary,
                    "confidence": observation.confidence,
                    "evidence_json": dump_json(observation.evidence),
                    "object_refs_json": dump_json([ref.model_dump() for ref in observation.object_refs]),
                    "source_ids_json": dump_json(observation.source_ids),
                    "node_ids_json": dump_json(observation.node_ids),
                    "edge_ids_json": dump_json(observation.edge_ids),
                    "metadata_json": dump_json(observation.metadata),
                    "created_at": observation.created_at,
                }
                for observation in bundle.observations
            ]
            owners = [
                {
                    "id": owner.id,
                    "project_id": owner.project_id,
                    "owner_type": owner.owner_type,
                    "display_name": owner.display_name,
                    "contact": owner.contact,
                    "scope_kind": owner.scope_kind,
                    "scope_id": owner.scope_id,
                    "escalation_contact": owner.escalation_contact,
                    "metadata_json": dump_json(owner.metadata),
                    "created_at": owner.created_at,
                    "updated_at": owner.updated_at,
                }
                for owner in bundle.owners
            ]
            routing_policies = [
                {
                    "id": policy.id,
                    "project_id": policy.project_id,
                    "name": policy.name,
                    "description": policy.description,
                    "enabled": policy.enabled,
                    "match_json": dump_json(policy.match),
                    "severity": policy.severity,
                    "owner_id": policy.owner_id,
                    "sla_seconds": policy.sla_seconds,
                    "suggested_actions_json": dump_json(policy.suggested_actions),
                    "approval_required": policy.approval_required,
                    "metadata_json": dump_json(policy.metadata),
                    "created_at": policy.created_at,
                    "updated_at": policy.updated_at,
                }
                for policy in bundle.routing_policies
            ]
            alerts = [
                {
                    "id": alert.id,
                    "project_id": alert.project_id,
                    "signal_id": alert.signal_id,
                    "observation_id": alert.observation_id,
                    "owner_id": alert.owner_id,
                    "policy_id": alert.policy_id,
                    "severity": alert.severity,
                    "status": alert.status,
                    "title": alert.title,
                    "summary": alert.summary,
                    "reason": alert.reason,
                    "object_refs_json": dump_json([ref.model_dump() for ref in alert.object_refs]),
                    "due_at": alert.due_at,
                    "created_at": alert.created_at,
                    "updated_at": alert.updated_at,
                }
                for alert in bundle.alerts
            ]
            suppressed_action_run_ids = {
                run.id for run in bundle.action_runs if run.status in {"queued", "running"}
            }
            attention_items = [
                {
                    "id": item.id,
                    "project_id": item.project_id,
                    "kind": item.kind,
                    "status": "blocked"
                    if item.action_run_id in suppressed_action_run_ids
                    and item.status in {"waiting_for_action", "waiting_for_outcome"}
                    else item.status,
                    "severity": item.severity,
                    "sla_status": item.sla_status,
                    "title": item.title,
                    "summary": item.summary,
                    "owner_id": item.owner_id,
                    "assignee_id": item.assignee_id,
                    "due_at": item.due_at,
                    "source_id": item.source_id,
                    "signal_id": item.signal_id,
                    "observation_id": item.observation_id,
                    "alert_id": item.alert_id,
                    "proposal_id": item.proposal_id,
                    "decision_record_id": item.decision_record_id,
                    "action_proposal_id": item.action_proposal_id,
                    "action_run_id": item.action_run_id,
                    "outcome_id": item.outcome_id,
                    "feedback_event_id": item.feedback_event_id,
                    "object_refs_json": dump_json([ref.model_dump() for ref in item.object_refs]),
                    "evidence_json": dump_json(item.evidence),
                    "suggested_actions_json": dump_json(item.suggested_actions),
                    "blockers_json": dump_json(item.blockers),
                    "created_at": item.created_at,
                    "updated_at": restore_timestamp
                    if item.action_run_id in suppressed_action_run_ids
                    else item.updated_at,
                    "resolved_at": item.resolved_at,
                }
                for item in bundle.attention_items
            ]
            decision_records = [
                {
                    "id": decision.id,
                    "project_id": decision.project_id,
                    "alert_id": decision.alert_id,
                    "attention_item_id": decision.attention_item_id,
                    "proposal_id": decision.proposal_id,
                    "decision": decision.decision,
                    "rationale": decision.rationale,
                    "actor_id": decision.actor_id,
                    "evidence_json": dump_json(decision.evidence),
                    "object_refs_json": dump_json([ref.model_dump() for ref in decision.object_refs]),
                    "created_at": decision.created_at,
                }
                for decision in bundle.decision_records
            ]
            action_proposals = [
                {
                    "id": action.id,
                    "project_id": action.project_id,
                    "decision_record_id": action.decision_record_id,
                    "alert_id": action.alert_id,
                    "attention_item_id": action.attention_item_id,
                    "action_type": action.action_type,
                    "status": "cancelled"
                    if action.status in {"approved", "queued", "running"}
                    else action.status,
                    "title": action.title,
                    "summary": action.summary,
                    "payload_json": dump_json(action.redacted_payload),
                    "redacted_payload_json": dump_json(action.redacted_payload),
                    "safety_json": dump_json(action.safety.model_dump()),
                    "approval_required": action.approval_required,
                    "created_by": action.created_by,
                    "approved_by": action.approved_by,
                    "rejected_by": action.rejected_by,
                    "rationale": action.rationale,
                    "created_at": action.created_at,
                    "updated_at": restore_timestamp
                    if action.status in {"approved", "queued", "running"}
                    else action.updated_at,
                    "decided_at": action.decided_at,
                }
                for action in bundle.action_proposals
            ]
            action_runs = [
                {
                    "id": run.id,
                    "project_id": run.project_id,
                    "action_proposal_id": run.action_proposal_id,
                    "action_type": run.action_type,
                    "status": "cancelled" if run.status in {"queued", "running"} else run.status,
                    "executor_id": run.executor_id,
                    "target": run.target,
                    "payload_json": dump_json(run.redacted_payload),
                    "redacted_payload_json": dump_json(run.redacted_payload),
                    "external_id": run.external_id,
                    "trace_id": run.trace_id,
                    "error_code": "RestoreSuppressed"
                    if run.status in {"queued", "running"}
                    else run.error_code,
                    "error": "Suppressed during restore"
                    if run.status in {"queued", "running"}
                    else run.error,
                    "started_at": run.started_at,
                    "finished_at": restore_timestamp
                    if run.status in {"queued", "running"}
                    else run.finished_at,
                }
                for run in bundle.action_runs
            ]
            outcomes = [
                {
                    "id": outcome.id,
                    "project_id": outcome.project_id,
                    "action_run_id": outcome.action_run_id,
                    "attention_item_id": outcome.attention_item_id,
                    "alert_id": outcome.alert_id,
                    "status": outcome.status,
                    "title": outcome.title,
                    "summary": outcome.summary,
                    "result_json": dump_json(outcome.result),
                    "actor_id": outcome.actor_id,
                    "occurred_at": outcome.occurred_at,
                    "created_at": outcome.created_at,
                }
                for outcome in bundle.outcomes
            ]
            feedback_events = [
                {
                    "id": feedback.id,
                    "project_id": feedback.project_id,
                    "outcome_id": feedback.outcome_id,
                    "action_run_id": feedback.action_run_id,
                    "attention_item_id": feedback.attention_item_id,
                    "kind": feedback.kind,
                    "summary": feedback.summary,
                    "effect_json": dump_json(feedback.effect),
                    "proposed_value_json": dump_json(feedback.proposed_value) if feedback.proposed_value is not None else None,
                    "actor_id": feedback.actor_id,
                    "created_at": feedback.created_at,
                }
                for feedback in bundle.feedback_events
            ]
            agent_context_clients = [
                {
                    "id": client.id,
                    "project_id": client.project_id,
                    "display_name": client.display_name,
                    "runtime_kind": client.runtime_kind,
                    "status": "revoked",
                    "created_by": client.created_by,
                    "token_hash": "restored:revoked",
                    "scopes_json": dump_json(client.scopes),
                    "settings_json": dump_json(client.settings),
                    "created_at": client.created_at,
                    "updated_at": restore_timestamp,
                    "last_seen_at": client.last_seen_at,
                    "revoked_at": restore_timestamp,
                }
                for client in bundle.agent_context_clients
            ]
            agent_context_sessions = [
                {
                    "id": session.id,
                    "project_id": session.project_id,
                    "client_id": session.client_id,
                    "runtime_kind": session.runtime_kind,
                    "authority": session.authority,
                    "status": "cancelled" if session.status == "running" else session.status,
                    "title": session.title,
                    "workspace_root": session.workspace_root,
                    "repository_uri": session.repository_uri,
                    "branch": session.branch,
                    "commit_sha": session.commit_sha,
                    "metadata_json": dump_json(session.metadata),
                    "started_at": session.started_at,
                    "ended_at": restore_timestamp if session.status == "running" else session.ended_at,
                    "updated_at": restore_timestamp if session.status == "running" else session.updated_at,
                }
                for session in bundle.agent_context_sessions
            ]
            agent_context_artifacts = [
                {
                    "id": artifact.id,
                    "project_id": artifact.project_id,
                    "session_id": artifact.session_id,
                    "kind": artifact.kind,
                    "uri": artifact.uri,
                    "path": artifact.path,
                    "title": artifact.title,
                    "content_type": artifact.content_type,
                    "checksum": artifact.checksum,
                    "metadata_json": dump_json(artifact.metadata),
                    "created_at": artifact.created_at,
                    "updated_at": artifact.updated_at,
                }
                for artifact in bundle.agent_context_artifacts
            ]
            agent_context_blob_content_by_id = {
                content.blob_id: content.encrypted_content for content in bundle.agent_context_blob_contents
            }
            restored_blob_object_keys: dict[str, str] = {}
            if self.object_store is not None:
                for blob_id, envelope in agent_context_blob_content_by_id.items():
                    object_key = f"{bundle.project.id}/agent-context/restored/{blob_id}.gvenc"
                    self.object_store.put_bytes(
                        object_key,
                        envelope.encode("utf-8"),
                        content_type="application/vnd.graphview.encrypted-context",
                        checksum=hashlib.sha256(envelope.encode("utf-8")).hexdigest(),
                    )
                    restored_blob_object_keys[blob_id] = object_key
            agent_context_blobs = [
                {
                    "id": blob.id,
                    "project_id": blob.project_id,
                    "session_id": blob.session_id,
                    "artifact_id": blob.artifact_id,
                    "content_kind": blob.content_kind,
                    "media_type": blob.media_type,
                    "redaction_status": blob.redaction_status
                    if agent_context_blob_content_by_id.get(blob.id)
                    else "metadata_only",
                    "encryption_status": blob.encryption_status
                    if agent_context_blob_content_by_id.get(blob.id)
                    else "metadata_only",
                    "checksum": blob.checksum,
                    "byte_count": blob.byte_count,
                    "token_count": blob.token_count,
                    "encrypted_content": None
                    if blob.id in restored_blob_object_keys
                    else agent_context_blob_content_by_id.get(blob.id),
                    "object_key": restored_blob_object_keys.get(blob.id),
                    "metadata_json": dump_json(blob.metadata),
                    "created_at": blob.created_at,
                    "expires_at": blob.expires_at,
                }
                for blob in bundle.agent_context_blobs
            ]
            agent_context_events = [
                {
                    "id": event.id,
                    "project_id": event.project_id,
                    "session_id": event.session_id,
                    "client_event_id": event.client_event_id,
                    "sequence": event.sequence,
                    "event_kind": event.event_kind,
                    "authority": event.authority,
                    "status": event.status,
                    "summary": event.summary,
                    "checksum": event.checksum,
                    "artifact_id": event.artifact_id,
                    "blob_id": event.blob_id,
                    "payload_json": dump_json(event.payload),
                    "object_refs_json": dump_json(event.object_refs),
                    "occurred_at": event.occurred_at,
                    "received_at": event.received_at,
                }
                for event in bundle.agent_context_events
            ]

            if graph_version:
                conn.execute(insert(db.graph_versions).values(**graph_version))
            for table, rows in [
                (db.topics, topics),
                (db.connector_accounts, connector_accounts),
                (db.connector_targets, connector_targets),
                (db.connector_sync_runs, connector_sync_runs),
                (db.graph_layouts, graph_layouts),
                (db.sources, sources),
                (db.source_chunks, source_chunks),
                (db.content_nodes, nodes),
                (db.graph_layout_positions, graph_layout_positions),
                (db.semantic_edges, edges),
                (db.ingestion_runs, ingestion_runs),
                (db.extraction_proposals, proposals),
                (db.content_embeddings, embeddings),
                (db.review_decisions, review_decisions),
                (db.planning_sessions, planning_sessions),
                (db.graph_build_specs, graph_build_specs),
                (db.agent_runs, agent_runs),
                (db.agent_steps, agent_steps),
                (db.planning_messages, planning_messages),
                (db.research_tasks, research_tasks),
                (db.agent_action_proposals, agent_action_proposals),
                (db.graph_activity_events, activity_events),
                (db.signals, signals),
                (db.observations, observations),
                (db.owners, owners),
                (db.routing_policies, routing_policies),
                (db.alerts, alerts),
                (db.attention_items, attention_items),
                (db.decision_records, decision_records),
                (db.action_proposals, action_proposals),
                (db.action_runs, action_runs),
                (db.outcomes, outcomes),
                (db.feedback_events, feedback_events),
                (db.agent_context_clients, agent_context_clients),
                (db.agent_context_sessions, agent_context_sessions),
                (db.agent_context_artifacts, agent_context_artifacts),
                (db.agent_context_blobs, agent_context_blobs),
                (db.agent_context_events, agent_context_events),
            ]:
                if rows:
                    conn.execute(insert(table), rows)
            if graph_settings:
                conn.execute(insert(db.graph_settings).values(**graph_settings))
            elif project_id == DEFAULT_PROJECT_ID:
                timestamp = now()
                conn.execute(
                    insert(db.graph_settings).values(
                        project_id=DEFAULT_PROJECT_ID,
                        llm_enabled=False,
                        llm_provider="openai-compatible",
                        llm_model=None,
                        auto_commit_threshold=self.auto_commit_threshold,
                        settings_json=dump_json({}),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )

            conn.execute(
                insert(db.audit_events).values(
                    id=new_id("audit"),
                    project_id=project_id,
                    actor_id=actor_id,
                    action="project.restore",
                    resource_type="project",
                    resource_id=project_id,
                    outcome="succeeded",
                    summary="Restored a logical project bundle with side effects suppressed.",
                    metadata_json=dump_json(
                        {
                            "source_count": len(bundle.sources),
                            "node_count": len(bundle.nodes),
                            "edge_count": len(bundle.edges),
                            "layout_count": len(bundle.graph_layouts),
                            "connector_account_count": len(bundle.connector_accounts),
                        }
                    ),
                    trace_id=new_id("trace"),
                    occurred_at=restore_timestamp,
                )
            )

        return self.export_bundle()
