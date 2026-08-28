#!/usr/bin/env bash

phase_setup() {
  extended_init connection
  local name namespace token ca revision
  name=$(extended_name connection)
  namespace=$(extended_namespace connection)
  revision=$(resolve_source_revision main)
  k create namespace "$namespace" --dry-run=client -o yaml | k apply -f - >/dev/null
  k -n "$namespace" create serviceaccount atlas-connection --dry-run=client -o yaml | k apply -f - >/dev/null
  cat <<EOF | k apply -f - >/dev/null
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ${name}
rules:
  - apiGroups: ['*']
    resources: ['*']
    verbs: [get, list, watch]
  - apiGroups: ['']
    resources: [configmaps]
    verbs: [create, update, patch, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${name}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: ${name}
subjects:
  - kind: ServiceAccount
    name: atlas-connection
    namespace: ${namespace}
EOF
  token=$(k -n "$namespace" create token atlas-connection --duration=15m)
  ca=$(kubectl --context "$EXPECTED_CONTEXT" config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')
  cat <<EOF | k apply -f - >/dev/null
apiVersion: v1
kind: Secret
metadata:
  name: ${name}-repository
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    argocd.argoproj.io/secret-type: repository
type: Opaque
stringData:
  type: git
  url: ${SOURCE_URL}
---
apiVersion: v1
kind: Secret
metadata:
  name: ${name}-cluster
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: atlas-connection-local
  server: https://kubernetes.default.svc.cluster.local
  namespaces: ${namespace}
  clusterResources: "false"
  config: '{"bearerToken":"${token}","tlsClientConfig":{"insecure":false,"caData":"${ca}"}}'
---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: ${name}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  sourceRepos: [${SOURCE_URL}, 'http://unreachable.invalid/repo.git']
  destinations:
    - namespace: ${namespace}
      server: https://kubernetes.default.svc.cluster.local
    - namespace: ${namespace}
      server: https://unreachable.invalid
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
    path: apps/application
  destination:
    server: https://kubernetes.default.svc.cluster.local
    namespace: ${namespace}
  syncPolicy:
    syncOptions: [CreateNamespace=true]
EOF
  request_sync "$name"
}

phase_execute() {
  local name revision namespace
  name=$(extended_name connection)
  namespace=$(extended_namespace connection)
  revision=$(resolve_source_revision main)
  refresh_app "$name"
  cat <<EOF | k apply -f - >/dev/null
apiVersion: v1
kind: Secret
metadata:
  name: ${name}-repository-invalid
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    argocd.argoproj.io/secret-type: repository
type: Opaque
stringData:
  type: git
  url: http://unreachable.invalid/repo.git
---
apiVersion: v1
kind: Secret
metadata:
  name: ${name}-cluster-invalid
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: atlas-connection-invalid
  server: https://unreachable.invalid
  config: '{"tlsClientConfig":{"insecure":true}}'
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${name}-invalid-repository
  namespace: ${ARGOCD_NAMESPACE}
spec:
  project: ${name}
  source:
    repoURL: http://unreachable.invalid/repo.git
    targetRevision: ${revision}
    path: apps/application
  destination:
    server: https://kubernetes.default.svc.cluster.local
    namespace: ${namespace}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${name}-invalid-cluster
  namespace: ${ARGOCD_NAMESPACE}
spec:
  project: ${name}
  source:
    repoURL: ${SOURCE_URL}
    targetRevision: ${revision}
    path: apps/application
  destination:
    server: https://unreachable.invalid
    namespace: ${namespace}
EOF
  refresh_app "${name}-invalid-repository"
  refresh_app "${name}-invalid-cluster"
}

phase_verify() {
  local name metadata invalid_repo_conditions invalid_cluster_conditions
  name=$(extended_name connection)
  wait_synced_healthy "$name"
  extended_wait_nonempty_jsonpath "$ARGOCD_NAMESPACE" "application/${name}-invalid-repository" '{.status.conditions[0].type}' 180
  extended_wait_nonempty_jsonpath "$ARGOCD_NAMESPACE" "application/${name}-invalid-cluster" '{.status.conditions[0].type}' 180
  [[ "$(k -n "$ARGOCD_NAMESPACE" get application "${name}-invalid-repository" -o jsonpath='{.status.sync.status}')" != Synced ]] || die '無効Repositoryが成功扱いです'
  [[ "$(k -n "$ARGOCD_NAMESPACE" get application "${name}-invalid-cluster" -o jsonpath='{.status.sync.status}')" != Synced ]] || die '無効Clusterが成功扱いです'
  metadata=$(k -n "$ARGOCD_NAMESPACE" get secrets -o json | jq --arg prefix "${name}-" '[.items[]|select(.metadata.name|startswith($prefix))|{name:.metadata.name,secret_type:.metadata.labels["argocd.argoproj.io/secret-type"],type}]')
  invalid_repo_conditions=$(k -n "$ARGOCD_NAMESPACE" get application "${name}-invalid-repository" -o json | jq '.status.conditions')
  invalid_cluster_conditions=$(k -n "$ARGOCD_NAMESPACE" get application "${name}-invalid-cluster" -o json | jq '.status.conditions')
  jq -n --argjson metadata "$metadata" --argjson repo_conditions "$invalid_repo_conditions" --argjson cluster_conditions "$invalid_cluster_conditions" \
    '{connection:{valid_application_synced:true,invalid_repository_rejected:true,invalid_cluster_rejected:true,invalid_repository_conditions:$repo_conditions,invalid_cluster_conditions:$cluster_conditions,secrets:$metadata,credential_values_captured:false}}' >"$(extended_trace_file connection)"
  extended_capture connection
}

phase_cleanup() {
  local name namespace
  name=$(extended_name connection)
  namespace=$(extended_namespace connection)
  k -n "$ARGOCD_NAMESPACE" delete applications "${name}-invalid-repository" "${name}-invalid-cluster" --ignore-not-found --wait=true >/dev/null
  extended_cleanup_project_app connection
  k -n "$ARGOCD_NAMESPACE" delete secrets "${name}-repository" "${name}-cluster" "${name}-repository-invalid" "${name}-cluster-invalid" --ignore-not-found >/dev/null
  k delete clusterrolebinding "$name" --ignore-not-found >/dev/null
  k delete clusterrole "$name" --ignore-not-found >/dev/null
  k delete namespace "$namespace" --ignore-not-found --wait=true >/dev/null
}
