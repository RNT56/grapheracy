from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, select, update

from graphview_api import db
from graphview_api.json_compat import json_value


DEFAULT_PROJECT_ID = "project-default"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class ConnectorRepositoryMixin:
    """Project-scoped connector account, target, credential, and run persistence."""

    def list_connector_accounts(self, *, project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        with self.engine.begin() as connection:
            return [
                self._connector_account_from_row(row)
                for row in connection.execute(
                    select(db.connector_accounts)
                    .where(db.connector_accounts.c.project_id == project_id)
                    .order_by(db.connector_accounts.c.created_at.desc(), db.connector_accounts.c.id.desc())
                ).mappings()
            ]

    def create_connector_account(self, payload, actor_id: str, *, project_id: str = DEFAULT_PROJECT_ID) -> dict:
        timestamp = _now()
        account = {
            "id": _new_id("connacct"),
            "project_id": project_id,
            "kind": payload.kind,
            "display_name": payload.display_name,
            "status": "connected",
            "created_by": actor_id,
            "encrypted_token_json": self._encrypt_json(payload.token_json) if payload.token_json else None,
            "scopes_json": _json(payload.scopes),
            "settings_json": _json(payload.settings),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.engine.begin() as connection:
            connection.execute(insert(db.connector_accounts).values(**account))
        return self._connector_account_from_row(account)

    def update_connector_account_tokens(self, account_id: str, token_json: dict, *, project_id: str) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(db.connector_accounts)
                .where(and_(db.connector_accounts.c.id == account_id, db.connector_accounts.c.project_id == project_id))
                .values(encrypted_token_json=self._encrypt_json(token_json), updated_at=_now())
            )
            if result.rowcount != 1:
                raise KeyError(account_id)

    def list_connector_targets(self, *, project_id: str | None = DEFAULT_PROJECT_ID) -> list[dict]:
        statement = select(db.connector_targets)
        if project_id is not None:
            statement = statement.where(db.connector_targets.c.project_id == project_id)
        statement = statement.order_by(db.connector_targets.c.created_at.desc(), db.connector_targets.c.id.desc())
        with self.engine.begin() as connection:
            return [
                self._connector_target_from_row(row)
                for row in connection.execute(statement).mappings()
            ]

    def create_connector_target(self, payload, *, project_id: str = DEFAULT_PROJECT_ID) -> dict:
        with self.engine.begin() as connection:
            account_row = connection.execute(
                select(db.connector_accounts).where(
                    and_(db.connector_accounts.c.id == payload.account_id, db.connector_accounts.c.project_id == project_id)
                )
            ).mappings().first()
            if account_row is None:
                raise KeyError(payload.account_id)
            timestamp = _now()
            target = {
                "id": _new_id("conntgt"),
                "project_id": project_id,
                "account_id": payload.account_id,
                "connector_kind": account_row["kind"],
                "target_type": payload.target_type,
                "remote_id": payload.remote_id,
                "title": payload.title,
                "parent_remote_id": payload.parent_remote_id,
                "sync_settings_json": _json(payload.sync_settings),
                "last_synced_at": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            connection.execute(insert(db.connector_targets).values(**target))
        return self._connector_target_from_row(target)

    def update_connector_target(self, target_id: str, payload, *, project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
        values = payload.model_dump(exclude_unset=True)
        if "sync_settings" in values:
            values["sync_settings_json"] = _json(values.pop("sync_settings") or {})
        if not values:
            bundle = self.connector_target_bundle(target_id, project_id=project_id)
            return bundle[1] if bundle else None
        values["updated_at"] = _now()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(db.connector_targets)
                .where(and_(db.connector_targets.c.id == target_id, db.connector_targets.c.project_id == project_id))
                .values(**values)
            )
            if result.rowcount == 0:
                return None
            row = connection.execute(
                select(db.connector_targets).where(
                    and_(db.connector_targets.c.id == target_id, db.connector_targets.c.project_id == project_id)
                )
            ).mappings().one()
            return self._connector_target_from_row(row)

    def connector_target_bundle(self, target_id: str, *, project_id: str | None = None) -> tuple[dict, dict, dict | None] | None:
        with self.engine.begin() as connection:
            target_conditions = [db.connector_targets.c.id == target_id]
            if project_id is not None:
                target_conditions.append(db.connector_targets.c.project_id == project_id)
            target_row = connection.execute(
                select(db.connector_targets).where(and_(*target_conditions))
            ).mappings().first()
            if target_row is None:
                return None
            account_row = connection.execute(
                select(db.connector_accounts).where(
                    and_(db.connector_accounts.c.id == target_row["account_id"], db.connector_accounts.c.project_id == target_row["project_id"])
                )
            ).mappings().first()
            if account_row is None:
                return None
            envelope = json_value(account_row, "encrypted_token_json")
            return (
                self._connector_account_from_row(account_row),
                self._connector_target_from_row(target_row),
                self._decrypt_json(envelope) if envelope else None,
            )

    def list_connector_sync_runs(self, *, project_id: str = DEFAULT_PROJECT_ID) -> list[dict]:
        with self.engine.begin() as connection:
            return [
                self._connector_sync_run_from_row(row)
                for row in connection.execute(
                    select(db.connector_sync_runs)
                    .where(db.connector_sync_runs.c.project_id == project_id)
                    .order_by(db.connector_sync_runs.c.started_at.desc(), db.connector_sync_runs.c.id.desc())
                ).mappings()
            ]

    def get_connector_sync_run(self, sync_run_id: str, *, project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                select(db.connector_sync_runs).where(
                    and_(db.connector_sync_runs.c.id == sync_run_id, db.connector_sync_runs.c.project_id == project_id)
                )
            ).mappings().first()
            return self._connector_sync_run_from_row(row) if row else None
