#!/bin/sh
set -eu

operation="${1:-}"
shift || true
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_prefix="backups/${timestamp}"

case "$operation" in
  backup)
    retention_days=30
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --retention-days) retention_days="$2"; shift 2 ;;
        *) echo "Unknown backup argument: $1" >&2; exit 2 ;;
      esac
    done
    : "${PGHOST:?required}" "${PGUSER:?required}" "${PGDATABASE:?required}" "${PGPASSWORD:?required}"
    : "${MC_HOST_graphview:?required}"
    pg_dump --format=custom --no-owner --no-privileges --file=/tmp/graphview.dump
    sha256sum /tmp/graphview.dump > /tmp/graphview.dump.sha256
    mc cp /tmp/graphview.dump "graphview/graphview/${backup_prefix}/database.dump"
    mc cp /tmp/graphview.dump.sha256 "graphview/graphview/${backup_prefix}/database.dump.sha256"
    mc mirror --overwrite "graphview/graphview" "graphview/graphview/${backup_prefix}/objects" --exclude "backups/*"
    printf '%s\n' "$backup_prefix" > /tmp/backup-prefix
    mc cp /tmp/backup-prefix "graphview/graphview/${backup_prefix}/backup-prefix"
    cutoff="$(date -u -d "-${retention_days} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
    if [ -n "$cutoff" ]; then mc rm --recursive --force --older-than "${retention_days}d" "graphview/graphview/backups/"; fi
    echo "backup_prefix=${backup_prefix}"
    ;;
  verify)
    : "${BACKUP_PREFIX:?required}" "${MC_HOST_graphview:?required}"
    mc cp "graphview/graphview/${BACKUP_PREFIX}/database.dump" /tmp/graphview.dump
    mc cp "graphview/graphview/${BACKUP_PREFIX}/database.dump.sha256" /tmp/graphview.dump.sha256
    (cd /tmp && sha256sum -c graphview.dump.sha256)
    pg_restore --list /tmp/graphview.dump >/dev/null
    ;;
  restore)
    restore_prefix="${BACKUP_PREFIX:-}"
    confirmation="${RESTORE_CONFIRM:-}"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --backup-prefix) restore_prefix="$2"; shift 2 ;;
        --confirm) confirmation="$2"; shift 2 ;;
        *) echo "Unknown restore argument: $1" >&2; exit 2 ;;
      esac
    done
    : "${PGHOST:?required}" "${PGUSER:?required}" "${PGDATABASE:?required}" "${PGPASSWORD:?required}"
    : "${MC_HOST_graphview:?required}" "${REDIS_URL:?required}"
    if [ -z "$restore_prefix" ] || [ "$confirmation" != "$PGDATABASE" ]; then
      echo "Restore requires --backup-prefix and --confirm matching PGDATABASE" >&2
      exit 2
    fi
    BACKUP_PREFIX="$restore_prefix" "$0" verify
    psql --set ON_ERROR_STOP=1 --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid()"
    pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error --single-transaction --dbname="$PGDATABASE" /tmp/graphview.dump
    psql --set ON_ERROR_STOP=1 <<'SQL'
UPDATE connector_accounts
SET encrypted_token_json=NULL, status='reauth_required', updated_at=now();
UPDATE agent_context_clients
SET token_hash='restored:revoked', revoked_at=now();
UPDATE durable_jobs
SET status='cancelled', leased_until=NULL, worker_id=NULL,
    error_code='RestoreSuppressed', error='Suppressed during restore to prevent side-effect replay',
    updated_at=now(), finished_at=COALESCE(finished_at, now())
WHERE status IN ('queued', 'retry', 'running');
UPDATE event_outbox
SET status='suppressed', published_at=COALESCE(published_at, now())
WHERE status='pending';
UPDATE connector_cursors
SET lease_owner=NULL, leased_until=NULL, health_status='degraded',
    actionable_failure='Credentials require reauthorization after restore', updated_at=now();
SQL
    mc mirror --overwrite --remove "graphview/graphview/${restore_prefix}/objects" "graphview/graphview" --exclude "backups/*"
    redis-cli -u "$REDIS_URL" FLUSHDB >/dev/null
    ;;
  *)
    echo "Usage: graphview-ops backup [--retention-days N] | verify | restore --backup-prefix PREFIX --confirm DATABASE" >&2
    exit 2
    ;;
esac
