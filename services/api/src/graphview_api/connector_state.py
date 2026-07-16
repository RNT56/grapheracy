from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, insert, select, update

from graphview_api import db
from graphview_api.json_compat import json_value
from graphview_api.redaction import redact_sensitive_text


class ConnectorStateRepository:
    """Durable cursor, lease, and operator-facing health state for connector targets."""

    def __init__(self, engine):
        self.engine = engine

    def get(self, target_id: str) -> dict | None:
        with self.engine.begin() as connection:
            target = connection.execute(
                select(db.connector_targets).where(db.connector_targets.c.id == target_id)
            ).mappings().first()
            if target is None:
                return None
            row = connection.execute(
                select(db.connector_cursors).where(db.connector_cursors.c.target_id == target_id)
            ).mappings().first()
            return self._output(target, row)

    def project_id(self, target_id: str) -> str | None:
        with self.engine.begin() as connection:
            return connection.execute(
                select(db.connector_targets.c.project_id).where(db.connector_targets.c.id == target_id)
            ).scalar_one_or_none()

    def remote_ids(self, target_id: str) -> set[str]:
        with self.engine.begin() as connection:
            target = connection.execute(
                select(db.connector_targets).where(db.connector_targets.c.id == target_id)
            ).mappings().first()
            if target is None:
                raise KeyError(target_id)
            remote_ids: set[str] = set()
            for row in connection.execute(
                select(db.sources.c.remote_id, db.sources.c.metadata_json).where(
                    and_(
                        db.sources.c.project_id == target["project_id"],
                        db.sources.c.connector_kind == target["connector_kind"],
                    )
                )
            ).mappings():
                raw_metadata = json_value(row, "metadata_json")
                metadata = raw_metadata if isinstance(raw_metadata, dict) else json.loads(raw_metadata or "{}")
                if metadata.get("targetId") == target_id and row["remote_id"]:
                    remote_ids.add(str(row["remote_id"]))
            return remote_ids

    def mark_queued(self, target_id: str, *, next_scheduled_at=None) -> dict:
        return self._upsert(
            target_id,
            health_status="syncing",
            next_scheduled_at=next_scheduled_at,
            actionable_failure=None,
        )

    def claim(self, target_id: str, *, worker_id: str, lease_seconds: int = 900) -> dict:
        timestamp = datetime.now(tz=UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                select(db.connector_cursors).where(db.connector_cursors.c.target_id == target_id)
            ).mappings().first()
            if row and row["leased_until"] and row["leased_until"] > timestamp and row["lease_owner"] != worker_id:
                raise RuntimeError("Connector target already has an active sync lease")
        return self._upsert(
            target_id,
            health_status="syncing",
            lease_owner=worker_id,
            leased_until=timestamp + timedelta(seconds=lease_seconds),
            actionable_failure=None,
        )

    def succeed(
        self,
        target_id: str,
        *,
        imported_count: int,
        deleted_count: int,
        cursor: str | None = None,
        next_scheduled_at=None,
    ) -> dict:
        return self._upsert(
            target_id,
            health_status="healthy",
            cursor=cursor,
            lease_owner=None,
            leased_until=None,
            retry_attempt=0,
            imported_count=imported_count,
            deleted_count=deleted_count,
            last_success_at=datetime.now(tz=UTC),
            next_scheduled_at=next_scheduled_at,
            actionable_failure=None,
        )

    def fail(self, target_id: str, error: Exception, *, retry_attempt: int) -> dict:
        message = redact_sensitive_text(error)[:1000]
        lowered = message.lower()
        status = "auth_failed" if any(value in lowered for value in ("401", "403", "unauthorized", "credential")) else (
            "rate_limited" if "429" in lowered or "rate limit" in lowered else "degraded"
        )
        return self._upsert(
            target_id,
            health_status=status,
            lease_owner=None,
            leased_until=None,
            retry_attempt=retry_attempt,
            actionable_failure=message,
        )

    def _upsert(self, target_id: str, **values) -> dict:
        timestamp = datetime.now(tz=UTC)
        with self.engine.begin() as connection:
            target = connection.execute(
                select(db.connector_targets).where(db.connector_targets.c.id == target_id)
            ).mappings().first()
            if target is None:
                raise KeyError(target_id)
            existing = connection.execute(
                select(db.connector_cursors).where(db.connector_cursors.c.target_id == target_id)
            ).mappings().first()
            if existing is None:
                record = {
                    "target_id": target_id,
                    "project_id": target["project_id"],
                    "cursor": None,
                    "lease_owner": None,
                    "leased_until": None,
                    "health_status": "healthy",
                    "retry_attempt": 0,
                    "imported_count": 0,
                    "deleted_count": 0,
                    "last_success_at": None,
                    "next_scheduled_at": None,
                    "actionable_failure": None,
                    "updated_at": timestamp,
                    **values,
                }
                connection.execute(insert(db.connector_cursors).values(**record))
            else:
                connection.execute(
                    update(db.connector_cursors)
                    .where(db.connector_cursors.c.target_id == target_id)
                    .values(updated_at=timestamp, **values)
                )
            row = connection.execute(
                select(db.connector_cursors).where(db.connector_cursors.c.target_id == target_id)
            ).mappings().one()
            return self._output(target, row)

    def _output(self, target, row) -> dict:
        timestamp = datetime.now(tz=UTC)
        if row is None:
            row = {
                "target_id": target["id"],
                "cursor": None,
                "lease_owner": None,
                "leased_until": None,
                "health_status": "healthy",
                "retry_attempt": 0,
                "imported_count": 0,
                "deleted_count": 0,
                "last_success_at": None,
                "next_scheduled_at": None,
                "actionable_failure": None,
                "updated_at": timestamp,
            }
        return {
            "target_id": target["id"],
            "status": row["health_status"],
            "last_success_at": row["last_success_at"],
            "next_scheduled_at": row["next_scheduled_at"],
            "cursor": {
                "target_id": target["id"],
                "cursor": row["cursor"],
                "lease_owner": row["lease_owner"],
                "leased_until": row["leased_until"],
                "updated_at": row["updated_at"],
            },
            "retry_attempt": row["retry_attempt"],
            "imported_count": row["imported_count"],
            "deleted_count": row["deleted_count"],
            "actionable_failure": row["actionable_failure"],
        }
