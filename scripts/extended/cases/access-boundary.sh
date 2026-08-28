#!/usr/bin/env bash

phase_setup() {
  extended_init access-boundary
  local backup_dir issuer client_secret
  backup_dir="${EXTENDED_RUNTIME}/backup/access-boundary"
  mkdir -p "$backup_dir"
  issuer="http://oidc-provider.atlas-extended-access-boundary.svc.cluster.local"
  k -n "$ARGOCD_NAMESPACE" get configmap argocd-rbac-cm -o json >"${backup_dir}/argocd-rbac-cm.json"
  k -n "$ARGOCD_NAMESPACE" get configmap argocd-cm -o json >"${backup_dir}/argocd-cm.json"
  if k -n "$ARGOCD_NAMESPACE" get secret argocd-secret -o jsonpath='{.data.oidc\.clientSecret}' | grep -q .; then
    die '既存oidc.clientSecretがあるため上書きを拒否しました'
  fi
  client_secret=$(printf '%s' "${CLUSTER_NAME}-oidc-$(date -u '+%s')-$$" | shasum -a 256 | awk '{print $1}')
  k -n "$ARGOCD_NAMESPACE" patch secret argocd-secret --type merge -p "{\"stringData\":{\"oidc.clientSecret\":\"${client_secret}\"}}" >/dev/null
  printf 'created\n' >"${EXTENDED_RUNTIME}/access-boundary-secret-created"
  k -n "$ARGOCD_NAMESPACE" patch configmap argocd-rbac-cm --type merge -p \
    '{"data":{"policy.csv":"p, role:atlas-auditor, applications, get, atlas-extended-*/*, allow\np, role:atlas-auditor, applications, get, outside-project/*, deny\np, role:atlas-auditor, applications, delete, *, deny\np, role:atlas-auditor, repositories, get, *, deny\np, role:atlas-auditor, clusters, get, *, deny\ng, atlas-oidc-user, role:atlas-auditor","policy.default":"role:atlas-empty","scopes":"[groups, email]"}}' >/dev/null
  k -n "$ARGOCD_NAMESPACE" patch configmap argocd-cm --type merge -p \
    "{\"data\":{\"oidc.config\":\"name: Atlas Local OIDC\\nissuer: ${issuer}\\nclientID: atlas-client\\nclientSecret: \$oidc.clientSecret\\nrequestedScopes: [openid, profile, email, groups]\"}}" >/dev/null
  cat <<EOF | k apply -f - >/dev/null
apiVersion: v1
kind: Namespace
metadata:
  name: atlas-extended-access-boundary
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: oidc-static
  namespace: atlas-extended-access-boundary
data:
  discovery.json: '{"issuer":"${issuer}","authorization_endpoint":"${issuer}/authorize","token_endpoint":"${issuer}/token","jwks_uri":"${issuer}/jwks.json","response_types_supported":["code"],"subject_types_supported":["public"],"id_token_signing_alg_values_supported":["RS256"]}'
  jwks.json: '{"keys":[]}'
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oidc-provider
  namespace: atlas-extended-access-boundary
spec:
  replicas: 1
  selector:
    matchLabels: {app: oidc-provider}
  template:
    metadata:
      labels: {app: oidc-provider}
    spec:
      automountServiceAccountToken: false
      containers:
        - name: http
          image: ${SUPPORT_IMAGE}
          args: ["python", "-m", "http.server", "8080", "--directory", "/srv"]
          volumeMounts:
            - name: static
              mountPath: /srv
              readOnly: true
      volumes:
        - name: static
          configMap:
            name: oidc-static
            items:
              - key: discovery.json
                path: .well-known/openid-configuration
              - key: jwks.json
                path: jwks.json
---
apiVersion: v1
kind: Service
metadata:
  name: oidc-provider
  namespace: atlas-extended-access-boundary
spec:
  selector: {app: oidc-provider}
  ports:
    - port: 80
      targetPort: 8080
EOF
  k -n atlas-extended-access-boundary rollout status deployment/oidc-provider --timeout=180s
  k -n "$ARGOCD_NAMESPACE" rollout restart deployment/argocd-server >/dev/null
  k -n "$ARGOCD_NAMESPACE" rollout status deployment/argocd-server --timeout=240s
}

phase_execute() {
  local namespace issuer endpoints provider_pods elapsed=0
  namespace=atlas-extended-access-boundary
  issuer="http://oidc-provider.${namespace}.svc.cluster.local"
  k -n "$namespace" delete pod oidc-discovery-ok oidc-discovery-fail --ignore-not-found >/dev/null
  k -n "$namespace" run oidc-discovery-ok --image="$SUPPORT_IMAGE" --restart=Never --command -- \
    python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('${issuer}/.well-known/openid-configuration', timeout=10)); assert d['issuer']=='${issuer}'" >/dev/null
  extended_wait_jsonpath "$namespace" pod/oidc-discovery-ok '{.status.phase}' Succeeded 120
  k -n "$namespace" scale deployment oidc-provider --replicas=0 >/dev/null
  k -n "$namespace" rollout status deployment/oidc-provider --timeout=120s
  while (( elapsed < 60 )); do
    endpoints=$(k -n "$namespace" get endpoints oidc-provider -o jsonpath='{.subsets}' 2>/dev/null || true)
    provider_pods=$(k -n "$namespace" get pods -l app=oidc-provider --no-headers 2>/dev/null | wc -l | tr -d ' ')
    [[ -z "$endpoints" && "$provider_pods" == 0 ]] && break
    sleep 2
    elapsed=$((elapsed + 2))
  done
  [[ -z "$endpoints" && "$provider_pods" == 0 ]] || die 'OIDC provider endpointまたはPodが消失しません'
  k -n "$namespace" run oidc-discovery-fail --image="$SUPPORT_IMAGE" --restart=Never --command -- \
    python -c "import urllib.request; urllib.request.urlopen('${issuer}/.well-known/openid-configuration', timeout=5)" >/dev/null
  extended_wait_jsonpath "$namespace" pod/oidc-discovery-fail '{.status.phase}' Failed 120
}

phase_verify() {
  local namespace allow outside_deny deny credential_deny issuer
  namespace=atlas-extended-access-boundary
  issuer="http://oidc-provider.${namespace}.svc.cluster.local"
  k -n "$namespace" scale deployment oidc-provider --replicas=1 >/dev/null
  k -n "$namespace" rollout status deployment/oidc-provider --timeout=180s
  allow=$(k -n "$ARGOCD_NAMESPACE" exec deployment/argocd-server -- argocd admin settings rbac can atlas-oidc-user get applications 'atlas-extended-*/*' --namespace "$ARGOCD_NAMESPACE")
  outside_deny=$(k -n "$ARGOCD_NAMESPACE" exec deployment/argocd-server -- argocd admin settings rbac can atlas-oidc-user get applications 'outside-project/*' --namespace "$ARGOCD_NAMESPACE" || true)
  deny=$(k -n "$ARGOCD_NAMESPACE" exec deployment/argocd-server -- argocd admin settings rbac can atlas-oidc-user delete applications '*' --namespace "$ARGOCD_NAMESPACE" || true)
  credential_deny=$(k -n "$ARGOCD_NAMESPACE" exec deployment/argocd-server -- argocd admin settings rbac can atlas-oidc-user get repositories '*' --namespace "$ARGOCD_NAMESPACE" || true)
  [[ "$allow" == *Yes* && "$outside_deny" == *No* && "$deny" == *No* && "$credential_deny" == *No* ]] || die "RBAC判定が不一致です: allow=${allow}, outside=${outside_deny}, deny=${deny}, credential=${credential_deny}"
  jq -n --arg issuer "$issuer" --arg allow "$allow" --arg outside_deny "$outside_deny" --arg deny "$deny" --arg credential_deny "$credential_deny" \
    '{access_boundary:{target_project_read:$allow,outside_project_read:$outside_deny,delete_operation:$deny,credential_access:$credential_deny,oidc_subject:"atlas-oidc-user",oidc_issuer:$issuer,discovery_success:true,provider_outage_rejected:true,argocd_server_survived:true,client_secret_captured:false,interactive_login:"not-attempted"}}' \
    >"$(extended_trace_file access-boundary)"
  extended_capture access-boundary
}

phase_cleanup() {
  local backup_dir rbac_data cm_data
  backup_dir="${EXTENDED_RUNTIME}/backup/access-boundary"
  k -n atlas-extended-access-boundary scale deployment oidc-provider --replicas=1 >/dev/null 2>&1 || true
  k delete namespace atlas-extended-access-boundary --ignore-not-found --wait=true >/dev/null
  if [[ -s "${backup_dir}/argocd-rbac-cm.json" ]]; then
    rbac_data=$(jq -c '.data // {}' "${backup_dir}/argocd-rbac-cm.json")
    k -n "$ARGOCD_NAMESPACE" patch configmap argocd-rbac-cm --type json -p "[{\"op\":\"replace\",\"path\":\"/data\",\"value\":${rbac_data}}]" >/dev/null
  fi
  if [[ -s "${backup_dir}/argocd-cm.json" ]]; then
    cm_data=$(jq -c '.data // {}' "${backup_dir}/argocd-cm.json")
    k -n "$ARGOCD_NAMESPACE" patch configmap argocd-cm --type json -p "[{\"op\":\"replace\",\"path\":\"/data\",\"value\":${cm_data}}]" >/dev/null
  fi
  if [[ -f "${EXTENDED_RUNTIME}/access-boundary-secret-created" ]] && k -n "$ARGOCD_NAMESPACE" get secret argocd-secret -o jsonpath='{.data.oidc\.clientSecret}' | grep -q .; then
    k -n "$ARGOCD_NAMESPACE" patch secret argocd-secret --type json -p '[{"op":"remove","path":"/data/oidc.clientSecret"}]' >/dev/null
  fi
  k -n "$ARGOCD_NAMESPACE" rollout restart deployment/argocd-server >/dev/null
  k -n "$ARGOCD_NAMESPACE" rollout status deployment/argocd-server --timeout=240s
  rm -f -- "${EXTENDED_RUNTIME}/access-boundary-secret-created" "${backup_dir}/argocd-rbac-cm.json" "${backup_dir}/argocd-cm.json"
  rmdir "$backup_dir" 2>/dev/null || true
}
