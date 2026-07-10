from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from graphview_api import db
from graphview_api.repository import DEFAULT_PROJECT_ID, dump_json, load_json
from graphview_api.json_compat import json_value, normalize_json_row


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class JobRepository:
    def __init__(self, engine):
        self.engine = engine

    def enqueue(self, payload, *, project_id: str = DEFAULT_PROJECT_ID, trace_id: str | None = None, connection=None) -> dict:
        timestamp = utc_now()
        trace_id = trace_id or f"trace_{uuid4().hex[:20]}"
        job_id = f"job_{uuid4().hex[:20]}"
        row = {
            "id": job_id,
            "project_id": project_id,
            "queue": payload.queue,
            "kind": payload.kind,
            "status": "queued",
            "idempotency_key": payload.idempotency_key,
            "payload_json": dump_json(payload.payload),
            "result_json": dump_json({}),
            "attempt": 0,
            "max_attempts": payload.max_attempts,
            "available_at": timestamp,
            "leased_until": None,
            "worker_id": None,
            "error_code": None,
            "error": None,
            "trace_id": trace_id,
            "created_at": timestamp,
            "updated_at": timestamp,
            "finished_at": None,
        }
        outbox_row = {
            "id": f"outbox_{uuid4().hex[:20]}",
            "project_id": project_id,
            "topic": f"jobs.{payload.queue}",
            "event_type": "job.queued",
            "aggregate_type": "job",
            "aggregate_id": job_id,
            "schema_version": 1,
            "payload_json": dump_json({"job_id": job_id, "queue": payload.queue, "kind": payload.kind}),
            "trace_id": trace_id,
            "status": "pending",
            "attempt": 0,
            "available_at": timestamp,
            "published_at": None,
            "created_at": timestamp,
        }
        if connection is not None:
            connection.execute(insert(db.durable_jobs).values(**row))
            connection.execute(insert(db.event_outbox).values(**outbox_row))
            return self._job(row)
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(db.durable_jobs).values(**row))
                conn.execute(insert(db.event_outbox).values(**outbox_row))
        except IntegrityError:
            existing = self.get_by_idempotency(project_id, payload.idempotency_key)
            if existing is None:
                raise
            return existing
        return self._job(row)

    def get(self, job_id: str, *, project_id: str | None = None) -> dict | None:
        statement = select(db.durable_jobs).where(db.durable_jobs.c.id == job_id)
        if project_id is not None:
            statement = statement.where(db.durable_jobs.c.project_id == project_id)
        with self.engine.begin() as conn:
            row = conn.execute(statement).mappings().first()
        return self._job(row) if row else None

    def get_by_idempotency(self, project_id: str, idempotency_key: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(db.durable_jobs).where(
                    and_(db.durable_jobs.c.project_id == project_id, db.durable_jobs.c.idempotency_key == idempotency_key)
                )
            ).mappings().first()
        return self._job(row) if row else None

    def list(self, *, project_id: str = DEFAULT_PROJECT_ID, status: str | None = None, limit: int = 50, cursor: str | None = None) -> list[dict]:
        stmt = select(db.durable_jobs).where(db.durable_jobs.c.project_id == project_id)
        if status:
            stmt = stmt.where(db.durable_jobs.c.status == status)
        if cursor:
            stmt = stmt.where(db.durable_jobs.c.id > cursor)
        stmt = stmt.order_by(db.durable_jobs.c.created_at.desc(), db.durable_jobs.c.id.desc()).limit(min(200, max(1, limit)))
        with self.engine.begin() as conn:
            return [self._job(row) for row in conn.execute(stmt).mappings()]

    def claim(self, job_id: str, *, worker_id: str, lease_seconds: int = 300) -> dict | None:
        timestamp = utc_now()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(db.durable_jobs)
                .where(
                    and_(
                        db.durable_jobs.c.id == job_id,
                        db.durable_jobs.c.status.in_(["queued", "retry"]),
                        db.durable_jobs.c.available_at <= timestamp,
                        or_(db.durable_jobs.c.leased_until.is_(None), db.durable_jobs.c.leased_until < timestamp),
                    )
                )
                .values(
                    status="running",
                    worker_id=worker_id,
                    leased_until=timestamp + timedelta(seconds=lease_seconds),
                    attempt=db.durable_jobs.c.attempt + 1,
                    updated_at=timestamp,
                )
            )
            if result.rowcount == 0:
                return None
            row = conn.execute(select(db.durable_jobs).where(db.durable_jobs.c.id == job_id)).mappings().one()
        return self._job(row)

    def complete(self, job_id: str, result: dict) -> dict:
        timestamp = utc_now()
        with self.engine.begin() as conn:
            conn.execute(
                update(db.durable_jobs)
                .where(db.durable_jobs.c.id == job_id)
                .values(status="succeeded", result_json=dump_json(result), leased_until=None, updated_at=timestamp, finished_at=timestamp)
            )
            row = conn.execute(select(db.durable_jobs).where(db.durable_jobs.c.id == job_id)).mappings().one()
        return self._job(row)

    def fail(self, job_id: str, *, error_code: str, error: str, retry_delay_seconds: int = 30) -> dict:
        timestamp = utc_now()
        with self.engine.begin() as conn:
            current = conn.execute(select(db.durable_jobs).where(db.durable_jobs.c.id == job_id)).mappings().one()
            retry = current["attempt"] < current["max_attempts"]
            conn.execute(
                update(db.durable_jobs)
                .where(db.durable_jobs.c.id == job_id)
                .values(
                    status="retry" if retry else "failed",
                    error_code=error_code,
                    error=error[:2000],
                    available_at=timestamp + timedelta(seconds=retry_delay_seconds),
                    leased_until=None,
                    updated_at=timestamp,
                    finished_at=None if retry else timestamp,
                )
            )
            row = conn.execute(select(db.durable_jobs).where(db.durable_jobs.c.id == job_id)).mappings().one()
        return self._job(row)

    def cancel(self, job_id: str, *, project_id: str | None = None) -> dict | None:
        timestamp = utc_now()
        conditions = [db.durable_jobs.c.id == job_id, db.durable_jobs.c.status.in_(["queued", "retry"])]
        if project_id is not None:
            conditions.append(db.durable_jobs.c.project_id == project_id)
        with self.engine.begin() as conn:
            result = conn.execute(
                update(db.durable_jobs)
                .where(and_(*conditions))
                .values(status="cancelled", updated_at=timestamp, finished_at=timestamp)
            )
            if result.rowcount == 0:
                return None
            row = conn.execute(select(db.durable_jobs).where(db.durable_jobs.c.id == job_id)).mappings().one()
        return self._job(row)

    def retry(self, job_id: str, *, project_id: str | None = None) -> dict | None:
        timestamp = utc_now()
        conditions = [db.durable_jobs.c.id == job_id, db.durable_jobs.c.status.in_(["failed", "cancelled"])]
        if project_id is not None:
            conditions.append(db.durable_jobs.c.project_id == project_id)
        with self.engine.begin() as conn:
            result = conn.execute(
                update(db.durable_jobs)
                .where(and_(*conditions))
                .values(
                    status="queued",
                    attempt=0,
                    available_at=timestamp,
                    leased_until=None,
                    worker_id=None,
                    error_code=None,
                    error=None,
                    updated_at=timestamp,
                    finished_at=None,
                )
            )
            if result.rowcount == 0:
                return None
            row = conn.execute(select(db.durable_jobs).where(db.durable_jobs.c.id == job_id)).mappings().one()
            conn.execute(
                insert(db.event_outbox).values(
                    id=f"outbox_{uuid4().hex[:20]}",
                    project_id=row["project_id"],
                    topic=f"jobs.{row['queue']}",
                    event_type="job.retried",
                    aggregate_type="job",
                    aggregate_id=job_id,
                    schema_version=1,
                    payload_json=dump_json({"job_id": job_id, "queue": row["queue"], "kind": row["kind"]}),
                    trace_id=row["trace_id"],
                    status="pending",
                    attempt=0,
                    available_at=timestamp,
                    published_at=None,
                    created_at=timestamp,
                )
            )
        return self._job(row)

    def pending_outbox(self, *, limit: int = 100) -> list[dict]:
        timestamp = utc_now()
        with self.engine.begin() as conn:
            return [
                {**normalize_json_row(row), "payload": load_json(json_value(row, "payload_json"), {})}
                for row in conn.execute(
                    select(db.event_outbox)
                    .where(and_(db.event_outbox.c.status == "pending", db.event_outbox.c.available_at <= timestamp))
                    .order_by(db.event_outbox.c.created_at, db.event_outbox.c.id)
                    .limit(limit)
                ).mappings()
            ]

    def mark_outbox_published(self, outbox_id: str) -> None:
        timestamp = utc_now()
        with self.engine.begin() as conn:
            conn.execute(
                update(db.event_outbox)
                .where(db.event_outbox.c.id == outbox_id)
                .values(status="published", published_at=timestamp, attempt=db.event_outbox.c.attempt + 1)
            )

    def _job(self, row) -> dict:
        data = normalize_json_row(row)
        data["payload"] = load_json(data.pop("payload_json"), {})
        data["result"] = load_json(data.pop("result_json"), {})
        return data
