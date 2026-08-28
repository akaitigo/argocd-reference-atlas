#!/usr/bin/env bash

phase_setup() {
  extended_init drift
  extended_apply_project_app drift apps/diff main
}

phase_execute() {
  local name namespace
  name=$(extended_name drift)
  namespace=$(extended_namespace drift)
  k -n "$namespace" patch configmap atlas-diff --type merge -p '{"data":{"desired":"semantic-live-drift"}}' >/dev/null
  refresh_app "$name"
  wait_for_app_field "$name" '{.status.sync.status}' OutOfSync 180
  request_sync "$name"
  wait_synced_healthy "$name"
  k -n "$ARGOCD_NAMESPACE" patch application "$name" --type merge -p \
    '{"spec":{"ignoreDifferences":[{"group":"","kind":"ConfigMap","name":"atlas-diff","jsonPointers":["/metadata/annotations/atlas.openai.com~1noise"]}]}}' >/dev/null
  k -n "$namespace" annotate configmap atlas-diff atlas.openai.com/noise=ignored --overwrite >/dev/null
  refresh_app "$name"
}

phase_verify() {
  local name namespace tracking diff_rule
  name=$(extended_name drift)
  namespace=$(extended_namespace drift)
  wait_for_app_field "$name" '{.status.sync.status}' Synced 180
  tracking=$(k -n "$ARGOCD_NAMESPACE" get configmap argocd-cm -o jsonpath='{.data.application\.resourceTrackingMethod}' 2>/dev/null || true)
  [[ -n "$tracking" ]] || tracking=label
  diff_rule=$(k -n "$ARGOCD_NAMESPACE" get application "$name" -o json | jq '.spec.ignoreDifferences')
  jq -n --arg tracking "$tracking" --argjson diff_rule "$diff_rule" \
    '{drift:{semantic_change_status:"OutOfSync",semantic_change_repaired:true,ignored_annotation_status:"Synced",tracking_method:$tracking,diff_ignore:$diff_rule,resource_update_ignore:"not-configured"}}' >"$(extended_trace_file drift)"
  extended_capture drift
}

phase_cleanup() { extended_cleanup_project_app drift; }
