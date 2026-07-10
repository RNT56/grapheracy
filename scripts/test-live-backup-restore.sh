#!/usr/bin/env bash
set -euo pipefail

project_name="${GRAPHVIEW_COMPOSE_PROJECT:-graphview-live-ci}"
compose_file="${GRAPHVIEW_COMPOSE_FILE:-infra/compose/docker-compose.production.yml}"
compose=(docker compose -p "$project_name" -f "$compose_file")

container_id() {
  docker ps -aq \
    --filter "label=com.docker.compose.project=$project_name" \
    --filter "label=com.docker.compose.service=$1" \
    | head -n 1
}

postgres_id="$(container_id postgres)"
redis_id="$(container_id redis)"
if [[ -z "$postgres_id" || -z "$redis_id" ]]; then
  echo "The Graphview PostgreSQL and Redis services must be running." >&2
  exit 1
fi

psql_graphview() {
  docker exec -i "$postgres_id" psql --set ON_ERROR_STOP=1 --username graphview --dbname graphview "$@"
}

wait_for_service() {
  local service="$1"
  local expected="$2"
  local identifier
  identifier="$(container_id "$service")"
  for _ in $(seq 1 120); do
    local observed
    observed="$(docker inspect "$identifier" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')"
    if [[ "$observed" == "$expected" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "$service did not reach $expected." >&2
  docker logs --tail=200 "$identifier" >&2
  return 1
}

"${compose[@]}" stop api worker keycloak

psql_graphview <<'SQL'
DELETE FROM action_runs WHERE id='run-restore-canary';
DELETE FROM action_proposals WHERE id='action-restore-canary';
DELETE FROM attention_items WHERE id='attention-restore-canary';
DELETE FROM event_outbox WHERE id='outbox-restore-canary';
DELETE FROM durable_jobs WHERE id='job-restore-canary';
DELETE FROM agent_context_clients WHERE id='client-restore-canary';
DELETE FROM connector_accounts WHERE id='connector-restore-canary';
DELETE FROM sources WHERE id='source-restore-canary';

INSERT INTO sources (
  id, project_id, kind, title, uri, object_key, checksum, metadata_json, metadata_json__jsonb,
  created_at, updated_at
) VALUES (
  'source-restore-canary', 'project-default', 'upload', 'Restore canary source', NULL,
  'project-default/restore-canary/object.txt',
  '247eab6c9dd7c1d37e5333ff3f220e00211ccfaf05b7ef1e02c522e0693f03fb', '{}', '{}'::jsonb,
  now(), now()
);

INSERT INTO connector_accounts (
  id, project_id, kind, display_name, status, created_by, encrypted_token_json,
  scopes_json, settings_json, scopes_json__jsonb, settings_json__jsonb, created_at, updated_at
) VALUES (
  'connector-restore-canary', 'project-default', 'notion', 'Restore credential canary', 'active',
  'restore-test', 'gvsecret:vault:v1:must-not-survive', '[]', '{}', '[]'::jsonb, '{}'::jsonb, now(), now()
);

INSERT INTO agent_context_clients (
  id, project_id, display_name, runtime_kind, status, created_by, token_hash,
  scopes_json, settings_json, scopes_json__jsonb, settings_json__jsonb, created_at, updated_at
) VALUES (
  'client-restore-canary', 'project-default', 'Restore context canary', 'generic', 'active', 'restore-test',
  'usable-token-hash-must-not-survive', '["context:capture"]', '{}', '["context:capture"]'::jsonb,
  '{}'::jsonb, now(), now()
);

INSERT INTO durable_jobs (
  id, project_id, queue, kind, status, idempotency_key, payload_json, result_json,
  payload_json__jsonb, result_json__jsonb, attempt, max_attempts, available_at, trace_id, created_at, updated_at
) VALUES (
  'job-restore-canary', 'project-default', 'actions', 'action.run', 'queued', 'restore-canary-job',
  '{"action_proposal_id":"action-restore-canary","credential_ref":"gvsecret:vault:v1:must-not-survive"}', '{}',
  '{"action_proposal_id":"action-restore-canary","credential_ref":"gvsecret:vault:v1:must-not-survive"}'::jsonb,
  '{}'::jsonb, 0, 5, now(), 'trace-restore-canary', now(), now()
);

INSERT INTO event_outbox (
  id, project_id, topic, event_type, aggregate_type, aggregate_id, schema_version,
  payload_json, payload_json__jsonb, trace_id, status, attempt, available_at, created_at
) VALUES (
  'outbox-restore-canary', 'project-default', 'jobs.actions', 'job.queued', 'job', 'job-restore-canary', 1,
  '{"job_id":"job-restore-canary"}', '{"job_id":"job-restore-canary"}'::jsonb,
  'trace-restore-canary', 'pending', 0, now(), now()
);

INSERT INTO attention_items (
  id, project_id, kind, status, severity, sla_status, title, summary,
  object_refs_json, evidence_json, suggested_actions_json, blockers_json,
  object_refs_json__jsonb, evidence_json__jsonb, suggested_actions_json__jsonb, blockers_json__jsonb,
  created_at, updated_at
) VALUES (
  'attention-restore-canary', 'project-default', 'action', 'waiting_for_action', 'medium', 'within_sla',
  'Restore action canary', 'Must become blocked without execution', '[]', '[]', '[]', '[]',
  '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, now(), now()
);

INSERT INTO action_proposals (
  id, project_id, attention_item_id, action_type, status, title, summary,
  payload_json, redacted_payload_json, safety_json,
  payload_json__jsonb, redacted_payload_json__jsonb, safety_json__jsonb,
  approval_required, created_by, approved_by, created_at, updated_at, decided_at
) VALUES (
  'action-restore-canary', 'project-default', 'attention-restore-canary', 'trigger_workflow', 'queued',
  'Restore side-effect canary', 'Must never execute after restore',
  '{"destination":"https://example.com/hook","credential_ref":"gvsecret:vault:v1:must-not-survive"}',
  '{"destination":"https://example.com/hook","credential_ref":"[redacted]"}',
  '{"calls_external_system":true}',
  '{"destination":"https://example.com/hook","credential_ref":"gvsecret:vault:v1:must-not-survive"}'::jsonb,
  '{"destination":"https://example.com/hook","credential_ref":"[redacted]"}'::jsonb,
  '{"calls_external_system":true}'::jsonb,
  true, 'restore-test', 'restore-test', now(), now(), now()
);

INSERT INTO action_runs (
  id, project_id, action_proposal_id, action_type, status, executor_id, target,
  payload_json, redacted_payload_json, payload_json__jsonb, redacted_payload_json__jsonb,
  trace_id, started_at
) VALUES (
  'run-restore-canary', 'project-default', 'action-restore-canary', 'trigger_workflow', 'queued', 'restore-test',
  'https://example.com/hook',
  '{"destination":"https://example.com/hook","credential_ref":"gvsecret:vault:v1:must-not-survive"}',
  '{"destination":"https://example.com/hook","credential_ref":"[redacted]"}',
  '{"destination":"https://example.com/hook","credential_ref":"gvsecret:vault:v1:must-not-survive"}'::jsonb,
  '{"destination":"https://example.com/hook","credential_ref":"[redacted]"}'::jsonb,
  'trace-restore-canary', now()
);

UPDATE attention_items
SET action_proposal_id='action-restore-canary', action_run_id='run-restore-canary'
WHERE id='attention-restore-canary';

UPDATE graph_settings
SET settings_json=(COALESCE(settings_json__jsonb, settings_json::jsonb, '{}'::jsonb)
    || '{"ai_provider_credentials":{"openai":{"encrypted_api_key":"gvsecret:vault:v1:must-not-survive"}}}'::jsonb)::text,
    settings_json__jsonb=(COALESCE(settings_json__jsonb, settings_json::jsonb, '{}'::jsonb)
    || '{"ai_provider_credentials":{"openai":{"encrypted_api_key":"gvsecret:vault:v1:must-not-survive"}}}'::jsonb),
    updated_at=now()
WHERE project_id='project-default';
SQL

"${compose[@]}" run --rm --no-deps --entrypoint /bin/sh ops -ec \
  "printf '%s' 'Graphview restore object canary' | mc pipe graphview/graphview/project-default/restore-canary/object.txt >/dev/null"

if [[ -n "${REDIS_PASSWORD:-}" ]]; then
  docker exec -e REDISCLI_AUTH="$REDIS_PASSWORD" "$redis_id" redis-cli SET graphview:restore-canary present >/dev/null
else
  echo "REDIS_PASSWORD is required for live restore acceptance." >&2
  exit 1
fi

backup_output="$("${compose[@]}" run --rm --no-deps ops backup --retention-days 30)"
backup_prefix="$(printf '%s\n' "$backup_output" | sed -n 's/^backup_prefix=//p' | tail -n 1)"
if [[ "$backup_prefix" != backups/* ]]; then
  echo "Backup did not return a safe prefix." >&2
  exit 1
fi
"${compose[@]}" run --rm --no-deps -e BACKUP_PREFIX="$backup_prefix" ops verify

psql_graphview <<'SQL'
DELETE FROM action_runs WHERE id='run-restore-canary';
DELETE FROM action_proposals WHERE id='action-restore-canary';
DELETE FROM attention_items WHERE id='attention-restore-canary';
DELETE FROM event_outbox WHERE id='outbox-restore-canary';
DELETE FROM durable_jobs WHERE id='job-restore-canary';
DELETE FROM agent_context_clients WHERE id='client-restore-canary';
DELETE FROM connector_accounts WHERE id='connector-restore-canary';
DELETE FROM sources WHERE id='source-restore-canary';
SQL
"${compose[@]}" run --rm --no-deps --entrypoint mc ops rm graphview/graphview/project-default/restore-canary/object.txt

"${compose[@]}" run --rm --no-deps \
  -e RESTORE_MAINTENANCE_CONFIRMED=1 \
  ops restore --backup-prefix "$backup_prefix" --confirm graphview

psql_graphview <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM sources WHERE id='source-restore-canary' AND title='Restore canary source') THEN
    RAISE EXCEPTION 'source record was not restored';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM connector_accounts
    WHERE id='connector-restore-canary' AND encrypted_token_json IS NULL AND status='error'
  ) THEN
    RAISE EXCEPTION 'connector credential was not neutralized';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM agent_context_clients
    WHERE id='client-restore-canary' AND token_hash='restored:revoked' AND status='revoked' AND revoked_at IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'agent context token was not revoked';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM durable_jobs
    WHERE id='job-restore-canary' AND status='cancelled' AND error_code='RestoreSuppressed'
  ) THEN
    RAISE EXCEPTION 'durable job was not suppressed';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM event_outbox
    WHERE id='outbox-restore-canary' AND status='suppressed' AND published_at IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'outbox event was not suppressed';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM action_runs
    WHERE id='run-restore-canary' AND status='cancelled' AND error_code='RestoreSuppressed'
      AND NOT (COALESCE(payload_json__jsonb, payload_json::jsonb, '{}'::jsonb) ? 'credential_ref')
  ) THEN
    RAISE EXCEPTION 'action run was not neutralized';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM action_proposals
    WHERE id='action-restore-canary' AND status='cancelled'
      AND NOT (COALESCE(payload_json__jsonb, payload_json::jsonb, '{}'::jsonb) ? 'credential_ref')
  ) THEN
    RAISE EXCEPTION 'action proposal was not neutralized';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM attention_items WHERE id='attention-restore-canary' AND status='blocked') THEN
    RAISE EXCEPTION 'attention item was not blocked';
  END IF;
  IF EXISTS (
    SELECT 1 FROM graph_settings
    WHERE project_id='project-default'
      AND COALESCE(settings_json__jsonb, settings_json::jsonb, '{}'::jsonb) ? 'ai_provider_credentials'
  ) THEN
    RAISE EXCEPTION 'AI provider credential reference survived restore';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM audit_events
    WHERE action='system.restore' AND outcome='succeeded'
      AND COALESCE(metadata_json__jsonb, metadata_json::jsonb, '{}'::jsonb) @>
        '{"credentials_restored":false,"side_effect_replay":false}'::jsonb
  ) THEN
    RAISE EXCEPTION 'restore audit event is missing';
  END IF;
END $$;
SQL

object_text="$("${compose[@]}" run --rm --no-deps --entrypoint mc ops cat graphview/graphview/project-default/restore-canary/object.txt)"
[[ "$object_text" == "Graphview restore object canary" ]]
redis_value="$(docker exec -e REDISCLI_AUTH="$REDIS_PASSWORD" "$redis_id" redis-cli --raw GET graphview:restore-canary)"
[[ -z "$redis_value" ]]

"${compose[@]}" up -d --no-deps keycloak
wait_for_service keycloak healthy
"${compose[@]}" up -d --no-deps api worker
wait_for_service api healthy
wait_for_service worker running
curl -fsS "${GRAPHVIEW_PUBLIC_URL:-http://127.0.0.1:8080}/ready" >/dev/null
sleep 3

psql_graphview -Atc "SELECT CASE WHEN status='cancelled' AND error_code='RestoreSuppressed' THEN 'suppressed' ELSE status END FROM durable_jobs WHERE id='job-restore-canary'" \
  | grep -qx suppressed
psql_graphview -Atc "SELECT CASE WHEN status='cancelled' AND error_code='RestoreSuppressed' THEN 'suppressed' ELSE status END FROM action_runs WHERE id='run-restore-canary'" \
  | grep -qx suppressed

echo "Live backup/restore proof passed for $backup_prefix: database and objects restored; credentials, sessions, jobs, outbox events, and actions remained inert."
