#!/usr/bin/env bash

phase_setup() {
  extended_init hook-wave
  extended_apply_project_app hook-wave apps/application main
}

phase_execute() {
  local name revision
  name=$(extended_name hook-wave)
  revision=$(resolve_source_revision hook-wave)
  k -n "$ARGOCD_NAMESPACE" patch application "$name" --type merge -p \
    "{\"spec\":{\"source\":{\"repoURL\":\"${SOURCE_URL}\",\"targetRevision\":\"${revision}\",\"path\":\"apps/hook-wave\"}}}" >/dev/null
  request_sync "$name"
}

phase_verify() {
  local name namespace result pre_index minus_index plus_index post_index
  name=$(extended_name hook-wave)
  namespace=$(extended_namespace hook-wave)
  extended_wait_jsonpath "$ARGOCD_NAMESPACE" "application/${name}" '{.status.operationState.phase}' Succeeded 240
  k -n "$namespace" get configmap atlas-hook-wave-minus-one >/dev/null
  k -n "$namespace" get configmap atlas-hook-wave-one >/dev/null
  extended_wait_absent "$namespace" job/atlas-hook-presync 120
  extended_wait_absent "$namespace" job/atlas-hook-postsync 120
  result=$(k -n "$ARGOCD_NAMESPACE" get application "$name" -o json | jq '.status.operationState.syncResult.resources')
  [[ "$(jq '[.[]|select(.hookType=="PreSync" and .hookPhase=="Succeeded")]|length' <<<"$result")" -ge 1 ]] || die '成功したPreSync resultがありません'
  [[ "$(jq '[.[]|select(.hookType=="PostSync" and .hookPhase=="Succeeded")]|length' <<<"$result")" -ge 1 ]] || die '成功したPostSync resultがありません'
  pre_index=$(jq 'map(.name) | index("atlas-hook-presync")' <<<"$result")
  minus_index=$(jq 'map(.name) | index("atlas-hook-wave-minus-one")' <<<"$result")
  plus_index=$(jq 'map(.name) | index("atlas-hook-wave-one")' <<<"$result")
  post_index=$(jq 'map(.name) | index("atlas-hook-postsync")' <<<"$result")
  [[ "$pre_index" != null && "$minus_index" != null && "$plus_index" != null && "$post_index" != null ]] || die 'Hook/Wave resultが不足しています'
  (( pre_index < minus_index && minus_index < plus_index && plus_index < post_index )) || die 'Hook/Waveの観測順序が不正です'
  jq -n --argjson result "$result" --argjson pre "$pre_index" --argjson minus "$minus_index" --argjson plus "$plus_index" --argjson post "$post_index" \
    '{hook_wave:{operation_phase:"Succeeded",observed_order:{presync:$pre,wave_minus_one:$minus,wave_one:$plus,postsync:$post},hook_jobs_deleted_by_policy:true,resources:$result}}' >"$(extended_trace_file hook-wave)"
  extended_capture hook-wave
}

phase_cleanup() { extended_cleanup_project_app hook-wave; }
