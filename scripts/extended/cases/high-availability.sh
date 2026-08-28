#!/usr/bin/env bash
. "$(dirname -- "${BASH_SOURCE[0]}")/../isolation.sh"

ISO_CLUSTER=argocd-atlas-ha-v3-5-2
ISO_CONTEXT=kind-argocd-atlas-ha-v3-5-2
k() { isolated_k "$@"; }

redis_master() {
  local pod role
  while IFS= read -r pod; do
    role=$(k -n "$ARGOCD_NAMESPACE" exec "$pod" -c redis -- sh -c 'redis-cli --no-auth-warning -a "$AUTH" role | head -1' 2>/dev/null || true)
    [[ "$role" == master ]] && { printf '%s\n' "$pod"; return 0; }
  done < <(k -n "$ARGOCD_NAMESPACE" get pods -l app.kubernetes.io/name=argocd-redis-ha -o name | sort)
  return 1
}

phase_setup() {
  extended_init high-availability
  local lock install_url install_sha256 version_url version_sha256
  lock="${ATLAS_ROOT}/environments/kind/argocd-v3.5.2-ha.lock"
  install_url=$(sed -n 's/^install_url=//p' "$lock")
  install_sha256=$(sed -n 's/^install_sha256=//p' "$lock")
  version_url=$(sed -n 's/^version_url=//p' "$lock")
  version_sha256=$(sed -n 's/^version_sha256=//p' "$lock")
  extended_download_verified "$version_url" "$version_sha256" "${EXTENDED_RUNTIME}/downloads/high-availability-VERSION"
  isolated_setup 3 "$install_url" "$install_sha256" high-availability
  k -n "$ARGOCD_NAMESPACE" rollout status statefulset/argocd-redis-ha-server --timeout=600s
  extended_wait_jsonpath "$ARGOCD_NAMESPACE" deployment/argocd-repo-server '{.status.readyReplicas}' 2 480
  extended_wait_jsonpath "$ARGOCD_NAMESPACE" deployment/argocd-server '{.status.readyReplicas}' 2 480
  extended_apply_project_app high-availability apps/application main
}

phase_execute() {
  local leader uid read_success=0 read_failure=0 metrics_success=0 metrics_failure=0 i
  leader=$(redis_master) || die 'Redis masterを特定できません'
  uid=$(k -n "$ARGOCD_NAMESPACE" get "$leader" -o jsonpath='{.metadata.uid}')
  k -n "$ARGOCD_NAMESPACE" delete "$leader" --wait=false >/dev/null
  for ((i=0; i<10; i++)); do
    if k -n "$ARGOCD_NAMESPACE" get application "$(extended_name high-availability)" >/dev/null 2>&1; then read_success=$((read_success+1)); else read_failure=$((read_failure+1)); fi
    if k get --raw "/api/v1/namespaces/${ARGOCD_NAMESPACE}/services/argocd-server-metrics:8083/proxy/metrics" >/dev/null 2>&1; then metrics_success=$((metrics_success+1)); else metrics_failure=$((metrics_failure+1)); fi
    sleep 2
  done
  jq -n --arg leader "$leader" --arg uid "$uid" --argjson reads "$read_success" --argjson read_failures "$read_failure" --argjson metrics "$metrics_success" --argjson metric_failures "$metrics_failure" \
    '{high_availability:{leader_before:$leader,leader_uid_before:$uid,outage_window:{application_reads_succeeded:$reads,application_reads_failed:$read_failures,server_metric_reads_succeeded:$metrics,server_metric_reads_failed:$metric_failures,attempts:10}}}' >"$(extended_trace_file high-availability)"
  (( read_success > 0 && metrics_success > 0 )) || die 'Redis leader停止中にread pathを観測できませんでした'
  k -n "$ARGOCD_NAMESPACE" rollout status statefulset/argocd-redis-ha-server --timeout=600s
}

phase_verify() {
  local leader_before leader_after ready_repo ready_server images
  leader_after=$(redis_master) || die '再選出後のRedis masterを特定できません'
  leader_before=$(jq -r '.high_availability.leader_before' "$(extended_trace_file high-availability)")
  [[ "$leader_after" != "$leader_before" ]] || die 'Redis leaderが別Podへ再選出されていません'
  ready_repo=$(k -n "$ARGOCD_NAMESPACE" get deployment argocd-repo-server -o jsonpath='{.status.readyReplicas}')
  ready_server=$(k -n "$ARGOCD_NAMESPACE" get deployment argocd-server -o jsonpath='{.status.readyReplicas}')
  (( ready_repo >= 2 && ready_server >= 2 )) || die 'HA replicaが回復していません'
  wait_synced_healthy "$(extended_name high-availability)"
  images=$(k -n "$ARGOCD_NAMESPACE" get pods -o json | jq '[.items[].status.containerStatuses[]?|{name:.name,image:.image,imageID:.imageID}] | unique_by(.imageID)')
  jq --arg after "$leader_after" --argjson repo "$ready_repo" --argjson server "$ready_server" --argjson images "$images" \
    '.high_availability += {leader_after:$after,repo_server_ready:$repo,api_server_ready:$server,application_read_path_available:true,runtime_images:$images,non_guarantee:"単一Kind host自体の障害耐性は実証対象外"}' \
    "$(extended_trace_file high-availability)" >"$(extended_trace_file high-availability).tmp"
  mv "$(extended_trace_file high-availability).tmp" "$(extended_trace_file high-availability)"
  extended_capture high-availability
}

phase_cleanup() { isolated_cleanup high-availability; }
