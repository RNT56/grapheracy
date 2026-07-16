#!/usr/bin/env bash
set -euo pipefail

for command_name in helm kubeconform trivy; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required deployment verification tool is missing: $command_name" >&2
    exit 1
  fi
done

temporary_directory="$(mktemp -d -t graphview-helm-rendered.XXXXXX)"
rendered_manifest="$temporary_directory/rendered.yaml"
trap 'rm -rf "$temporary_directory"' EXIT

helm dependency list infra/helm/graphview | grep -Eq '^vault[[:space:]]+0\.34\.0[[:space:]].*[[:space:]]ok[[:space:]]*$'
helm lint --strict infra/helm/graphview
helm template graphview infra/helm/graphview --namespace graphview --skip-tests >"$rendered_manifest"
kubeconform -strict -summary -kubernetes-version 1.35.0 "$rendered_manifest"
trivy config --skip-version-check --severity HIGH,CRITICAL --exit-code 1 "$rendered_manifest"
