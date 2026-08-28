#!/usr/bin/env bash

metrics_proxy() {
  local service=$1 port=$2
  k get --raw "/api/v1/namespaces/${ARGOCD_NAMESPACE}/services/${service}:${port}/proxy/metrics"
}

phase_setup() {
  extended_init observability
  extended_apply_project_app observability apps/application main
}

phase_execute() {
  local name operation_time
  name=$(extended_name observability)
  operation_time=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  jq -n --arg time "$operation_time" --arg app "$name" '{operation:{started_at:$time,application:$app,actions:["hard-refresh","sync","wait"]}}' >"$(extended_trace_file observability)"
  refresh_app "$name"
  request_sync "$name"
  wait_synced_healthy "$name"
}

phase_verify() {
  local name trace_dir controller_metrics server_metrics repo_metrics controller_sample server_sample repo_sample operation_time controller_log server_log repo_log
  name=$(extended_name observability)
  trace_dir="${EXTENDED_RUNTIME}/observability"
  mkdir -p "$trace_dir"
  metrics_proxy argocd-metrics 8082 >"${trace_dir}/controller.metrics"
  metrics_proxy argocd-server-metrics 8083 >"${trace_dir}/server.metrics"
  metrics_proxy argocd-repo-server 8084 >"${trace_dir}/repo.metrics"
  grep -Eq '^argocd_app_(info|reconcile_count)' "${trace_dir}/controller.metrics" || die 'Application Controller metricがありません'
  grep -Eq '^argocd_|^grpc_' "${trace_dir}/server.metrics" || die 'API Server metricがありません'
  grep -Eq '^argocd_|^grpc_' "${trace_dir}/repo.metrics" || die 'Repository Server metricがありません'
  controller_sample=$(grep -E '^argocd_app_(info|reconcile_count)' "${trace_dir}/controller.metrics" | grep -F "$name" | head -5 || true)
  server_sample=$(grep -E '^argocd_|^grpc_' "${trace_dir}/server.metrics" | head -5 || true)
  repo_sample=$(grep -E '^argocd_|^grpc_' "${trace_dir}/repo.metrics" | head -5 || true)
  [[ -n "$server_sample" && -n "$repo_sample" ]] || die 'Server/Repository metric sampleが空です'
  [[ -n "$controller_sample" ]] || die 'Application識別子付きController metricがありません'
  operation_time=$(jq -r '.operation.started_at' "$(extended_trace_file observability)")
  controller_log=$(k -n "$ARGOCD_NAMESPACE" logs statefulset/argocd-application-controller --since-time="$operation_time" --tail=200 2>&1 | sed -E 's/([Pp]assword|[Tt]oken|[Ss]ecret|[Aa]uthorization)[=:][^ ]+/\1=[REDACTED]/g' | tail -40)
  server_log=$(k -n "$ARGOCD_NAMESPACE" logs deployment/argocd-server --since-time="$operation_time" --tail=100 2>&1 | sed -E 's/([Pp]assword|[Tt]oken|[Ss]ecret|[Aa]uthorization)[=:][^ ]+/\1=[REDACTED]/g' | tail -20)
  repo_log=$(k -n "$ARGOCD_NAMESPACE" logs deployment/argocd-repo-server --since-time="$operation_time" --tail=100 2>&1 | sed -E 's/([Pp]assword|[Tt]oken|[Ss]ecret|[Aa]uthorization)[=:][^ ]+/\1=[REDACTED]/g' | tail -20)
  jq --arg controller "$controller_sample" --arg server "$server_sample" --arg repo "$repo_sample" --arg controller_log "$controller_log" --arg server_log "$server_log" --arg repo_log "$repo_log" \
    '. + {observability:{application:.operation.application,operation_started_at:.operation.started_at,controller_metric_sample:$controller,server_metric_sample:$server,repo_metric_sample:$repo,component_logs:{application_controller:$controller_log,api_server:$server_log,repository_server:$repo_log},secret_values_captured:false}}' \
    "$(extended_trace_file observability)" >"$(extended_trace_file observability).tmp"
  mv "$(extended_trace_file observability).tmp" "$(extended_trace_file observability)"
  extended_capture observability
}

phase_cleanup() { extended_cleanup_project_app observability; }
