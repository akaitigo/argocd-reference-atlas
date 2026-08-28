#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/lib/lab-common.sh"

lab=${1:-}
phase=${2:-}
dry_run=false
[[ "${3:-}" == '--dry-run' ]] && dry_run=true

case "$lab" in application|reconciliation|sync|diff|health|promotion|security|failure|recovery) ;; *) die "未知のLab IDです: ${lab}" ;; esac
case "$phase" in setup|execute|verify|cleanup) ;; *) die 'usage: scripts/run-lab.sh LAB {setup|execute|verify|cleanup} [--dry-run]' ;; esac

spec="${ATLAS_ROOT}/labs/${lab}/lab.yaml"
[[ -f "$spec" ]] || die "Lab specがありません: ${spec}"
if $dry_run; then
  printf 'lab=%s phase=%s cluster=%s context=%s spec=%s\n' "$lab" "$phase" "$CLUSTER_NAME" "$EXPECTED_CONTEXT" "$spec"
  exit 0
fi

require_commands kind kubectl jq shasum git find grep wc cmp
assert_dedicated_context
app=$(lab_app "$lab")
namespace=$(lab_namespace "$lab")
trace_dir="${RUNTIME_DIR}/traces"
trace_file="${trace_dir}/${lab}.json"
mkdir -p "$trace_dir"

apply_app() {
  local main_revision
  main_revision=$(resolve_source_revision main)
  k create namespace "$namespace" --dry-run=client -o yaml | k apply -f - >/dev/null
  cat <<EOF | k apply -f - >/dev/null
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: ${app}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  sourceRepos: [${SOURCE_URL}]
  destinations:
    - namespace: ${namespace}
      server: https://kubernetes.default.svc
  clusterResourceWhitelist: []
  namespaceResourceWhitelist:
    - group: '*'
      kind: '*'
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${app}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  project: ${app}
  source:
    repoURL: ${SOURCE_URL}
    targetRevision: ${main_revision}
    path: apps/${lab}
  destination:
    server: https://kubernetes.default.svc
    namespace: ${namespace}
  syncPolicy:
    syncOptions: [CreateNamespace=true]
  ignoreDifferences: []
EOF
  request_sync "$app"
  wait_synced_healthy "$app"
}

setup_lab() {
  printf '{}\n' >"$trace_file"
  if [[ "$lab" == failure ]]; then
    k -n argocd-atlas-source scale deployment source-server --replicas=1 >/dev/null
    k -n argocd-atlas-source rollout status deployment/source-server --timeout=180s
  fi
  apply_app
  if [[ "$lab" == security ]]; then
    marker=$(printf '%s' "${CLUSTER_NAME}-$(date -u '+%s')-$$" | shasum -a 256 | awk '{print $1}')
    printf '%s\n' "$marker" >"${RUNTIME_DIR}/security-canary"
    chmod 0600 "${RUNTIME_DIR}/security-canary"
    cat <<EOF | k apply -f - >/dev/null
apiVersion: v1
kind: Secret
metadata:
  name: atlas-local-repo-credentials
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    argocd.argoproj.io/secret-type: repo-creds
type: Opaque
stringData:
  url: ${SOURCE_URL}
  username: local-atlas
  password: ${marker}
EOF
    refresh_app "$app"
    wait_synced_healthy "$app"
  fi
  if [[ "$lab" == recovery ]]; then
    main_revision=$(resolve_source_revision main)
    cat <<EOF | k apply -f - >/dev/null
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ${app}-set
  namespace: ${ARGOCD_NAMESPACE}
spec:
  generators:
    - list:
        elements:
          - name: child
  template:
    metadata:
      name: 'atlas-recovery-generated-{{name}}'
    spec:
      project: ${app}
      source:
        repoURL: ${SOURCE_URL}
        targetRevision: ${main_revision}
        path: apps/recovery
      destination:
        server: https://kubernetes.default.svc
        namespace: ${namespace}
EOF
  fi
}

execute_lab() {
  case "$lab" in
    application) refresh_app "$app" ;;
    reconciliation)
      k -n "$namespace" patch configmap atlas-reconciliation --type merge -p '{"data":{"desired":"live-drift"}}' >/dev/null
      refresh_app "$app"
      wait_for_app_field "$app" '{.status.sync.status}' OutOfSync 180
      jq -n --arg before OutOfSync '{before_sync:{sync_status:$before,live_value:"live-drift"}}' >"$trace_file"
      request_sync "$app"
      ;;
    sync) request_sync "$app" sync-failure ;;
    diff)
      k -n "$namespace" patch configmap atlas-diff --type merge -p '{"data":{"desired":"live-drift"}}' >/dev/null
      refresh_app "$app"
      wait_for_app_field "$app" '{.status.sync.status}' OutOfSync 180
      jq -n '{unignored:{sync_status:"OutOfSync",field:"/data/desired"}}' >"$trace_file"
      k -n "$ARGOCD_NAMESPACE" patch application "$app" --type merge -p \
        '{"spec":{"ignoreDifferences":[{"group":"","kind":"ConfigMap","name":"atlas-diff","jsonPointers":["/data/desired"]}]}}' >/dev/null
      refresh_app "$app"
      ;;
    health) request_sync "$app" health-bad ;;
    promotion)
      before_revision=$(k -n "$ARGOCD_NAMESPACE" get application "$app" -o jsonpath='{.status.sync.revision}')
      jq -n --arg before "$before_revision" '{promotion:{before_revision:$before}}' >"$trace_file"
      request_sync "$app" promotion-candidate
      ;;
    security) refresh_app "$app" ;;
    failure)
      resolve_source_revision main >"${RUNTIME_DIR}/failure-valid-revision"
      k -n argocd-atlas-source scale deployment source-server --replicas=0 >/dev/null
      k -n argocd-atlas-source rollout status deployment/source-server --timeout=180s
      k -n "$ARGOCD_NAMESPACE" delete pod -l app.kubernetes.io/name=argocd-repo-server --wait=true >/dev/null
      k -n "$ARGOCD_NAMESPACE" rollout status deployment/argocd-repo-server --timeout=180s
      k -n "$namespace" patch configmap atlas-failure --type merge -p '{"data":{"release":"drift-during-source-outage"}}' >/dev/null
      k -n "$ARGOCD_NAMESPACE" patch application "$app" --type merge \
        -p '{"spec":{"source":{"targetRevision":"refs/heads/atlas-missing-during-outage"}}}' >/dev/null
      refresh_app "$app"
      wait_for_app_field "$app" '{.status.conditions[?(@.type=="ComparisonError")].type}' ComparisonError 180
      k -n "$ARGOCD_NAMESPACE" get application "$app" -o json |
        jq '{outage:{conditions:.status.conditions,live_value:"drift-during-source-outage"}}' >"$trace_file"
      ;;
    recovery)
      mkdir -p "${RUNTIME_DIR}/recovery"
      k -n "$ARGOCD_NAMESPACE" get appproject "$app" -o json >"${RUNTIME_DIR}/recovery/project.json"
      k -n "$ARGOCD_NAMESPACE" get applicationset "${app}-set" -o json >"${RUNTIME_DIR}/recovery/applicationset.json"
      k -n "$ARGOCD_NAMESPACE" get application "$app" -o json >"${RUNTIME_DIR}/recovery/application.json"
      jq -s 'map({apiVersion,kind,metadata:{name:.metadata.name,namespace:.metadata.namespace},spec}) | sort_by(if .kind == "AppProject" then 0 elif .kind == "ApplicationSet" then 1 else 2 end)' \
        "${RUNTIME_DIR}/recovery/project.json" "${RUNTIME_DIR}/recovery/applicationset.json" "${RUNTIME_DIR}/recovery/application.json" \
        >"${RUNTIME_DIR}/recovery/backup.normalized.json"
      backup_digest=$(sha256_file "${RUNTIME_DIR}/recovery/backup.normalized.json")
      k -n "$ARGOCD_NAMESPACE" delete application "$app" --wait=true >/dev/null
      k -n "$ARGOCD_NAMESPACE" delete applicationset "${app}-set" --wait=true >/dev/null
      k -n "$ARGOCD_NAMESPACE" delete appproject "$app" --wait=true >/dev/null
      jq '{apiVersion:"v1",kind:"List",items:.}' "${RUNTIME_DIR}/recovery/backup.normalized.json" | k apply -f - >/dev/null
      jq -n --arg digest "sha256:${backup_digest}" --slurpfile backup "${RUNTIME_DIR}/recovery/backup.normalized.json" \
        '{recovery:{backup_digest:$digest,backup:$backup[0]}}' >"$trace_file"
      ;;
  esac
}

verify_lab() {
  local revision=main
  case "$lab" in
    application) wait_synced_healthy "$app" ;;
    reconciliation)
      wait_for_configmap_value "$namespace" atlas-reconciliation desired canonical 240
      wait_synced_healthy "$app"
      jq '. + {after_sync:{sync_status:"Synced",live_value:"canonical"}}' "$trace_file" >"${trace_file}.tmp"
      mv "${trace_file}.tmp" "$trace_file"
      ;;
    sync)
      wait_for_app_field "$app" '{.status.operationState.phase}' Failed 240
      k -n "$namespace" get configmap atlas-sync-before >/dev/null
      if k -n "$namespace" get configmap atlas-sync-after >/dev/null 2>&1; then
        die '失敗waveより後のResourceが適用されました'
      fi
      k -n "$ARGOCD_NAMESPACE" get application "$app" -o json |
        jq '{sync:{phase:.status.operationState.phase,result:.status.operationState.syncResult.resources,before_applied:true,after_applied:false}}' >"$trace_file"
      revision=sync-failure
      ;;
    diff)
      wait_for_app_field "$app" '{.status.sync.status}' Synced 180
      jq '. + {ignored:{sync_status:"Synced",field:"/data/desired"}}' "$trace_file" >"${trace_file}.tmp"
      mv "${trace_file}.tmp" "$trace_file"
      ;;
    health)
      wait_for_app_field "$app" '{.status.health.status}' Degraded 240
      revision=health-bad
      ;;
    promotion)
      wait_for_configmap_value "$namespace" atlas-promotion release candidate 240
      wait_synced_healthy "$app"
      after_revision=$(k -n "$ARGOCD_NAMESPACE" get application "$app" -o jsonpath='{.status.sync.revision}')
      jq --arg after "$after_revision" '.promotion.after_revision=$after' "$trace_file" >"${trace_file}.tmp"
      mv "${trace_file}.tmp" "$trace_file"
      revision=promotion-candidate
      ;;
    security)
      wait_synced_healthy "$app"
      marker=$(<"${RUNTIME_DIR}/security-canary")
      if k -n "$namespace" get secrets -o json | jq -e --arg marker "$marker" '.items[].data? | values[]? | @base64d | contains($marker)' >/dev/null; then
        die 'destination namespaceへのCredential漏洩を検出しました'
      fi
      repo_hits=$(
        { find "$ATLAS_ROOT" -path "${ATLAS_ROOT}/.git" -prune -o -path "${RUNTIME_DIR}" -prune -o -path "${ATLAS_ROOT}/evidence/raw" -prune -o -type f -exec grep -lF "$marker" {} + || true; } |
          wc -l | tr -d ' '
      )
      source_hits=$(
        while IFS= read -r source_ref; do
          git --git-dir="${RUNTIME_DIR}/source/repo.git" grep -lF "$marker" "$source_ref" -- 2>/dev/null || true
        done < <(git --git-dir="${RUNTIME_DIR}/source/repo.git" for-each-ref --format='%(refname)' refs/heads) |
          wc -l | tr -d ' '
      )
      evidence_hits=$(
        { find "${ATLAS_ROOT}/evidence" -type f -exec grep -lF "$marker" {} + 2>/dev/null || true; } |
          wc -l | tr -d ' '
      )
      [[ "$repo_hits" == 0 && "$source_hits" == 0 && "$evidence_hits" == 0 ]] || die 'runtime canaryがRepositoryまたはEvidenceへ残っています'
      jq -n --argjson repo_hits "$repo_hits" --argjson source_hits "$source_hits" --argjson evidence_hits "$evidence_hits" \
        '{secret_boundary:{destination_leak:false,atlas_repository_scan_hits:$repo_hits,git_source_scan_hits:$source_hits,evidence_scan_hits:$evidence_hits,canary_redacted:true}}' >"$trace_file"
      ;;
    failure)
      [[ "$(k -n argocd-atlas-source get deployment source-server -o jsonpath='{.spec.replicas}')" == 0 ]] || die 'failure injectionが維持されていません'
      k -n argocd-atlas-source scale deployment source-server --replicas=1 >/dev/null
      k -n argocd-atlas-source rollout status deployment/source-server --timeout=180s
      valid_revision=$(<"${RUNTIME_DIR}/failure-valid-revision")
      k -n "$ARGOCD_NAMESPACE" patch application "$app" --type merge \
        -p "{\"spec\":{\"source\":{\"targetRevision\":\"${valid_revision}\"}}}" >/dev/null
      recovered=false
      for _ in {1..90}; do
        refresh_app "$app"
        if [[ "$(k -n "$ARGOCD_NAMESPACE" get application "$app" -o jsonpath='{.status.sync.status}' 2>/dev/null || true)" == OutOfSync ]]; then
          recovered=true
          break
        fi
        sleep 2
      done
      $recovered || die 'Source復旧後にApplicationが再比較されませんでした'
      request_sync "$app"
      wait_for_configmap_value "$namespace" atlas-failure release v1 240
      wait_synced_healthy "$app"
      jq '. + {recovered:{source_replicas:1,sync_status:"Synced",live_value:"v1"}}' "$trace_file" >"${trace_file}.tmp"
      mv "${trace_file}.tmp" "$trace_file"
      ;;
    recovery)
      wait_synced_healthy "$app"
      k -n "$ARGOCD_NAMESPACE" get appproject "$app" -o json >"${RUNTIME_DIR}/recovery/project.restored.json"
      k -n "$ARGOCD_NAMESPACE" get applicationset "${app}-set" -o json >"${RUNTIME_DIR}/recovery/applicationset.restored.json"
      k -n "$ARGOCD_NAMESPACE" get application "$app" -o json >"${RUNTIME_DIR}/recovery/application.restored.json"
      jq -s 'map({apiVersion,kind,metadata:{name:.metadata.name,namespace:.metadata.namespace},spec}) | sort_by(if .kind == "AppProject" then 0 elif .kind == "ApplicationSet" then 1 else 2 end)' \
        "${RUNTIME_DIR}/recovery/project.restored.json" "${RUNTIME_DIR}/recovery/applicationset.restored.json" "${RUNTIME_DIR}/recovery/application.restored.json" \
        >"${RUNTIME_DIR}/recovery/restored.normalized.json"
      cmp "${RUNTIME_DIR}/recovery/backup.normalized.json" "${RUNTIME_DIR}/recovery/restored.normalized.json" >/dev/null || die 'restore後の正規化specがBackupと一致しません'
      restored_digest=$(sha256_file "${RUNTIME_DIR}/recovery/restored.normalized.json")
      jq --arg digest "sha256:${restored_digest}" --slurpfile restored "${RUNTIME_DIR}/recovery/restored.normalized.json" \
        '.recovery.restored_digest=$digest | .recovery.restored=$restored[0] | .recovery.specs_equal=true' "$trace_file" >"${trace_file}.tmp"
      mv "${trace_file}.tmp" "$trace_file"
      ;;
  esac
  "${ATLAS_ROOT}/scripts/evidence/capture.sh" "$lab" "$revision"
}

cleanup_lab() {
  if [[ "$lab" == failure ]]; then
    k -n argocd-atlas-source scale deployment source-server --replicas=1 >/dev/null
    k -n argocd-atlas-source rollout status deployment/source-server --timeout=180s
  fi
  k -n "$ARGOCD_NAMESPACE" delete application "$app" --ignore-not-found --wait=true >/dev/null
  [[ "$lab" != recovery ]] || k -n "$ARGOCD_NAMESPACE" delete applicationset "${app}-set" --ignore-not-found --wait=true >/dev/null
  k -n "$ARGOCD_NAMESPACE" delete appproject "$app" --ignore-not-found >/dev/null
  [[ "$lab" != security ]] || k -n "$ARGOCD_NAMESPACE" delete secret atlas-local-repo-credentials --ignore-not-found >/dev/null
  if [[ "$lab" == security ]]; then
    rm -f -- "${RUNTIME_DIR}/security-canary"
  fi
  k delete namespace "$namespace" --ignore-not-found --wait=true >/dev/null
}

case "$phase" in
  setup) setup_lab ;;
  execute) execute_lab ;;
  verify) verify_lab ;;
  cleanup) cleanup_lab ;;
esac
