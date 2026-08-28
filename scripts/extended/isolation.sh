#!/usr/bin/env bash

isolated_cluster_exists() {
  kind get clusters 2>/dev/null | grep -Fxq "$ISO_CLUSTER"
}

isolated_assert() {
  local actual
  isolated_cluster_exists || die "隔離Kind clusterがありません: ${ISO_CLUSTER}"
  actual=$(kubectl config current-context 2>/dev/null || true)
  [[ "$actual" == "$ISO_CONTEXT" ]] || die "操作を拒否しました。context=${actual:-none}, required=${ISO_CONTEXT}"
  kubectl --context "$ISO_CONTEXT" get namespace kube-system >/dev/null
}

isolated_k() {
  isolated_assert
  kubectl --context "$ISO_CONTEXT" "$@"
}

isolated_setup() {
  local node_count=$1 install_url_arg=$2 install_sha_arg=$3 profile=$4
  local config manifest previous current source_path i
  "${ATLAS_ROOT}/scripts/build-local-source.sh"
  config="${EXTENDED_RUNTIME}/${profile}-kind-config.yaml"
  manifest="${EXTENDED_RUNTIME}/downloads/${profile}-argocd-install.yaml"
  previous="${EXTENDED_RUNTIME}/${profile}-previous-context"
  current=$(kubectl config current-context 2>/dev/null || true)
  if [[ -n "$current" && "$current" != "$ISO_CONTEXT" ]]; then printf '%s\n' "$current" >"$previous"; fi
  source_path="${RUNTIME_DIR}/source"
  {
    printf '%s\n' 'kind: Cluster' 'apiVersion: kind.x-k8s.io/v1alpha4' 'nodes:'
    for ((i=0; i<node_count; i++)); do
      if (( i == 0 )); then printf '%s\n' '  - role: control-plane'; else printf '%s\n' '  - role: worker'; fi
      printf '%s\n' '    image: kindest/node:v1.34.0@sha256:7416a61b42b1662ca6ca89f02028ac133a309a2a30ba309614e8ec94d976dc5a'
      printf '%s\n' '    extraMounts:' "      - hostPath: ${source_path}" '        containerPath: /atlas-source' '        readOnly: true'
    done
  } >"$config"
  if ! isolated_cluster_exists; then kind create cluster --name "$ISO_CLUSTER" --config "$config"; fi
  kubectl config use-context "$ISO_CONTEXT" >/dev/null
  isolated_assert
  if (( node_count > 1 )); then
    isolated_k taint nodes --all node-role.kubernetes.io/control-plane- >/dev/null 2>&1 || true
  fi
  extended_download_verified "$install_url_arg" "$install_sha_arg" "$manifest"
  isolated_k create namespace "$ARGOCD_NAMESPACE" --dry-run=client -o yaml | isolated_k apply -f - >/dev/null
  isolated_k -n "$ARGOCD_NAMESPACE" apply --server-side --force-conflicts -f "$manifest" >/dev/null
  isolated_k apply -f "${ATLAS_ROOT}/environments/kind/source-server.yaml" >/dev/null
  isolated_k -n argocd-atlas-source rollout status deployment/source-server --timeout=240s
  isolated_k -n "$ARGOCD_NAMESPACE" rollout status deployment/argocd-repo-server --timeout=480s
  isolated_k -n "$ARGOCD_NAMESPACE" rollout status statefulset/argocd-application-controller --timeout=480s
}

isolated_cleanup() {
  local profile=$1 previous saved
  previous="${EXTENDED_RUNTIME}/${profile}-previous-context"
  if isolated_cluster_exists; then kind delete cluster --name "$ISO_CLUSTER"; fi
  if [[ -s "$previous" ]]; then
    saved=$(<"$previous")
    if kubectl config get-contexts "$saved" -o name 2>/dev/null | grep -Fxq "$saved"; then kubectl config use-context "$saved" >/dev/null; fi
  fi
}
