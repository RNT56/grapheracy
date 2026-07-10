#!/usr/bin/env bash
set -euo pipefail

: "${GRAPHVIEW_DATABASE_URL:?GRAPHVIEW_DATABASE_URL is required}"

uv run --package graphview-api alembic -c services/api/alembic.ini upgrade head
uv run --package graphview-api alembic -c services/api/alembic.ini downgrade 20260614_0010
uv run --package graphview-api alembic -c services/api/alembic.ini upgrade head

uv run --package graphview-api python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["GRAPHVIEW_DATABASE_URL"])
with engine.begin() as connection:
    version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "20260710_0017", version
    jsonb_columns = connection.execute(text("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND column_name LIKE '%\\_\\_jsonb' ESCAPE '\\'
    """)).scalar_one()
    assert jsonb_columns == 67, jsonb_columns
    secret_type = connection.execute(text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name='connector_accounts' AND column_name='encrypted_token_json'
    """)).scalar_one()
    assert secret_type == "text", secret_type
    connection.execute(text("""
        INSERT INTO graph_projects(id,name,created_at,updated_at)
        VALUES ('migration-acceptance','Migration acceptance',now(),now())
        ON CONFLICT (id) DO UPDATE SET updated_at=excluded.updated_at
    """))
    connection.execute(text("""
        INSERT INTO content_nodes(
          id,project_id,label,kind,topic_ids_json,metadata_json,provenance_json,created_at,updated_at
        ) VALUES (
          'migration-node','migration-acceptance','Migration node','concept','[]',:metadata,'[]',now(),now()
        )
        ON CONFLICT (id) DO UPDATE SET metadata_json=excluded.metadata_json, updated_at=excluded.updated_at
    """), {"metadata": '{"legacy":true}'})
    parity = connection.execute(text("""
        SELECT metadata_json::jsonb = metadata_json__jsonb
        FROM content_nodes WHERE id='migration-node'
    """)).scalar_one()
    assert parity is True
PY
