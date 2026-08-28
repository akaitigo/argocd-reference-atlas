#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/../lib/lab-common.sh"

lab=${1:?Lab IDが必要です}
artifact=${2:?raw artifact pathが必要です}
revision=${3:-main}
[[ -s "$artifact" ]] || die "raw artifactが空です: ${artifact}"

case "$lab" in
  application) evidence_id=evidence.application.v3-5-2; claim_id=claim.application.desired-state; kind=conformance ;;
  reconciliation) evidence_id=evidence.reconciliation.v3-5-2; claim_id=claim.reconciliation.convergence; kind=conformance ;;
  sync) evidence_id=evidence.sync.v3-5-2; claim_id=claim.sync.deterministic-order; kind=test-report ;;
  diff) evidence_id=evidence.diff.v3-5-2; claim_id=claim.diff.detect-drift; kind=test-report ;;
  health) evidence_id=evidence.health.v3-5-2; claim_id=claim.health.aggregate-status; kind=test-report ;;
  promotion) evidence_id=evidence.promotion.v3-5-2; claim_id=claim.promotion.git-boundary; kind=migration ;;
  security) evidence_id=evidence.security.v3-5-2; claim_id=claim.security.no-secret-leak; kind=attack ;;
  failure) evidence_id=evidence.failure.v3-5-2; claim_id=claim.failure.safe-degradation; kind=attack ;;
  recovery) evidence_id=evidence.recovery.v3-5-2; claim_id=claim.recovery.restore-state; kind=recovery ;;
  *) die "未知のLab IDです: ${lab}" ;;
esac

require_commands git shasum wc
bare="${RUNTIME_DIR}/source/repo.git"
git --git-dir="$bare" rev-parse --verify "refs/heads/${revision}" >/dev/null
source_sha=$(git --git-dir="$bare" archive "$revision" | shasum -a 256 | awk '{print $1}')
harness_sha=$(
  cd "$ATLAS_ROOT"
  {
    find "labs/${lab}" scripts/evidence scripts/lib -type f -print0
    printf '%s\0' scripts/build-local-source.sh scripts/environment.sh scripts/run-lab.sh scripts/run-suite.sh
  } |
    LC_ALL=C sort -z |
    xargs -0 shasum -a 256 |
    shasum -a 256 |
    awk '{print $1}'
)
environment_sha=$(
  cd "$ATLAS_ROOT"
  find environments/kind .runtime/downloads -type f -print0 |
    LC_ALL=C sort -z |
    xargs -0 shasum -a 256 |
    shasum -a 256 |
    awk '{print $1}'
)
artifact_sha=$(sha256_file "$artifact")
artifact_size=$(wc -c <"$artifact" | tr -d ' ')
artifact_uri=${artifact#"${ATLAS_ROOT}/"}
created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
record="${ATLAS_ROOT}/evidence/records/${evidence_id}.evidence.yaml"
mkdir -p "$(dirname -- "$record")"

cat >"$record" <<EOF
schema_version: 1
id: ${evidence_id}
atlas_id: ${ATLAS_ID}
claim_ids: [${claim_id}]
kind: ${kind}
producer: argocd-atlas-kind-harness
command: make lab-${lab}
created_at: "${created_at}"
environment:
  profile: cluster
  manifest_digest: sha256:${environment_sha}
  cluster_name: ${CLUSTER_NAME}
  kubernetes_context: ${EXPECTED_CONTEXT}
  argocd_version: v3.5.2
source_digest: sha256:${source_sha}
harness_digest: sha256:${harness_sha}
artifact:
  uri: ${artifact_uri}
  digest: sha256:${artifact_sha}
  media_type: application/json
  size_bytes: ${artifact_size}
verdict: pass
retention: git
EOF
info "Core evidence recordを生成しました: ${record}"
