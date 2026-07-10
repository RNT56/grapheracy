"""keep opaque connector secret references as text rather than JSONB

Revision ID: 20260710_0017
Revises: 20260710_0016
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260710_0017"
down_revision: str | None = "20260710_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _constraint(column: str) -> str:
    return f"ck_jsonb_parity_{hashlib.sha1(f'connector_accounts.{column}'.encode()).hexdigest()[:16]}"


def _create_connector_trigger(*, include_secret: bool) -> None:
    columns = ["scopes_json", "settings_json"]
    if include_secret:
        columns.insert(0, "encrypted_token_json")
    assignments = []
    for column in columns:
        shadow = f"{column}__jsonb"
        assignments.append(f"""
          IF TG_OP = 'INSERT' THEN
            IF NEW.{shadow} IS NULL AND NEW.{column} IS NOT NULL THEN NEW.{shadow} := NEW.{column}::jsonb;
            ELSE NEW.{column} := CASE WHEN NEW.{shadow} IS NULL THEN NULL ELSE NEW.{shadow}::text END; END IF;
          ELSIF NEW.{shadow} IS DISTINCT FROM OLD.{shadow} THEN
            NEW.{column} := CASE WHEN NEW.{shadow} IS NULL THEN NULL ELSE NEW.{shadow}::text END;
          ELSIF NEW.{column} IS DISTINCT FROM OLD.{column} THEN
            NEW.{shadow} := CASE WHEN NEW.{column} IS NULL THEN NULL ELSE NEW.{column}::jsonb END;
          END IF;
        """)
    op.execute(f"""
      CREATE FUNCTION graphview_sync_connector_accounts_jsonb() RETURNS trigger AS $$ BEGIN
        {''.join(assignments)}
        RETURN NEW;
      END $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER graphview_sync_connector_accounts_jsonb BEFORE INSERT OR UPDATE ON connector_accounts "
        "FOR EACH ROW EXECUTE FUNCTION graphview_sync_connector_accounts_jsonb()"
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS graphview_sync_connector_accounts_jsonb ON connector_accounts")
    op.execute("DROP FUNCTION IF EXISTS graphview_sync_connector_accounts_jsonb")
    op.execute(f'ALTER TABLE connector_accounts DROP CONSTRAINT IF EXISTS "{_constraint("encrypted_token_json")}"')
    op.execute("""
      UPDATE connector_accounts
      SET encrypted_token_json = CASE
        WHEN encrypted_token_json__jsonb IS NULL THEN NULL
        WHEN jsonb_typeof(encrypted_token_json__jsonb) = 'string' THEN encrypted_token_json__jsonb #>> '{}'
        ELSE encrypted_token_json
      END
    """)
    op.drop_column("connector_accounts", "encrypted_token_json__jsonb")
    _create_connector_trigger(include_secret=False)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS graphview_sync_connector_accounts_jsonb ON connector_accounts")
    op.execute("DROP FUNCTION IF EXISTS graphview_sync_connector_accounts_jsonb")
    op.add_column(
        "connector_accounts",
        sa.Column("encrypted_token_json__jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute("""
      UPDATE connector_accounts
      SET encrypted_token_json__jsonb = CASE
        WHEN encrypted_token_json IS NULL THEN NULL
        ELSE to_jsonb(encrypted_token_json)
      END,
      encrypted_token_json = CASE
        WHEN encrypted_token_json IS NULL THEN NULL
        ELSE to_jsonb(encrypted_token_json)::text
      END
    """)
    name = _constraint("encrypted_token_json")
    op.execute(
        f'ALTER TABLE connector_accounts ADD CONSTRAINT "{name}" CHECK '
        '((encrypted_token_json IS NULL) = (encrypted_token_json__jsonb IS NULL) AND '
        '(encrypted_token_json IS NULL OR encrypted_token_json::jsonb = encrypted_token_json__jsonb))'
    )
    _create_connector_trigger(include_secret=True)
