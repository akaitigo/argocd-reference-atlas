#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/../lib/lab-common.sh"

lab=${1:?Lab IDが必要です}
revision=${2:-main}
require_commands jq kubectl kind
assert_dedicated_context
app=$(lab_app "$lab")
namespace=$(lab_namespace "$lab")
raw_dir="${ATLAS_ROOT}/evidence/raw/evidence.${lab}.v3-5-2"
artifact="${raw_dir}/result.json"
tmp_dir="${RUNTIME_DIR}/capture-${lab}"
assert_runtime_path "$tmp_dir"
mkdir -p "$raw_dir" "$tmp_dir"

k -n "$ARGOCD_NAMESPACE" get application "$app" -o json >"${tmp_dir}/application.json"
k -n "$namespace" get all,configmaps -o json >"${tmp_dir}/resources.json"
k -n "$ARGOCD_NAMESPACE" get statefulset argocd-application-controller -o json >"${tmp_dir}/controller.json"
k -n argocd-atlas-source get pod -l app=source-server -o json >"${tmp_dir}/source-server.json"
k get nodes -o json >"${tmp_dir}/nodes.json"
kind version >"${tmp_dir}/kind-version.txt"
kubectl version --client -o json >"${tmp_dir}/kubectl-version.json"
k -n "$namespace" get secrets -o json |
  jq '{apiVersion,kind,items:[.items[]|{metadata:{name:.metadata.name,namespace:.metadata.namespace},type}]}' >"${tmp_dir}/secret-metadata.json"
trace_file="${RUNTIME_DIR}/traces/${lab}.json"
[[ -s "$trace_file" ]] || printf '{}\n' >"$trace_file"

jq -n \
  --arg atlas_id "$ATLAS_ID" \
  --arg lab "$lab" \
  --arg context "$EXPECTED_CONTEXT" \
  --arg revision "$revision" \
  --slurpfile application "${tmp_dir}/application.json" \
  --slurpfile resources "${tmp_dir}/resources.json" \
  --slurpfile controller "${tmp_dir}/controller.json" \
  --slurpfile source_server "${tmp_dir}/source-server.json" \
  --slurpfile nodes "${tmp_dir}/nodes.json" \
  --rawfile kind_version "${tmp_dir}/kind-version.txt" \
  --slurpfile kubectl_version "${tmp_dir}/kubectl-version.json" \
  --slurpfile secret_metadata "${tmp_dir}/secret-metadata.json" \
  --slurpfile trace "$trace_file" \
  '{schema_version:1,atlas_id:$atlas_id,lab:$lab,context:$context,source_revision:$revision,trace:$trace[0],application:$application[0],resources:$resources[0],controller:$controller[0],source_server:$source_server[0],nodes:$nodes[0],toolchain:{kind:$kind_version,kubectl:$kubectl_version[0]},destination_secret_metadata:$secret_metadata[0]}' \
  >"$artifact"

"${ATLAS_ROOT}/scripts/evidence/record.sh" "$lab" "$artifact" "$revision"
