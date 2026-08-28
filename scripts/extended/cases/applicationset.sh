#!/usr/bin/env bash

phase_setup() {
  extended_init applicationset
  local name revision
  name=$(extended_name applicationset)
  revision=$(resolve_source_revision main)
  cat <<EOF | k apply -f - >/dev/null
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: ${name}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  sourceRepos: [${SOURCE_URL}]
  destinations:
    - namespace: 'atlas-extended-applicationset-*'
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: ''
      kind: Namespace
  namespaceResourceWhitelist:
    - group: '*'
      kind: '*'
---
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ${name}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  generators:
    - list:
        elements:
          - name: blue
          - name: green
  template:
    metadata:
      name: '${name}-{{name}}'
    spec:
      project: ${name}
      source:
        repoURL: ${SOURCE_URL}
        targetRevision: ${revision}
        path: apps/application
      destination:
        server: https://kubernetes.default.svc
        namespace: '${name}-{{name}}'
      syncPolicy:
        automated: {prune: true, selfHeal: true}
        syncOptions: [CreateNamespace=true]
EOF
  extended_wait_jsonpath "$ARGOCD_NAMESPACE" "application/${name}-blue" '{.status.sync.status}' Synced 240
  extended_wait_jsonpath "$ARGOCD_NAMESPACE" "application/${name}-green" '{.status.sync.status}' Synced 240
}

phase_execute() {
  local name
  name=$(extended_name applicationset)
  k -n "$ARGOCD_NAMESPACE" patch applicationset "$name" --type merge -p '{"spec":{"generators":[{"list":{"elements":[{"name":"blue"}]}}]}}' >/dev/null
}

phase_verify() {
  local name blue_spec expected_revision
  name=$(extended_name applicationset)
  extended_wait_absent "$ARGOCD_NAMESPACE" "application/${name}-green" 240
  extended_wait_jsonpath "$ARGOCD_NAMESPACE" "application/${name}-blue" '{.status.sync.status}' Synced 240
  expected_revision=$(resolve_source_revision main)
  blue_spec=$(k -n "$ARGOCD_NAMESPACE" get application "${name}-blue" -o json | jq '.spec')
  [[ "$(jq -r '.source.targetRevision' <<<"$blue_spec")" == "$expected_revision" ]] || die '生成ApplicationのrevisionがTemplateと一致しません'
  [[ "$(jq -r '.destination.namespace' <<<"$blue_spec")" == "${name}-blue" ]] || die '生成ApplicationのdestinationがTemplate結果と一致しません'
  jq -n --arg retained "${name}-blue" --arg removed "${name}-green" --argjson spec "$blue_spec" \
    '{applicationset:{retained_application:$retained,removed_application:$removed,generator_count:1,normalized_generated_spec:$spec,template_match:true}}' >"$(extended_trace_file applicationset)"
  extended_capture applicationset
}

phase_cleanup() {
  local name
  name=$(extended_name applicationset)
  k -n "$ARGOCD_NAMESPACE" delete applicationset "$name" --ignore-not-found --wait=true >/dev/null
  k -n "$ARGOCD_NAMESPACE" delete appproject "$name" --ignore-not-found >/dev/null
  k delete namespace "${name}-blue" "${name}-green" --ignore-not-found --wait=true >/dev/null
}
