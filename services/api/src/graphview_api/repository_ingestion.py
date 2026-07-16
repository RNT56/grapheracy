from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, delete, insert, select, update

from graphview_api import db
from graphview_api.connectors import NormalizedSourceDocument, stable_id
from graphview_api.json_compat import json_value
from graphview_api.schemas import SourceCreate


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


class IngestionRepositoryMixin:
    """Atomic source ingestion, connector delta, proposal, embedding, and tombstone writes."""

    def create_ingestion_result(
        self,
        *,
        source_payload: SourceCreate,
        generated_proposals: list[dict],
        embedding_model: str,
        embedding_vector: list[float],
        actor_id: str,
        source_text: str | None = None,
        graph_id: str | None = None,
    ) -> dict:
        spec = self._graph_view_spec(graph_id)
        timestamp = now()
        source = {
            "id": new_id("src"),
            "project_id": spec.project_id,
            **self._source_values_from_payload(source_payload),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        ingestion_run = {
            "id": new_id("run"),
            "project_id": spec.project_id,
            "source_id": source["id"],
            "status": "proposal_ready",
            "stage": "propose",
            "trace_id": new_id("trace"),
            "started_at": timestamp,
            "finished_at": timestamp,
            "error_code": None,
        }
        generated_with_ids = self._assign_generated_graph_ids(generated_proposals)
        proposals: list[dict] = []
        embeddings: list[dict] = []
        for generated in generated_with_ids:
            provenance = [
                {
                    "sourceId": source["id"],
                    "sourceUri": source.get("uri"),
                    "locator": generated.get("locator"),
                    "extractedBy": "worker",
                    "actorId": actor_id,
                    "ingestionRunId": ingestion_run["id"],
                    "observedAt": timestamp.isoformat(),
                    "traceId": ingestion_run["trace_id"],
                }
            ]
            proposal = {
                "id": new_id("proposal"),
                "project_id": spec.project_id,
                "ingestion_run_id": ingestion_run["id"],
                "kind": generated.get("kind", "content_node"),
                "status": "pending_review",
                "proposed_value_json": dump_json(generated["proposed_value"]),
                "confidence": generated.get("confidence"),
                "provenance_json": dump_json(provenance),
                "created_at": timestamp,
            }
            embedding = {
                "id": new_id("embedding"),
                "project_id": spec.project_id,
                "proposal_id": proposal["id"],
                "content_node_id": None,
                "embedding_model": embedding_model,
                "vector_json": dump_json(embedding_vector),
                "created_at": timestamp,
            }
            proposals.append(proposal)
            embeddings.append(embedding)
        with self.engine.begin() as conn:
            conn.execute(insert(db.sources).values(**source))
            conn.execute(insert(db.ingestion_runs).values(**ingestion_run))
            chunk_rows = self._source_chunk_rows(
                project_id=spec.project_id,
                source_id=source["id"],
                source_title=source["title"],
                source_text=source_text,
                timestamp=timestamp,
            )
            if chunk_rows:
                conn.execute(insert(db.source_chunks), chunk_rows)
            if proposals:
                conn.execute(insert(db.extraction_proposals), proposals)
                conn.execute(insert(db.content_embeddings), embeddings)
            proposal_outputs = [self._proposal_from_row(proposal) for proposal in proposals]
            activity_lenses = self._activity_lenses_for_proposals(proposal_outputs)
            self._record_activity_event(
                conn,
                project_id=spec.project_id,
                event_type="source.created",
                actor_id=actor_id,
                summary=f"Added source {source['title']}.",
                object_refs=[self._activity_ref("source", source["id"], source["title"])],
                payload={"source_id": source["id"], "kind": source["kind"]},
                lenses=activity_lenses,
                timestamp=timestamp,
            )
            self._record_activity_event(
                conn,
                project_id=spec.project_id,
                event_type="ingestion.proposal_ready",
                actor_id=actor_id,
                summary=f"Ingested {source['title']} and generated {len(proposals)} proposals.",
                object_refs=[
                    self._activity_ref("source", source["id"], source["title"]),
                    self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run["stage"]),
                ],
                payload={
                    "source_id": source["id"],
                    "ingestion_run_id": ingestion_run["id"],
                    "proposal_count": len(proposals),
                    "chunk_count": len(chunk_rows),
                },
                lenses=activity_lenses,
                timestamp=timestamp,
            )
            for proposal in proposal_outputs:
                self._record_proposal_created_activity(
                    conn,
                    proposal=proposal,
                    source=self._source_from_row(source),
                    ingestion_run=ingestion_run,
                    actor_id=actor_id,
                    timestamp=timestamp,
                )
        return {
            "source": self._source_from_row(source),
            "ingestion_run": ingestion_run,
            "proposals": proposal_outputs,
            "embeddings": [self._embedding_from_row(embedding) for embedding in embeddings],
        }

    def _source_chunk_rows(
        self,
        *,
        project_id: str,
        source_id: str,
        source_title: str,
        source_text: str | None,
        timestamp: datetime,
    ) -> list[dict]:
        if not source_text or not source_text.strip():
            return []
        blocks = [block.strip() for block in source_text.strip().split("\n\n") if block.strip()]
        if len(blocks) == 1:
            blocks = [line.strip() for line in source_text.strip().splitlines() if line.strip()] or blocks
        rows = []
        active_heading = source_title
        for ordinal, block in enumerate(blocks):
            block_type = "heading" if block.startswith("#") else "paragraph"
            text_value = block.lstrip("# ").strip() if block_type == "heading" else block
            if block_type == "heading":
                active_heading = text_value
            rows.append(
                {
                    "id": new_id("chunk"),
                    "project_id": project_id,
                    "source_id": source_id,
                    "parent_chunk_id": None,
                    "heading_path_json": dump_json([active_heading]),
                    "block_type": block_type,
                    "ordinal": ordinal,
                    "text": text_value,
                    "links_json": dump_json(self._links_from_text(text_value)),
                    "mentions_json": dump_json(self._mentions_from_text(text_value)),
                    "checksum": hashlib.sha256(f"{source_id}:{ordinal}:{text_value}".encode("utf-8")).hexdigest(),
                    "locator": f"{source_id}#block-{ordinal + 1}",
                    "created_at": timestamp,
                }
            )
        return rows

    def _links_from_text(self, text_value: str) -> list[str]:
        return [word.rstrip(".,)") for word in text_value.split() if word.startswith(("http://", "https://"))]

    def _mentions_from_text(self, text_value: str) -> list[str]:
        return sorted({match.strip("@.,:;()[]") for match in text_value.split() if match.startswith("@")})

    def create_connector_sync_result(
        self,
        *,
        target_id: str,
        documents: list[NormalizedSourceDocument],
        generated_proposals_by_remote_id: dict[str, list[dict]],
        embedding_model: str,
        embedding_vectors_by_remote_id: dict[str, list[float]],
        actor_id: str,
        auto_commit_threshold: float | None = None,
        full_snapshot: bool = True,
        tombstone_remote_ids: set[str] | None = None,
    ) -> dict:
        timestamp = now()
        threshold = self.auto_commit_threshold if auto_commit_threshold is None else auto_commit_threshold
        sync_run = {
            "id": new_id("sync"),
            "project_id": "",
            "target_id": target_id,
            "status": "running",
            "stage": "connector.fetch",
            "source_count": 0,
            "chunk_count": 0,
            "proposal_count": 0,
            "auto_committed_count": 0,
            "error": None,
            "trace_id": new_id("trace"),
            "started_at": timestamp,
            "finished_at": None,
        }
        inserted_proposals: list[dict] = []
        inserted_embeddings: list[dict] = []
        source_outputs: list[dict] = []
        chunk_count = 0
        deleted_count = 0
        tombstone_remote_ids = tombstone_remote_ids or set()

        with self.engine.begin() as conn:
            target_row = conn.execute(
                select(db.connector_targets).where(db.connector_targets.c.id == target_id)
            ).mappings().first()
            if target_row is None:
                raise KeyError(target_id)
            project_id = target_row["project_id"]
            sync_run["project_id"] = project_id
            conn.execute(insert(db.connector_sync_runs).values(**sync_run))

            observed_remote_ids = {document.remote_id for document in documents}
            stale_timestamp = timestamp
            for row in conn.execute(
                select(db.sources).where(
                    and_(
                        db.sources.c.project_id == project_id,
                        db.sources.c.connector_kind == target_row["connector_kind"],
                    )
                )
            ).mappings():
                source_metadata = load_json(json_value(row, "metadata_json"), {})
                should_stale = (
                    source_metadata.get("targetId") == target_id
                    and row["remote_id"]
                    and ((full_snapshot and row["remote_id"] not in observed_remote_ids) or row["remote_id"] in tombstone_remote_ids)
                )
                if should_stale:
                    conn.execute(
                        update(db.sources)
                        .where(db.sources.c.id == row["id"])
                        .values(stale_at=stale_timestamp, updated_at=timestamp)
                    )
                    deleted_count += 1

            for document in documents:
                source = self._upsert_connector_source(conn, document, timestamp, target_id=target_id)
                source_outputs.append(source)
                conn.execute(delete(db.source_chunks).where(db.source_chunks.c.source_id == source["id"]))
                chunk_id_by_key: dict[str, str] = {}
                chunk_rows = []
                for chunk in document.chunks:
                    chunk_id = stable_id("chunk", source["id"], chunk.stable_key)
                    chunk_id_by_key[chunk.stable_key] = chunk_id
                    chunk_rows.append(
                        {
                            "id": chunk_id,
                            "project_id": project_id,
                            "source_id": source["id"],
                            "parent_chunk_id": chunk_id_by_key.get(chunk.parent_stable_key or ""),
                            "heading_path_json": dump_json(chunk.heading_path),
                            "block_type": chunk.block_type,
                            "ordinal": chunk.ordinal,
                            "text": chunk.text,
                            "links_json": dump_json(chunk.links),
                            "mentions_json": dump_json(chunk.mentions),
                            "checksum": chunk.checksum,
                            "locator": chunk.locator,
                            "created_at": timestamp,
                        }
                    )
                    self._ensure_topics_for_heading_path(conn, chunk.heading_path, timestamp)
                if chunk_rows:
                    conn.execute(insert(db.source_chunks), chunk_rows)
                    chunk_count += len(chunk_rows)

                ingestion_run = {
                    "id": new_id("run"),
                    "project_id": project_id,
                    "source_id": source["id"],
                    "status": "proposal_ready",
                    "stage": "propose",
                    "trace_id": sync_run["trace_id"],
                    "started_at": timestamp,
                    "finished_at": timestamp,
                    "error_code": None,
                }
                conn.execute(insert(db.ingestion_runs).values(**ingestion_run))

                generated = self._assign_generated_graph_ids(generated_proposals_by_remote_id.get(document.remote_id, []))
                document_inserted_proposals: list[dict] = []
                for proposal_input in generated:
                    value = dict(proposal_input["proposed_value"])
                    if self._proposal_value_exists(conn, proposal_input.get("kind", "content_node"), value):
                        continue
                    provenance = [
                        {
                            "sourceId": source["id"],
                            "sourceUri": source.get("uri"),
                            "locator": proposal_input.get("locator"),
                            "extractedBy": "worker",
                            "actorId": actor_id,
                            "ingestionRunId": ingestion_run["id"],
                            "observedAt": timestamp.isoformat(),
                            "traceId": sync_run["trace_id"],
                            "connectorKind": document.connector_kind,
                            "remoteId": document.remote_id,
                        }
                    ]
                    proposal = {
                        "id": new_id("proposal"),
                        "project_id": project_id,
                        "ingestion_run_id": ingestion_run["id"],
                        "kind": proposal_input.get("kind", "content_node"),
                        "status": "pending_review",
                        "proposed_value_json": dump_json(value),
                        "confidence": proposal_input.get("confidence"),
                        "provenance_json": dump_json(provenance),
                        "created_at": timestamp,
                    }
                    embedding = {
                        "id": new_id("embedding"),
                        "project_id": project_id,
                        "proposal_id": proposal["id"],
                        "content_node_id": None,
                        "embedding_model": embedding_model,
                        "vector_json": dump_json(embedding_vectors_by_remote_id.get(document.remote_id, [])),
                        "created_at": timestamp,
                    }
                    conn.execute(insert(db.extraction_proposals).values(**proposal))
                    conn.execute(insert(db.content_embeddings).values(**embedding))
                    inserted_proposals.append(proposal)
                    document_inserted_proposals.append(proposal)
                    inserted_embeddings.append(embedding)

                proposal_outputs = [self._proposal_from_row(proposal) for proposal in document_inserted_proposals]
                activity_lenses = self._activity_lenses_for_proposals(proposal_outputs)
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="source.synced",
                    actor_id=actor_id,
                    summary=f"Synced source {source['title']}.",
                    object_refs=[
                        self._activity_ref("source", source["id"], source["title"]),
                        self._activity_ref("connector_target", target_id, target_row["title"]),
                    ],
                    payload={
                        "source_id": source["id"],
                        "target_id": target_id,
                        "remote_id": document.remote_id,
                        "connector_kind": document.connector_kind,
                    },
                    lenses=activity_lenses,
                    timestamp=timestamp,
                )
                self._record_activity_event(
                    conn,
                    project_id=project_id,
                    event_type="ingestion.proposal_ready",
                    actor_id=actor_id,
                    summary=f"Ingested {source['title']} and generated {len(document_inserted_proposals)} proposals.",
                    object_refs=[
                        self._activity_ref("source", source["id"], source["title"]),
                        self._activity_ref("ingestion_run", ingestion_run["id"], ingestion_run["stage"]),
                        self._activity_ref("connector_target", target_id, target_row["title"]),
                    ],
                    payload={
                        "source_id": source["id"],
                        "ingestion_run_id": ingestion_run["id"],
                        "proposal_count": len(document_inserted_proposals),
                    },
                    lenses=activity_lenses,
                    timestamp=timestamp,
                )
                for proposal in proposal_outputs:
                    self._record_proposal_created_activity(
                        conn,
                        proposal=proposal,
                        source=source,
                        ingestion_run=ingestion_run,
                        actor_id=actor_id,
                        timestamp=timestamp,
                    )

            auto_committed = self._auto_commit_inserted_proposals(conn, inserted_proposals, threshold)
            conn.execute(
                update(db.connector_sync_runs)
                .where(db.connector_sync_runs.c.id == sync_run["id"])
                .values(
                    status="completed",
                    stage="review.commit",
                    source_count=len(source_outputs),
                    chunk_count=chunk_count,
                    proposal_count=len(inserted_proposals),
                    auto_committed_count=auto_committed,
                    finished_at=now(),
                )
            )
            conn.execute(
                update(db.connector_targets)
                .where(db.connector_targets.c.id == target_id)
                .values(last_synced_at=timestamp, updated_at=timestamp)
            )
            self._record_activity_event(
                conn,
                project_id=project_id,
                event_type="connector.sync_completed",
                actor_id=actor_id,
                summary=f"Completed connector sync for {target_row['title']}.",
                object_refs=[
                    self._activity_ref("connector_sync_run", sync_run["id"], "completed"),
                    self._activity_ref("connector_target", target_id, target_row["title"]),
                ],
                payload={
                    "sync_run_id": sync_run["id"],
                    "target_id": target_id,
                    "source_count": len(source_outputs),
                    "chunk_count": chunk_count,
                    "proposal_count": len(inserted_proposals),
                    "auto_committed_count": auto_committed,
                },
                lenses=self._activity_lenses_for_proposals([self._proposal_from_row(proposal) for proposal in inserted_proposals]),
                timestamp=timestamp,
            )

        sync_run = self.get_connector_sync_run(sync_run["id"], project_id=project_id) or sync_run
        return {
            "sync_run": sync_run,
            "sources": source_outputs,
            "proposals": [self._proposal_from_row(proposal) for proposal in inserted_proposals],
            "embeddings": [self._embedding_from_row(embedding) for embedding in inserted_embeddings],
            "deleted_count": deleted_count,
        }
