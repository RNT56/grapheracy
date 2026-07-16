"""validate JSONB parity and activate the JSONB read contract

Revision ID: 20260710_0014
Revises: 20260710_0013
"""

import hashlib
from collections.abc import Sequence

from alembic import op

revision: str = "20260710_0014"
down_revision: str | None = "20260710_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _shadow_columns(connection):
    inspector = __import__("sqlalchemy").inspect(connection)
    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            if column["name"].endswith("__jsonb"):
                yield table, column["name"], column["name"].removesuffix("__jsonb")


def _constraint(table: str, legacy: str) -> str:
    return f"ck_jsonb_parity_{hashlib.sha1(f'{table}.{legacy}'.encode()).hexdigest()[:16]}"


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    for table, shadow, legacy in _shadow_columns(connection):
        name = _constraint(table, legacy)
        op.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK '
            f'(("{legacy}" IS NULL) = ("{shadow}" IS NULL) AND '
            f'("{legacy}" IS NULL OR "{legacy}"::jsonb = "{shadow}")) NOT VALID'
        )
        op.execute(f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"')


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    for table, _, legacy in _shadow_columns(connection):
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{_constraint(table, legacy)}"')
