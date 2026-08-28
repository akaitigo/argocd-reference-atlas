#!/usr/bin/env bash

phase_setup() {
  extended_init auto-recovery
  local name
  name=$(extended_name auto-recovery)
  extended_apply_project_app auto-recovery apps/reconciliation main
  k -n "$ARGOCD_NAMESPACE" patch application "$name" --type merge -p \
    '{"spec":{"syncPolicy":{"automated":{"enabled":true,"prune":false,"selfHeal":true,"allowEmpty":false},"retry":{"limit":2,"backoff":{"duration":"5s","factor":2,"maxDuration":"10s"}},"syncOptions":["CreateNamespace=true"]}}}' >/dev/null
}

phase_execute() {
  local name namespace
  name=$(extended_name auto-recovery)
  namespace=$(extended_namespace auto-recovery)
  k -n "$namespace" patch configmap atlas-reconciliation --type merge -p '{"data":{"desired":"live-drift"}}' >/dev/null
  cat <<EOF | k apply -f - >/dev/null
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlas-auto-recovery-preserved
  namespace: ${namespace}
  labels:
    app.kubernetes.io/instance: ${name}
data:
  origin: live-only
EOF
  refresh_app "$name"
}

phase_verify() {
  local name namespace attempts
  name=$(extended_name auto-recovery)
  namespace=$(extended_namespace auto-recovery)
  wait_for_configmap_value "$namespace" atlas-reconciliation desired canonical 240
  k -n "$namespace" get configmap atlas-auto-recovery-preserved >/dev/null
  attempts=$(k -n "$ARGOCD_NAMESPACE" get application "$name" -o json | jq '[.status.operationState.syncResult.resources[]? | select(.status=="SyncFailed")] | length')
  (( attempts <= 2 )) || die "retry limitを超過しました: ${attempts}"
  jq -n --argjson attempts "$attempts" '{auto_recovery:{self_heal_without_manual_sync:true,prune_enabled:false,allow_empty:false,live_only_resource_preserved:true,retry_limit:2,observed_failed_resources:$attempts}}' >"$(extended_trace_file auto-recovery)"
  extended_capture auto-recovery
}

phase_cleanup() { extended_cleanup_project_app auto-recovery; }
