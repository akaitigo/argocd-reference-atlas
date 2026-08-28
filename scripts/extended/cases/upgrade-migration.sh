#!/usr/bin/env bash
. "$(dirname -- "${BASH_SOURCE[0]}")/../isolation.sh"

ISO_CLUSTER=argocd-atlas-upgrade-v3-4-8
ISO_CONTEXT=kind-argocd-atlas-upgrade-v3-4-8
k() { isolated_k "$@"; }

normalized_upgrade_state() {
  local output=$1 name
  name=$(extended_name upgrade-migration)
  k -n "$ARGOCD_NAMESPACE" get appproject "$name" -o json >"${output}.project"
  k -n "$ARGOCD_NAMESPACE" get application "$name" -o json >"${output}.application"
  jq -s 'map({apiVersion,kind,metadata:{name:.metadata.name,namespace:.metadata.namespace},spec}) | sort_by(.kind)' \
    "${output}.project" "${output}.application" >"$output"
}

phase_setup() {
  extended_init upgrade-migration
  local lock install_url install_sha256 version_url version_sha256
  lock="${ATLAS_ROOT}/environments/kind/argocd-v3.4.8.lock"
  install_url=$(sed -n 's/^install_url=//p' "$lock")
  install_sha256=$(sed -n 's/^install_sha256=//p' "$lock")
  version_url=$(sed -n 's/^version_url=//p' "$lock")
  version_sha256=$(sed -n 's/^version_sha256=//p' "$lock")
  extended_download_verified "$version_url" "$version_sha256" "${EXTENDED_RUNTIME}/downloads/upgrade-migration-v3.4.8-VERSION"
  isolated_setup 1 "$install_url" "$install_sha256" upgrade-migration-v3.4.8
  extended_apply_project_app upgrade-migration apps/application main
  normalized_upgrade_state "${EXTENDED_RUNTIME}/backup/upgrade-before.json"
  before_digest=$(sha256_file "${EXTENDED_RUNTIME}/backup/upgrade-before.json")
  before_images=$(k -n "$ARGOCD_NAMESPACE" get deployments,statefulsets -o json | jq '[.items[].spec.template.spec.containers[].image|select(contains("argoproj/argocd"))]|unique')
  [[ "$(jq '[.[]|select(contains("v3.4.8"))]|length' <<<"$before_images")" -ge 1 ]] || die 'v3.4.8 runtime imageがありません'
  jq -n --arg digest "sha256:${before_digest}" --argjson images "$before_images" \
    '{upgrade:{before_version:"v3.4.8",before_state_digest:$digest,before_images:$images,preflight:{plain_http_oci:false,ui_extensions:false,generated_event_grpc_client:false,deprecated_gnupg:false,action:"no fixture-specific migration required"},rollback_boundary:"restore backup and reapply v3.4.8 manifest on post-check failure"}}' \
    >"$(extended_trace_file upgrade-migration)"
}

phase_execute() {
  local lock install_url install_sha256 manifest
  lock="${ATLAS_ROOT}/environments/kind/argocd-v3.5.2.lock"
  install_url=$(sed -n 's/^install_url=//p' "$lock")
  install_sha256=$(sed -n 's/^install_sha256=//p' "$lock")
  manifest="${EXTENDED_RUNTIME}/downloads/upgrade-migration-v3.5.2-install.yaml"
  extended_download_verified "$install_url" "$install_sha256" "$manifest"
  k -n "$ARGOCD_NAMESPACE" apply --server-side --force-conflicts -f "$manifest" >/dev/null
  k -n "$ARGOCD_NAMESPACE" rollout status deployment/argocd-repo-server --timeout=480s
  k -n "$ARGOCD_NAMESPACE" rollout status deployment/argocd-server --timeout=480s
  k -n "$ARGOCD_NAMESPACE" rollout status statefulset/argocd-application-controller --timeout=480s
}

phase_verify() {
  local after_digest after_images
  normalized_upgrade_state "${EXTENDED_RUNTIME}/backup/upgrade-after.json"
  cmp "${EXTENDED_RUNTIME}/backup/upgrade-before.json" "${EXTENDED_RUNTIME}/backup/upgrade-after.json" >/dev/null || die 'Upgrade後の主要CR specが一致しません'
  after_digest=$(sha256_file "${EXTENDED_RUNTIME}/backup/upgrade-after.json")
  after_images=$(k -n "$ARGOCD_NAMESPACE" get deployments,statefulsets -o json | jq '[.items[].spec.template.spec.containers[].image|select(contains("argoproj/argocd"))]|unique')
  [[ "$(jq '[.[]|select(contains("v3.5.2"))]|length' <<<"$after_images")" -ge 1 ]] || die 'v3.5.2 runtime imageがありません'
  wait_synced_healthy "$(extended_name upgrade-migration)"
  jq --arg digest "sha256:${after_digest}" --argjson images "$after_images" \
    '.upgrade += {after_version:"v3.5.2",after_state_digest:$digest,after_images:$images,specs_equal:true,application_sync:"Synced",application_health:"Healthy",post_check:"pass"}' \
    "$(extended_trace_file upgrade-migration)" >"$(extended_trace_file upgrade-migration).tmp"
  mv "$(extended_trace_file upgrade-migration).tmp" "$(extended_trace_file upgrade-migration)"
  extended_capture upgrade-migration
}

phase_cleanup() { isolated_cleanup upgrade-migration-v3.4.8; }
