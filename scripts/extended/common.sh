#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/../lib/lab-common.sh"

readonly EXTENDED_RUNTIME="${RUNTIME_DIR}/extended"
readonly SUPPORT_IMAGE="python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc"

extended_lab_id() { printf 'lab.%s\n' "$1"; }
extended_evidence_id() { printf 'evidence.%s.v3-5-2\n' "$1"; }
extended_name() { printf 'atlas-extended-%s\n' "$1"; }
extended_namespace() { extended_name "$1"; }
extended_trace_file() { printf '%s/traces/%s.json\n' "$EXTENDED_RUNTIME" "$1"; }

extended_init() {
  mkdir -p "${EXTENDED_RUNTIME}/traces" "${EXTENDED_RUNTIME}/backup" "${EXTENDED_RUNTIME}/downloads"
  printf '{}\n' >"$(extended_trace_file "$1")"
}

extended_wait_jsonpath() {
  local namespace=$1 resource=$2 jsonpath=$3 expected=$4 timeout_seconds=${5:-240}
  local elapsed=0 actual
  while (( elapsed < timeout_seconds )); do
    actual=$(k -n "$namespace" get "$resource" -o "jsonpath=${jsonpath}" 2>/dev/null || true)
    [[ "$actual" == "$expected" ]] && return 0
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "待機がtimeoutしました: ${namespace}/${resource} ${jsonpath}=${expected}"
}

extended_wait_absent() {
  local namespace=$1 resource=$2 timeout_seconds=${3:-180} elapsed=0
  while (( elapsed < timeout_seconds )); do
    if ! k -n "$namespace" get "$resource" >/dev/null 2>&1; then return 0; fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "Resourceが削除されません: ${namespace}/${resource}"
}

extended_wait_nonempty_jsonpath() {
  local namespace=$1 resource=$2 jsonpath=$3 timeout_seconds=${4:-180} elapsed=0 actual
  while (( elapsed < timeout_seconds )); do
    actual=$(k -n "$namespace" get "$resource" -o "jsonpath=${jsonpath}" 2>/dev/null || true)
    [[ -n "$actual" ]] && return 0
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "Fieldが設定されません: ${namespace}/${resource} ${jsonpath}"
}

extended_apply_project_app() {
  local lab=$1 path=$2 revision_ref=${3:-main} destination_server=${4:-https://kubernetes.default.svc}
  local name namespace revision
  name=$(extended_name "$lab")
  namespace=$(extended_namespace "$lab")
  revision=$(resolve_source_revision "$revision_ref")
  k create namespace "$namespace" --dry-run=client -o yaml | k apply -f - >/dev/null
  cat <<EOF | k apply -f - >/dev/null
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: ${name}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  sourceRepos: [${SOURCE_URL}]
  destinations:
    - namespace: ${namespace}
      server: ${destination_server}
  namespaceResourceWhitelist:
    - group: '*'
      kind: '*'
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${name}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  project: ${name}
  source:
    repoURL: ${SOURCE_URL}
    targetRevision: ${revision}
    path: ${path}
  destination:
    server: ${destination_server}
    namespace: ${namespace}
  syncPolicy:
    syncOptions: [CreateNamespace=true]
EOF
  request_sync "$name"
  wait_synced_healthy "$name"
}

extended_cleanup_project_app() {
  local lab=$1 name namespace
  name=$(extended_name "$lab")
  namespace=$(extended_namespace "$lab")
  k -n "$ARGOCD_NAMESPACE" delete application "$name" --ignore-not-found --wait=true >/dev/null
  k -n "$ARGOCD_NAMESPACE" delete appproject "$name" --ignore-not-found >/dev/null
  k delete namespace "$namespace" --ignore-not-found --wait=true >/dev/null
}

extended_download_verified() {
  local url=$1 expected=$2 output=$3
  assert_runtime_path "$output"
  curl --fail --silent --show-error --location "$url" -o "$output"
  [[ "$(sha256_file "$output")" == "$expected" ]] || die "download digestが一致しません: ${url}"
}

extended_capture() {
  local lab=$1 trace raw_dir artifact namespace
  trace=$(extended_trace_file "$lab")
  namespace=$(extended_namespace "$lab")
  raw_dir="${ATLAS_ROOT}/evidence/raw/$(extended_evidence_id "$lab")"
  artifact="${raw_dir}/result.json"
  mkdir -p "$raw_dir"
  [[ -s "$trace" ]] || printf '{}\n' >"$trace"

  local applications projects appsets workloads topology secret_metadata
  applications=$(k -n "$ARGOCD_NAMESPACE" get applications -o json | jq --arg prefix 'atlas-extended-' '{apiVersion,kind,items:[.items[]|select(.metadata.name|startswith($prefix))]}')
  projects=$(k -n "$ARGOCD_NAMESPACE" get appprojects -o json | jq --arg prefix 'atlas-extended-' '{apiVersion,kind,items:[.items[]|select(.metadata.name|startswith($prefix))]}')
  appsets=$(k -n "$ARGOCD_NAMESPACE" get applicationsets -o json | jq --arg prefix 'atlas-extended-' '{apiVersion,kind,items:[.items[]|select(.metadata.name|startswith($prefix))]}')
  if k get namespace "$namespace" >/dev/null 2>&1; then
    workloads=$(k -n "$namespace" get all,configmaps -o json)
  else
    workloads='{"apiVersion":"v1","kind":"List","items":[]}'
  fi
  topology=$(k -n "$ARGOCD_NAMESPACE" get deployments,statefulsets,serviceaccounts,rolebindings -o json)
  secret_metadata=$(k -n "$ARGOCD_NAMESPACE" get secrets -o json | jq '{apiVersion,kind,items:[.items[]|select(.metadata.labels["argocd.argoproj.io/secret-type"] != null)|{metadata:{name:.metadata.name,namespace:.metadata.namespace,labels:.metadata.labels},type}]}')

  actual_context=$(kubectl config current-context 2>/dev/null || true)
  jq -n \
    --arg atlas_id "$ATLAS_ID" --arg lab_id "$(extended_lab_id "$lab")" --arg evidence_id "$(extended_evidence_id "$lab")" \
    --arg context "$actual_context" --slurpfile trace "$trace" \
    --argjson applications "$applications" --argjson projects "$projects" --argjson appsets "$appsets" \
    --argjson workloads "$workloads" --argjson topology "$topology" --argjson secret_metadata "$secret_metadata" \
    '{schema_version:1,atlas_id:$atlas_id,lab_id:$lab_id,evidence_id:$evidence_id,context:$context,trace:$trace[0],applications:$applications,projects:$projects,applicationsets:$appsets,workloads:$workloads,topology:$topology,connection_secret_metadata:$secret_metadata}' \
    >"$artifact"
  info "extended raw artifactを生成しました: ${artifact}"
}
