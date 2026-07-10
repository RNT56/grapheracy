#!/bin/sh
set -eu

operation="${1:-}"
shift || true
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_prefix="backups/${timestamp}"

validate_backup_prefix() {
  case "$1" in
    backups/*) ;;
    *) echo "Backup prefix must start with backups/" >&2; exit 2 ;;
  esac
  case "$1" in
    *..*|*//*|*[!A-Za-z0-9_./-]*) echo "Backup prefix contains unsafe characters" >&2; exit 2 ;;
  esac
}

write_live_object_manifest() {
  mc find graphview/graphview --ignore "backups/*" --print '{}|{size}' \
    | sed 's#^graphview/graphview/##' \
    | LC_ALL=C sort > "$1"
}

write_backup_object_manifest() {
  prefix="$1"
  mc find "graphview/graphview/${prefix}/payload" --print '{}|{size}' \
    | sed "s#^graphview/graphview/${prefix}/payload/##" \
    | LC_ALL=C sort > "$2"
}

case "$operation" in
  backup)
    retention_days=30
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --retention-days) retention_days="$2"; shift 2 ;;
        *) echo "Unknown backup argument: $1" >&2; exit 2 ;;
      esac
    done
    case "$retention_days" in ''|*[!0-9]*) echo "Retention days must be a positive integer" >&2; exit 2 ;; esac
    [ "$retention_days" -gt 0 ] || { echo "Retention days must be greater than zero" >&2; exit 2; }
    : "${PGHOST:?required}" "${PGUSER:?required}" "${PGDATABASE:?required}" "${PGPASSWORD:?required}"
    : "${MC_HOST_graphview:?required}"
    pg_dump --format=custom --no-owner --no-privileges --file=/tmp/graphview.dump
    sha256sum /tmp/graphview.dump > /tmp/graphview.dump.sha256
    write_live_object_manifest /tmp/objects.manifest
    sha256sum /tmp/objects.manifest > /tmp/objects.manifest.sha256
    mc mirror --overwrite --retry --summary "graphview/graphview" "graphview/graphview/${backup_prefix}/payload" --exclude "backups/*"
    mc cp /tmp/graphview.dump "graphview/graphview/${backup_prefix}/database.dump"
    mc cp /tmp/graphview.dump.sha256 "graphview/graphview/${backup_prefix}/database.dump.sha256"
    mc cp /tmp/objects.manifest "graphview/graphview/${backup_prefix}/objects.manifest"
    mc cp /tmp/objects.manifest.sha256 "graphview/graphview/${backup_prefix}/objects.manifest.sha256"
    printf '%s\n' "$backup_prefix" > /tmp/backup-prefix
    mc cp /tmp/backup-prefix "graphview/graphview/${backup_prefix}/backup-prefix"
    cutoff="$(date -u -d "-${retention_days} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
    if [ -n "$cutoff" ]; then mc rm --recursive --force --older-than "${retention_days}d" "graphview/graphview/backups/"; fi
    echo "backup_prefix=${backup_prefix}"
    ;;
  verify)
    : "${BACKUP_PREFIX:?required}" "${MC_HOST_graphview:?required}"
    validate_backup_prefix "$BACKUP_PREFIX"
    mc cp "graphview/graphview/${BACKUP_PREFIX}/database.dump" /tmp/graphview.dump
    mc cp "graphview/graphview/${BACKUP_PREFIX}/database.dump.sha256" /tmp/graphview.dump.sha256
    mc cp "graphview/graphview/${BACKUP_PREFIX}/objects.manifest" /tmp/objects.manifest
    mc cp "graphview/graphview/${BACKUP_PREFIX}/objects.manifest.sha256" /tmp/objects.manifest.sha256
    (cd /tmp && sha256sum -c graphview.dump.sha256)
    (cd /tmp && sha256sum -c objects.manifest.sha256)
    if [ -s /tmp/objects.manifest ]; then
      write_backup_object_manifest "$BACKUP_PREFIX" /tmp/backup-objects.manifest
    else
      : > /tmp/backup-objects.manifest
    fi
    cmp /tmp/objects.manifest /tmp/backup-objects.manifest
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
    : "${MC_HOST_graphview:?required}" "${REDIS_PASSWORD:?required}"
    validate_backup_prefix "$restore_prefix"
    if [ -z "$restore_prefix" ] || [ "$confirmation" != "$PGDATABASE" ]; then
      echo "Restore requires --backup-prefix and --confirm matching PGDATABASE" >&2
      exit 2
    fi
    if [ "${RESTORE_MAINTENANCE_CONFIRMED:-}" != "1" ]; then
      echo "Restore requires RESTORE_MAINTENANCE_CONFIRMED=1 after API and workers are stopped" >&2
      exit 2
    fi
    BACKUP_PREFIX="$restore_prefix" "$0" verify
    active_clients="$(
      psql --tuples-only --no-align --set ON_ERROR_STOP=1 \
        --command="SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid() AND backend_type='client backend'"
    )"
    if [ "$active_clients" != "0" ]; then
      echo "Restore refused because $active_clients database client connection(s) remain active" >&2
      exit 1
    fi
    psql --set ON_ERROR_STOP=1 --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid()"
    pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error --single-transaction --dbname="$PGDATABASE" /tmp/graphview.dump
    psql --set ON_ERROR_STOP=1 <<'SQL'
UPDATE connector_accounts
SET encrypted_token_json=NULL, status='error', updated_at=now();
UPDATE graph_settings
SET settings_json__jsonb=(COALESCE(settings_json__jsonb, settings_json::jsonb, '{}'::jsonb) - 'ai_provider_credentials' - 'llm_api_key'),
    settings_json=(COALESCE(settings_json__jsonb, settings_json::jsonb, '{}'::jsonb) - 'ai_provider_credentials' - 'llm_api_key')::text,
    updated_at=now();
UPDATE agent_context_clients
SET token_hash='restored:revoked', status='revoked', revoked_at=now(), updated_at=now();
UPDATE agent_context_sessions
SET status='cancelled', ended_at=COALESCE(ended_at, now()), updated_at=now()
WHERE status='running';
UPDATE durable_jobs
SET status='cancelled', leased_until=NULL, worker_id=NULL,
    error_code='RestoreSuppressed', error='Suppressed during restore to prevent side-effect replay',
    updated_at=now(), finished_at=COALESCE(finished_at, now())
WHERE status IN ('queued', 'retry', 'running');
UPDATE event_outbox
SET status='suppressed', published_at=COALESCE(published_at, now())
WHERE status='pending';
UPDATE action_runs
SET status='cancelled', error_code='RestoreSuppressed',
    error='Suppressed during restore to prevent side-effect replay', finished_at=COALESCE(finished_at, now())
WHERE status IN ('queued', 'running');
UPDATE action_proposals
SET payload_json__jsonb=(COALESCE(payload_json__jsonb, payload_json::jsonb, '{}'::jsonb) - 'credential_ref' - 'secret_ref' - 'token' - 'password' - 'api_key'),
    payload_json=(COALESCE(payload_json__jsonb, payload_json::jsonb, '{}'::jsonb) - 'credential_ref' - 'secret_ref' - 'token' - 'password' - 'api_key')::text
WHERE action_type IN ('create_external_ticket', 'create_notification', 'trigger_workflow');
UPDATE action_runs
SET payload_json__jsonb=(COALESCE(payload_json__jsonb, payload_json::jsonb, '{}'::jsonb) - 'credential_ref' - 'secret_ref' - 'token' - 'password' - 'api_key'),
    payload_json=(COALESCE(payload_json__jsonb, payload_json::jsonb, '{}'::jsonb) - 'credential_ref' - 'secret_ref' - 'token' - 'password' - 'api_key')::text
WHERE action_type IN ('create_external_ticket', 'create_notification', 'trigger_workflow');
UPDATE action_proposals
SET status='cancelled', updated_at=now()
WHERE status IN ('approved', 'queued', 'running');
UPDATE attention_items
SET status='blocked', updated_at=now()
WHERE action_run_id IN (SELECT id FROM action_runs WHERE error_code='RestoreSuppressed')
  AND status IN ('waiting_for_action', 'waiting_for_outcome');
UPDATE ingestion_runs
SET status='cancelled', finished_at=COALESCE(finished_at, now()),
    error_code=COALESCE(error_code, 'RestoreSuppressed')
WHERE status IN ('queued', 'running');
UPDATE connector_sync_runs
SET status='failed', stage='restore_suppressed', finished_at=COALESCE(finished_at, now()),
    error=COALESCE(error, 'Suppressed during restore')
WHERE status='running';
UPDATE agent_runs
SET status='cancelled', finished_at=COALESCE(finished_at, now()), error=COALESCE(error, 'Suppressed during restore')
WHERE status IN ('queued', 'running');
UPDATE research_tasks
SET status='failed', updated_at=now(),
    result_json__jsonb=jsonb_build_object('restore_suppressed', true),
    result_json=jsonb_build_object('restore_suppressed', true)::text
WHERE status IN ('queued', 'running');
UPDATE connector_cursors
SET lease_owner=NULL, leased_until=NULL, health_status='degraded',
    actionable_failure='Credentials require reauthorization after restore', updated_at=now();
INSERT INTO audit_events (
  id, project_id, actor_id, action, resource_type, resource_id, outcome, summary,
  metadata_json, metadata_json__jsonb, trace_id, occurred_at
)
SELECT
  'audit_restore_' || substring(md5(clock_timestamp()::text || random()::text), 1, 20),
  id, 'system-restore', 'system.restore', 'project', id, 'succeeded',
  'Production database and object restore completed with credentials and side effects suppressed',
  '{"credentials_restored":false,"side_effect_replay":false}',
  '{"credentials_restored":false,"side_effect_replay":false}'::jsonb,
  'trace_restore_' || substring(md5(clock_timestamp()::text || random()::text), 1, 20), now()
FROM graph_projects;
SQL
    write_live_object_manifest /tmp/live-objects-before-restore.manifest
    if [ -s /tmp/live-objects-before-restore.manifest ]; then
      sed 's#|.*$##; s#^#graphview/graphview/#' /tmp/live-objects-before-restore.manifest > /tmp/live-object-paths
      mc rm --force --stdin < /tmp/live-object-paths
    fi
    mc mirror --overwrite --retry --summary "graphview/graphview/${restore_prefix}/payload" "graphview/graphview"
    write_live_object_manifest /tmp/restored-objects.manifest
    cmp /tmp/objects.manifest /tmp/restored-objects.manifest
    redis_result="$(
      REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli \
        -h "${REDIS_HOST:-redis}" -p "${REDIS_PORT:-6379}" -n "${REDIS_DB:-0}" FLUSHDB
    )"
    [ "$redis_result" = "OK" ] || { echo "Redis session invalidation failed" >&2; exit 1; }
    ;;
  *)
    echo "Usage: graphview-ops backup [--retention-days N] | verify | restore --backup-prefix PREFIX --confirm DATABASE" >&2
    exit 2
    ;;
esac
