from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, select, update

from graphview_api import db
from graphview_api.jobs.repository import JobRepository
from graphview_api.jobs.schemas import JobCreate


class ResumableUploadRepository:
    def __init__(self, engine, object_store):
        self.engine = engine
        self.object_store = object_store

    def create(
        self,
        *,
        project_id: str,
        graph_id: str | None,
        filename: str,
        title: str,
        content_type: str,
        expected_bytes: int,
        actor_id: str,
    ) -> dict:
        timestamp = datetime.now(tz=UTC)
        session_id = f"upload_{uuid4().hex[:20]}"
        object_key = f"{project_id}/uploads/{session_id}/{filename}"
        storage_upload_id = self.object_store.create_multipart(object_key, content_type=content_type)
        row = {
            "id": session_id,
            "project_id": project_id,
            "object_key": object_key,
            "storage_upload_id": storage_upload_id,
            "filename": filename,
            "content_type": content_type,
            "title": title,
            "graph_id": graph_id,
            "expected_bytes": expected_bytes,
            "received_bytes": 0,
            "status": "uploading",
            "actor_id": actor_id,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(db.upload_sessions).values(**row))
        except Exception:
            self.object_store.abort_multipart(object_key, storage_upload_id)
            raise
        return {**row, "job_id": None}

    def get(self, upload_id: str) -> dict | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                select(db.upload_sessions).where(db.upload_sessions.c.id == upload_id)
            ).mappings().first()
            return dict(row) if row else None

    def append(self, upload_id: str, *, offset: int, payload: bytes) -> dict:
        timestamp = datetime.now(tz=UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                select(db.upload_sessions)
                .where(db.upload_sessions.c.id == upload_id)
                .with_for_update()
            ).mappings().first()
            if row is None:
                raise KeyError(upload_id)
            if row["status"] == "completing" and row["received_bytes"] == row["expected_bytes"] == offset:
                result = {**dict(row), "job_id": None}
                should_finish = True
            elif row["status"] != "uploading":
                raise ValueError("Upload session is no longer writable")
            else:
                should_finish = False
            if should_finish:
                pass
            elif row["received_bytes"] != offset:
                raise RuntimeError(f"Upload offset mismatch; expected {row['received_bytes']}")
            elif not payload or offset + len(payload) > row["expected_bytes"]:
                raise ValueError("Upload part is empty or exceeds the declared length")
            if should_finish:
                parts = [
                    dict(part)
                    for part in connection.execute(
                        select(db.upload_parts)
                        .where(db.upload_parts.c.session_id == upload_id)
                        .order_by(db.upload_parts.c.part_number)
                    ).mappings()
                ]
            else:
                part_number = connection.execute(
                    select(db.upload_parts.c.part_number)
                    .where(db.upload_parts.c.session_id == upload_id)
                    .order_by(db.upload_parts.c.part_number.desc())
                    .limit(1)
                ).scalar_one_or_none()
                part_number = int(part_number or 0) + 1
                etag = self.object_store.upload_part(
                    row["object_key"], row["storage_upload_id"], part_number, payload
                )
                connection.execute(
                    insert(db.upload_parts).values(
                        session_id=upload_id,
                        part_number=part_number,
                        offset_bytes=offset,
                        size_bytes=len(payload),
                        etag=etag,
                        created_at=timestamp,
                    )
                )
                received = offset + len(payload)
                status = "completing" if received == row["expected_bytes"] else "uploading"
                connection.execute(
                    update(db.upload_sessions)
                    .where(db.upload_sessions.c.id == upload_id)
                    .values(received_bytes=received, status=status, updated_at=timestamp)
                )
                result = {**dict(row), "received_bytes": received, "status": status, "updated_at": timestamp, "job_id": None}
                if status == "completing":
                    parts = [
                        dict(part)
                        for part in connection.execute(
                            select(db.upload_parts)
                            .where(db.upload_parts.c.session_id == upload_id)
                            .order_by(db.upload_parts.c.part_number)
                        ).mappings()
                    ]
                else:
                    parts = []
        if result["status"] != "completing":
            return result
        if not self.object_store.exists(row["object_key"]):
            self.object_store.complete_multipart(row["object_key"], row["storage_upload_id"], parts)
        with self.engine.begin() as connection:
            current = connection.execute(
                select(db.upload_sessions).where(db.upload_sessions.c.id == upload_id).with_for_update()
            ).mappings().one()
            idempotency_key = f"resumable-upload:{upload_id}"
            if current["status"] == "completed":
                job_id = connection.execute(
                    select(db.durable_jobs.c.id).where(
                        and_(
                            db.durable_jobs.c.project_id == current["project_id"],
                            db.durable_jobs.c.idempotency_key == idempotency_key,
                        )
                    )
                ).scalar_one()
            else:
                job = JobRepository(self.engine).enqueue(
                    JobCreate(
                        kind="upload.ingest",
                        queue="ingestion",
                        idempotency_key=idempotency_key,
                        payload={
                            "project_id": current["project_id"],
                            "graph_id": current["graph_id"],
                            "actor_id": current["actor_id"],
                            "object_key": current["object_key"],
                            "filename": current["filename"],
                            "title": current["title"],
                            "content_type": current["content_type"],
                            "checksum": f"multipart:{upload_id}",
                        },
                    ),
                    project_id=current["project_id"],
                    connection=connection,
                )
                job_id = job["id"]
                connection.execute(
                    update(db.upload_sessions)
                    .where(db.upload_sessions.c.id == upload_id)
                    .values(status="completed", updated_at=timestamp)
                )
        return {**result, "status": "completed", "job_id": job_id}

    def abort(self, upload_id: str) -> None:
        with self.engine.begin() as connection:
            row = connection.execute(
                select(db.upload_sessions).where(db.upload_sessions.c.id == upload_id).with_for_update()
            ).mappings().first()
            if row is None:
                raise KeyError(upload_id)
            if row["status"] == "uploading":
                self.object_store.abort_multipart(row["object_key"], row["storage_upload_id"])
                connection.execute(
                    update(db.upload_sessions)
                    .where(db.upload_sessions.c.id == upload_id)
                    .values(status="aborted", updated_at=datetime.now(tz=UTC))
                )
