#!/usr/bin/env bash
set -euo pipefail

: "${GRAPHVIEW_DATABASE_URL:?GRAPHVIEW_DATABASE_URL is required}"

uv run --package graphview-api alembic -c services/api/alembic.ini upgrade head
uv run --package graphview-api alembic -c services/api/alembic.ini downgrade 20260614_0010

lock_marker="$(mktemp -t graphview-migration-lock.XXXXXX)"
migration_failure_log="$(mktemp -t graphview-migration-failure.XXXXXX)"
rm -f "$lock_marker"
cleanup_locker() {
  if [[ -n "${locker_pid:-}" ]]; then
    kill "$locker_pid" >/dev/null 2>&1 || true
    wait "$locker_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$lock_marker" "$migration_failure_log"
}
trap cleanup_locker EXIT

uv run --package graphview-api python - "$lock_marker" <<'PY' &
import os
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["GRAPHVIEW_DATABASE_URL"])
with engine.begin() as connection:
    connection.execute(text("LOCK TABLE agent_context_blobs IN ACCESS EXCLUSIVE MODE"))
    Path(sys.argv[1]).write_text("locked\n")
    time.sleep(30)
PY
locker_pid="$!"
for _ in $(seq 1 100); do
  [[ -s "$lock_marker" ]] && break
  sleep 0.1
done
[[ -s "$lock_marker" ]]

if PGOPTIONS="-c lock_timeout=250ms" uv run --package graphview-api alembic -c services/api/alembic.ini upgrade head \
  >"$migration_failure_log" 2>&1; then
  echo "Migration interruption injection unexpectedly succeeded." >&2
  exit 1
fi
grep -q 'LockNotAvailable' "$migration_failure_log"
cleanup_locker
locker_pid=""

uv run --package graphview-api python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["GRAPHVIEW_DATABASE_URL"])
with engine.begin() as connection:
    version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "20260614_0010", version
    partial_column_count = connection.execute(text("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND table_name='agent_context_blobs' AND column_name='object_key'
    """)).scalar_one()
    assert partial_column_count == 0, partial_column_count
PY

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
