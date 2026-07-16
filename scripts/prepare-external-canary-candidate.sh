#!/usr/bin/env bash
set -euo pipefail

required=(GITHUB_REPOSITORY GITHUB_REPOSITORY_OWNER GITHUB_SHA GITHUB_REF GITHUB_ENV GH_TOKEN)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required to resolve the staged canary candidate." >&2
    exit 1
  fi
done
if [[ ! "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "GITHUB_SHA must be a full commit SHA." >&2
  exit 1
fi

temporary_directory="$(mktemp -d -t graphview-canary-candidate.XXXXXX)"
trap 'rm -rf "$temporary_directory"' EXIT

staging_run_id="$({
  gh api --method GET "repos/$GITHUB_REPOSITORY/actions/workflows/staging.yml/runs" \
    -f head_sha="$GITHUB_SHA" -f status=success -f per_page=100
} | jq -er --arg sha "$GITHUB_SHA" \
  '[.workflow_runs[] | select(.head_sha == $sha and .conclusion == "success")] | sort_by(.run_started_at) | last | .id')"

artifact_id="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$staging_run_id/artifacts" \
  | jq -er '[.artifacts[] | select(.name == "graphview-candidate-image-manifest" and (.expired | not))] | last | .id')"
gh api "repos/$GITHUB_REPOSITORY/actions/artifacts/$artifact_id/zip" > "$temporary_directory/manifest.zip"
unzip -q "$temporary_directory/manifest.zip" -d "$temporary_directory/manifest"
manifest_path="$(find "$temporary_directory/manifest" -type f -name candidate-image-manifest.json -print -quit)"
if [[ -z "$manifest_path" ]]; then
  echo "The successful staging run did not contain candidate-image-manifest.json." >&2
  exit 1
fi

services='["api","clamav","keycloak","minio","ops","otel","web","worker"]'
jq -e --arg commit "$GITHUB_SHA" --argjson services "$services" '
  .schema_version == 1
  and .commit == $commit
  and ((.images | keys | sort) == $services)
  and ([.images[] | .reference | type] | all(. == "string"))
  and ([.images[] | .digest | test("^sha256:[0-9a-f]{64}$")] | all)
' "$manifest_path" >/dev/null

registry_owner="$(printf '%s' "$GITHUB_REPOSITORY_OWNER" | tr '[:upper:]' '[:lower:]')"
repository_regex="${GITHUB_REPOSITORY//./\\.}"
staging_identity="^https://github.com/${repository_regex}/\\.github/workflows/staging\\.yml@refs/(heads/.+|pull/[0-9]+/merge)$"

mkdir -p artifacts
cp "$manifest_path" artifacts/candidate-image-manifest.json
manifest_sha256="$(sha256sum artifacts/candidate-image-manifest.json | awk '{print $1}')"

while IFS=$'\t' read -r service reference digest; do
  expected="ghcr.io/$registry_owner/graphview-$service:candidate-$GITHUB_SHA"
  if [[ "$reference" != "$expected" ]]; then
    echo "Candidate manifest reference mismatch for $service." >&2
    exit 1
  fi
  observed_digest="$(docker buildx imagetools inspect "$reference" --format '{{json .Manifest}}' | jq -er .digest)"
  if [[ "$observed_digest" != "$digest" ]]; then
    echo "Candidate digest drift detected for $service." >&2
    exit 1
  fi
  cosign verify \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity-regexp "$staging_identity" \
    "$reference@$digest" >/dev/null
  environment_name="GRAPHVIEW_$(printf '%s' "$service" | tr '[:lower:]' '[:upper:]')_IMAGE"
  printf '%s=%s@%s\n' "$environment_name" "$reference" "$digest" >> "$GITHUB_ENV"
done < <(jq -r '.images | to_entries[] | [.key,.value.reference,.value.digest] | @tsv' "$manifest_path")

{
  echo "GRAPHVIEW_CANARY_STAGING_RUN_ID=$staging_run_id"
  echo "GRAPHVIEW_CANARY_CANDIDATE_MANIFEST_SHA256=$manifest_sha256"
} >> "$GITHUB_ENV"

echo "Verified and digest-pinned eight staging-signed candidate images from run $staging_run_id."
