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

wait_redis_master() {
  local timeout_seconds=${1:-300} elapsed=0 master
  while (( elapsed < timeout_seconds )); do
    master=$(redis_master || true)
    if [[ -n "$master" ]]; then
      printf '%s\n' "$master"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  return 1
}

ready_component_pod() {
  local selector=$1
  k -n "$ARGOCD_NAMESPACE" get pods -l "$selector" -o json | jq -r '
    [.items[] | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))] |
    sort_by(.metadata.name) | first | .metadata.name // empty'
}

wait_replacement_ready() {
  local selector=$1 previous_uid=$2 timeout_seconds=${3:-480} elapsed=0 pod uid
  while (( elapsed < timeout_seconds )); do
    pod=$(ready_component_pod "$selector")
    if [[ -n "$pod" ]]; then
      uid=$(k -n "$ARGOCD_NAMESPACE" get pod "$pod" -o jsonpath='{.metadata.uid}')
      if [[ "$uid" != "$previous_uid" ]]; then
        printf '%s\n' "$pod"
        return 0
      fi
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "Component Podが別UIDで回復しません: ${selector}"
}

exercise_component_failure() {
  local component=$1 selector=$2 before uid_before after uid_after started finished elapsed read_success=0 read_failure=0 i
  before=$(ready_component_pod "$selector")
  [[ -n "$before" ]] || die "Ready Podを特定できません: ${component}"
  uid_before=$(k -n "$ARGOCD_NAMESPACE" get pod "$before" -o jsonpath='{.metadata.uid}')
  started=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  local start_seconds=$SECONDS
  k -n "$ARGOCD_NAMESPACE" delete pod "$before" --wait=false >/dev/null
  for ((i=0; i<10; i++)); do
    if k -n "$ARGOCD_NAMESPACE" get application "$(extended_name high-availability)" >/dev/null 2>&1; then
      read_success=$((read_success+1))
    else
      read_failure=$((read_failure+1))
    fi
    sleep 2
  done
  after=$(wait_replacement_ready "$selector" "$uid_before")
  uid_after=$(k -n "$ARGOCD_NAMESPACE" get pod "$after" -o jsonpath='{.metadata.uid}')
  elapsed=$((SECONDS - start_seconds))
  finished=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  jq -n --arg component "$component" --arg before "$before" --arg before_uid "$uid_before" \
    --arg after "$after" --arg after_uid "$uid_after" --arg started "$started" --arg finished "$finished" \
    --argjson elapsed "$elapsed" --argjson reads "$read_success" --argjson failures "$read_failure" \
    '{component:$component,pod_before:$before,pod_uid_before:$before_uid,pod_after:$after,pod_uid_after:$after_uid,started_at:$started,recovered_at:$finished,recovery_seconds:$elapsed,application_reads:{succeeded:$reads,failed:$failures,attempts:10}}'
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
  local leader uid promoted_leader='' observed_leader read_success=0 read_failure=0 metrics_success=0 metrics_failure=0 i controller_failure repo_failure name namespace
  name=$(extended_name high-availability)
  namespace=$(extended_namespace high-availability)

  controller_failure=$(exercise_component_failure application-controller 'app.kubernetes.io/name=argocd-application-controller')
  k -n "$namespace" patch configmap atlas-application --type merge -p '{"data":{"release":"controller-drift"}}' >/dev/null
  refresh_app "$name"
  wait_for_app_field "$name" '{.status.sync.status}' OutOfSync 240
  request_sync "$name"
  wait_synced_healthy "$name"
  wait_for_configmap_value "$namespace" atlas-application release v1 240

  repo_failure=$(exercise_component_failure repo-server 'app.kubernetes.io/name=argocd-repo-server')
  refresh_app "$name"
  wait_synced_healthy "$name"

  leader=$(redis_master) || die 'Redis masterを特定できません'
  uid=$(k -n "$ARGOCD_NAMESPACE" get "$leader" -o jsonpath='{.metadata.uid}')
  k -n "$ARGOCD_NAMESPACE" delete "$leader" --wait=false >/dev/null
  for ((i=0; i<10; i++)); do
    if k -n "$ARGOCD_NAMESPACE" get application "$(extended_name high-availability)" >/dev/null 2>&1; then read_success=$((read_success+1)); else read_failure=$((read_failure+1)); fi
    if k get --raw "/api/v1/namespaces/${ARGOCD_NAMESPACE}/services/argocd-server-metrics:8083/proxy/metrics" >/dev/null 2>&1; then metrics_success=$((metrics_success+1)); else metrics_failure=$((metrics_failure+1)); fi
    observed_leader=$(redis_master || true)
    if [[ -n "$observed_leader" && "$observed_leader" != "$leader" ]]; then promoted_leader=$observed_leader; fi
    sleep 2
  done
  jq -n --arg leader "$leader" --arg uid "$uid" --argjson reads "$read_success" --argjson read_failures "$read_failure" --argjson metrics "$metrics_success" --argjson metric_failures "$metrics_failure" \
    --argjson controller "$controller_failure" --argjson repo "$repo_failure" --arg promoted "$promoted_leader" \
    '{high_availability:{component_failures:{application_controller:$controller,repo_server:$repo},controller_reconciled_post_recovery_drift:true,repo_server_completed_hard_refresh_after_recovery:true,redis:{leader_before:$leader,leader_uid_before:$uid,leader_promoted_during_outage:$promoted,outage_window:{application_reads_succeeded:$reads,application_reads_failed:$read_failures,server_metric_reads_succeeded:$metrics,server_metric_reads_failed:$metric_failures,attempts:10}}}}' >"$(extended_trace_file high-availability)"
  (( read_success > 0 && metrics_success > 0 )) || die 'Redis leader停止中にread pathを観測できませんでした'
  k -n "$ARGOCD_NAMESPACE" rollout status statefulset/argocd-redis-ha-server --timeout=600s
}

phase_verify() {
  local leader_before_uid leader_after leader_after_uid ready_repo ready_server images
  leader_after=$(wait_redis_master 300) || die '再選出後のRedis masterを特定できません'
  leader_before_uid=$(jq -r '.high_availability.redis.leader_uid_before' "$(extended_trace_file high-availability)")
  leader_after_uid=$(k -n "$ARGOCD_NAMESPACE" get "$leader_after" -o jsonpath='{.metadata.uid}')
  [[ "$leader_after_uid" != "$leader_before_uid" ]] || die 'Redis master PodのUIDが障害前後で変化していません'
  ready_repo=$(k -n "$ARGOCD_NAMESPACE" get deployment argocd-repo-server -o jsonpath='{.status.readyReplicas}')
  ready_server=$(k -n "$ARGOCD_NAMESPACE" get deployment argocd-server -o jsonpath='{.status.readyReplicas}')
  (( ready_repo >= 2 && ready_server >= 2 )) || die 'HA replicaが回復していません'
  wait_synced_healthy "$(extended_name high-availability)"
  images=$(k -n "$ARGOCD_NAMESPACE" get pods -o json | jq '[.items[].status.containerStatuses[]?|{name:.name,image:.image,imageID:.imageID}] | unique_by(.imageID)')
  jq --arg after "$leader_after" --arg after_uid "$leader_after_uid" --argjson repo "$ready_repo" --argjson server "$ready_server" --argjson images "$images" \
    '.high_availability.redis += {leader_after:$after,leader_uid_after:$after_uid,master_process_recovered:true} | .high_availability += {repo_server_ready:$repo,api_server_ready:$server,application_read_path_available:true,runtime_images:$images,non_guarantee:"単一Kind host自体の障害耐性、network partition、Redis全停止、別ordinalへの昇格は実証対象外"}' \
    "$(extended_trace_file high-availability)" >"$(extended_trace_file high-availability).tmp"
  mv "$(extended_trace_file high-availability).tmp" "$(extended_trace_file high-availability)"
  extended_capture high-availability
}

phase_cleanup() { isolated_cleanup high-availability; }
