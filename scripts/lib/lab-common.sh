#!/usr/bin/env bash
set -euo pipefail

ATLAS_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
readonly ATLAS_ROOT
readonly ATLAS_ID="argocd-reference-atlas"
readonly CLUSTER_NAME="argocd-atlas-v3-5-2"
readonly EXPECTED_CONTEXT="kind-${CLUSTER_NAME}"
readonly ARGOCD_NAMESPACE="argocd"
readonly SOURCE_URL="http://source-server.argocd-atlas-source.svc.cluster.local/repo.git"
readonly RUNTIME_DIR="${ATLAS_ROOT}/.runtime"

die() { printf 'エラー: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*" >&2; }

require_commands() {
  local command_name
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || die "必要なcommandがありません: ${command_name}"
  done
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

assert_runtime_path() {
  case "$1" in
    "${RUNTIME_DIR}"/*) ;;
    *) die "生成物pathが.runtime外です: $1" ;;
  esac
}

cluster_exists() {
  kind get clusters 2>/dev/null | grep -Fxq "$CLUSTER_NAME"
}

assert_dedicated_context() {
  local actual
  cluster_exists || die "専用Kind clusterがありません: ${CLUSTER_NAME}"
  actual=$(kubectl config current-context 2>/dev/null || true)
  [[ "$actual" == "$EXPECTED_CONTEXT" ]] || die "操作を拒否しました。context=${actual:-none}, required=${EXPECTED_CONTEXT}"
  kubectl --context "$EXPECTED_CONTEXT" get namespace kube-system >/dev/null
}

k() {
  assert_dedicated_context
  kubectl --context "$EXPECTED_CONTEXT" "$@"
}

lab_namespace() { printf 'atlas-%s\n' "$1"; }
lab_app() { printf 'atlas-%s\n' "$1"; }

resolve_source_revision() {
  git --git-dir="${RUNTIME_DIR}/source/repo.git" rev-parse --verify "refs/heads/$1"
}

wait_for_app_field() {
  local app=$1 jsonpath=$2 expected=$3 timeout_seconds=${4:-180}
  local elapsed=0 actual
  while (( elapsed < timeout_seconds )); do
    actual=$(k -n "$ARGOCD_NAMESPACE" get application "$app" -o "jsonpath=${jsonpath}" 2>/dev/null || true)
    [[ "$actual" == "$expected" ]] && return 0
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "Application ${app}の待機がtimeoutしました: ${jsonpath}=${expected}"
}

refresh_app() {
  k -n "$ARGOCD_NAMESPACE" annotate application "$1" argocd.argoproj.io/refresh=hard --overwrite >/dev/null
}

request_sync() {
  local app=$1 revision=${2:-}
  if [[ -n "$revision" ]]; then
    revision=$(resolve_source_revision "$revision")
    k -n "$ARGOCD_NAMESPACE" patch application "$app" --type json \
      -p "[{\"op\":\"replace\",\"path\":\"/spec/source/targetRevision\",\"value\":\"${revision}\"}]" >/dev/null
  fi
  k -n "$ARGOCD_NAMESPACE" patch application "$app" --type merge \
    -p '{"operation":{"sync":{"prune":true}}}' >/dev/null
}

wait_synced_healthy() {
  wait_for_app_field "$1" '{.status.sync.status}' Synced 240
  wait_for_app_field "$1" '{.status.health.status}' Healthy 240
}

wait_for_configmap_value() {
  local namespace=$1 name=$2 key=$3 expected=$4 timeout_seconds=${5:-180}
  local elapsed=0 actual
  while (( elapsed < timeout_seconds )); do
    actual=$(k -n "$namespace" get configmap "$name" -o "jsonpath={.data.${key}}" 2>/dev/null || true)
    [[ "$actual" == "$expected" ]] && return 0
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "ConfigMap ${namespace}/${name}の値が収束しません: ${key}=${expected}"
}
