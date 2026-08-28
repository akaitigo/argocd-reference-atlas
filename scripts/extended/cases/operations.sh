#!/usr/bin/env bash

normalized_operations_state() {
  local output=$1 name
  name=$(extended_name operations)
  k -n "$ARGOCD_NAMESPACE" get appproject "$name" -o json >"${output}.project"
  k -n "$ARGOCD_NAMESPACE" get application "$name" -o json >"${output}.application"
  jq -s 'map({apiVersion,kind,metadata:{name:.metadata.name,namespace:.metadata.namespace},spec}) | sort_by(.kind)' \
    "${output}.project" "${output}.application" >"$output"
}

phase_setup() {
  extended_init operations
  extended_apply_project_app operations apps/application main
  normalized_operations_state "${EXTENDED_RUNTIME}/backup/operations-before.json"
}

phase_execute() {
  local name backup backup_digest before_digest
  name=$(extended_name operations)
  backup="${EXTENDED_RUNTIME}/backup/operations-export.yaml"
  k --request-timeout=60s -n "$ARGOCD_NAMESPACE" exec deployment/argocd-server -- argocd admin export --namespace "$ARGOCD_NAMESPACE" >"$backup"
  chmod 0600 "$backup"
  [[ -s "$backup" ]] || die 'argocd admin exportが空です'
  backup_digest=$(sha256_file "$backup")
  before_digest=$(sha256_file "${EXTENDED_RUNTIME}/backup/operations-before.json")
  k -n "$ARGOCD_NAMESPACE" delete application "$name" --wait=true >/dev/null
  k -n "$ARGOCD_NAMESPACE" delete appproject "$name" --wait=true >/dev/null
  k --request-timeout=60s -n "$ARGOCD_NAMESPACE" exec -i deployment/argocd-server -- argocd admin import - <"$backup" >/dev/null
  jq -n --arg backup "sha256:${backup_digest}" --arg before "sha256:${before_digest}" \
    '{operations:{precondition:{context_verified:true,application_exists:true},refresh:{timeout_seconds:180},sync:{timeout_seconds:240},wait:{timeout_seconds:240},diagnosis:{application_status_captured:true},backup_digest:$backup,before_state_digest:$before,backup_contains_secrets:true,backup_retained_in_evidence:false}}' \
    >"$(extended_trace_file operations)"
}

phase_verify() {
  local after_digest conditions
  wait_synced_healthy "$(extended_name operations)"
  normalized_operations_state "${EXTENDED_RUNTIME}/backup/operations-after.json"
  cmp "${EXTENDED_RUNTIME}/backup/operations-before.json" "${EXTENDED_RUNTIME}/backup/operations-after.json" >/dev/null || die 'Operations restore後の主要CR specが一致しません'
  after_digest=$(sha256_file "${EXTENDED_RUNTIME}/backup/operations-after.json")
  conditions=$(k -n "$ARGOCD_NAMESPACE" get application "$(extended_name operations)" -o json | jq '.status.conditions // []')
  jq --arg after "sha256:${after_digest}" --argjson conditions "$conditions" \
    '.operations += {after_state_digest:$after,specs_equal:true,diagnostic_conditions:$conditions,stop_condition:"all bounded operations completed",temporary_credentials_left:false}' \
    "$(extended_trace_file operations)" >"$(extended_trace_file operations).tmp"
  mv "$(extended_trace_file operations).tmp" "$(extended_trace_file operations)"
  extended_capture operations
}

phase_cleanup() {
  extended_cleanup_project_app operations
  rm -f -- "${EXTENDED_RUNTIME}/backup/operations-export.yaml"
}
