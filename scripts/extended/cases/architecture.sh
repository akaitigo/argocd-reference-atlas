#!/usr/bin/env bash

phase_setup() {
  extended_init architecture
  local name
  name=$(extended_name architecture)
  cat <<EOF | k apply -f - >/dev/null
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: ${name}
  namespace: ${ARGOCD_NAMESPACE}
spec:
  sourceRepos: [${SOURCE_URL}]
  destinations:
    - namespace: atlas-extended-architecture
      server: https://kubernetes.default.svc
  namespaceResourceWhitelist:
    - group: '*'
      kind: '*'
---
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
  name: architecture-local
  server: https://architecture.invalid.example
  config: '{}'
EOF
}

phase_execute() {
  local name
  name=$(extended_name architecture)
  k -n "$ARGOCD_NAMESPACE" annotate appproject "$name" atlas.openai.com/topology-probe="$(date -u '+%Y%m%dT%H%M%SZ')" --overwrite >/dev/null
}

phase_verify() {
  local name workloads sas bindings missing_sa missing_subject
  name=$(extended_name architecture)
  for resource in deployment/argocd-server deployment/argocd-repo-server deployment/argocd-applicationset-controller statefulset/argocd-application-controller; do
    k -n "$ARGOCD_NAMESPACE" get "$resource" >/dev/null
  done
  workloads=$(k -n "$ARGOCD_NAMESPACE" get deployments,statefulsets -l app.kubernetes.io/part-of=argocd -o json)
  sas=$(k -n "$ARGOCD_NAMESPACE" get serviceaccounts -o json)
  bindings=$(k -n "$ARGOCD_NAMESPACE" get rolebindings -o json)
  missing_sa=$(jq -n --argjson workloads "$workloads" --argjson sas "$sas" '[($workloads.items[].spec.template.spec.serviceAccountName // "default") as $wanted | select([$sas.items[].metadata.name] | index($wanted) | not) | $wanted] | unique | length')
  missing_subject=$(jq -n --argjson bindings "$bindings" --argjson sas "$sas" '[ $bindings.items[].subjects[]? | select(.kind=="ServiceAccount") | .name as $wanted | select([$sas.items[].metadata.name] | index($wanted) | not) | $wanted] | unique | length')
  [[ "$missing_sa" == 0 && "$missing_subject" == 0 ]] || die 'ServiceAccountまたはRoleBinding topologyが閉じていません'
  [[ "$(k -n "$ARGOCD_NAMESPACE" get appproject "$name" -o json | jq -r --arg url "$SOURCE_URL" '.spec.sourceRepos | index($url) != null')" == true ]] || die 'AppProject source allowlistが一致しません'
  [[ "$(k -n "$ARGOCD_NAMESPACE" get appproject "$name" -o json | jq -r '.spec.destinations[] | select(.namespace=="atlas-extended-architecture" and .server=="https://kubernetes.default.svc") | true')" == true ]] || die 'AppProject destination allowlistが一致しません'
  secret_metadata=$(k -n "$ARGOCD_NAMESPACE" get secrets "${name}-repository" "${name}-cluster" -o json | jq '[.items[]|{name:.metadata.name,secret_type:.metadata.labels["argocd.argoproj.io/secret-type"],type}]')
  jq -n --argjson missing_sa "$missing_sa" --argjson missing_subject "$missing_subject" --argjson secrets "$secret_metadata" \
    '{topology:{missing_workload_serviceaccounts:$missing_sa,missing_rolebinding_subjects:$missing_subject,project_allowlists:true,connection_secret_metadata:$secrets,secret_values_captured:false}}' >"$(extended_trace_file architecture)"
  extended_capture architecture
}

phase_cleanup() {
  local name
  name=$(extended_name architecture)
  k -n "$ARGOCD_NAMESPACE" delete appproject "$name" --ignore-not-found >/dev/null
  k -n "$ARGOCD_NAMESPACE" delete secrets "${name}-repository" "${name}-cluster" --ignore-not-found >/dev/null
}
