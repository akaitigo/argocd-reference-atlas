#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/lib/lab-common.sh"

lock_file="${ATLAS_ROOT}/environments/kind/argocd-v3.5.2.lock"
# shellcheck disable=SC1090
. "$lock_file"

setup_environment() {
  require_commands kind kubectl curl git shasum
  local current_context previous_context_file
  previous_context_file="${RUNTIME_DIR}/previous-kube-context"
  mkdir -p "${RUNTIME_DIR}"
  current_context=$(kubectl config current-context 2>/dev/null || true)
  if [[ -n "$current_context" && "$current_context" != "$EXPECTED_CONTEXT" ]]; then
    printf '%s\n' "$current_context" >"$previous_context_file"
  fi
  "${ATLAS_ROOT}/scripts/build-local-source.sh"
  mkdir -p "${RUNTIME_DIR}/downloads"
  local rendered="${RUNTIME_DIR}/kind-config.yaml"
  local source_path="${RUNTIME_DIR}/source"
  sed "s|__SOURCE_PATH__|${source_path}|g" "${ATLAS_ROOT}/environments/kind/kind-config.yaml.tmpl" >"$rendered"
  if ! cluster_exists; then
    kind create cluster --name "$CLUSTER_NAME" --config "$rendered"
  fi
  kubectl config use-context "$EXPECTED_CONTEXT" >/dev/null
  assert_dedicated_context

  curl --fail --silent --show-error --location "$install_url" -o "${RUNTIME_DIR}/downloads/argocd-install.yaml"
  curl --fail --silent --show-error --location "$version_url" -o "${RUNTIME_DIR}/downloads/argocd-VERSION"
  [[ "$(sha256_file "${RUNTIME_DIR}/downloads/argocd-install.yaml")" == "$install_sha256" ]] || die 'Argo CD install manifestのdigestが一致しません'
  [[ "$(sha256_file "${RUNTIME_DIR}/downloads/argocd-VERSION")" == "$version_sha256" ]] || die 'Argo CD VERSIONのdigestが一致しません'

  k create namespace "$ARGOCD_NAMESPACE" --dry-run=client -o yaml | k apply -f - >/dev/null
  k -n "$ARGOCD_NAMESPACE" apply --server-side --force-conflicts -f "${RUNTIME_DIR}/downloads/argocd-install.yaml" >/dev/null
  k apply -f "${ATLAS_ROOT}/environments/kind/source-server.yaml" >/dev/null
  k -n argocd-atlas-source rollout status deployment/source-server --timeout=180s
  k -n "$ARGOCD_NAMESPACE" rollout status deployment/argocd-repo-server --timeout=300s
  k -n "$ARGOCD_NAMESPACE" rollout status statefulset/argocd-application-controller --timeout=300s
  info 'Argo CD v3.5.2専用Kind environmentの準備が完了しました'
}

cleanup_environment() {
  require_commands kind kubectl
  local previous_context previous_context_file
  previous_context_file="${RUNTIME_DIR}/previous-kube-context"
  if cluster_exists; then
    kind delete cluster --name "$CLUSTER_NAME"
  fi
  if [[ -s "$previous_context_file" ]]; then
    previous_context=$(<"$previous_context_file")
    if kubectl config get-contexts "$previous_context" -o name 2>/dev/null | grep -Fxq "$previous_context"; then
      kubectl config use-context "$previous_context" >/dev/null
      info "元のkubectl contextを復元しました: ${previous_context}"
    fi
  fi
  info '専用Kind clusterを削除しました。Evidenceは保持します'
}

case "${1:-}" in
  setup) setup_environment ;;
  cleanup) cleanup_environment ;;
  --dry-run|dry-run)
    printf 'cluster=%s context=%s version=%s install_sha256=%s node_image=%s source_image=%s\n' \
      "$CLUSTER_NAME" "$EXPECTED_CONTEXT" "$version" "$install_sha256" "$kind_node_image" "$source_server_image"
    ;;
  *) die 'usage: scripts/environment.sh {setup|cleanup|dry-run}' ;;
esac
