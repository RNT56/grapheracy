"""backfill Graphview JSONB read-contract columns

Revision ID: 20260710_0013
Revises: 20260710_0012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260710_0013"
down_revision: str | None = "20260710_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _shadow_columns(connection):
    inspector = __import__("sqlalchemy").inspect(connection)
    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            if column["name"].endswith("__jsonb"):
                yield table, column["name"], column["name"].removesuffix("__jsonb")


def upgrade() -> None:
    connection = op.get_bind()
    postgres = connection.dialect.name == "postgresql"
    for table, shadow, legacy in _shadow_columns(connection):
        cast = f'"{legacy}"::jsonb' if postgres else f'"{legacy}"'
        op.execute(
            f'UPDATE "{table}" SET "{shadow}" = {cast} '
            f'WHERE "{legacy}" IS NOT NULL AND "{shadow}" IS NULL'
        )


def downgrade() -> None:
    pass
