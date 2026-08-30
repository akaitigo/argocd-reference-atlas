#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/lib/lab-common.sh"

require_commands git
work="${RUNTIME_DIR}/source-work"
bare="${RUNTIME_DIR}/source/repo.git"
assert_runtime_path "$work"
assert_runtime_path "$bare"
mkdir -p "$RUNTIME_DIR" "${RUNTIME_DIR}/source"
rm -rf -- "$work" "$bare"
mkdir -p "$work"

git -C "$work" init -q -b main
git -C "$work" config user.name 'Argo CD Atlas'
git -C "$work" config user.email 'atlas@example.invalid'
export GIT_AUTHOR_DATE='2026-08-28T00:00:00Z'
export GIT_COMMITTER_DATE="$GIT_AUTHOR_DATE"

write_configmap() {
  local path=$1 name=$2 key=$3 value=$4
  mkdir -p "${work}/${path}"
  cat >"${work}/${path}/configmap.yaml" <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: ${name}
data:
  ${key}: ${value}
EOF
}

for lab in failure recovery security; do
  write_configmap "apps/${lab}" "atlas-${lab}" release v1
done
mkdir -p "${work}/apps/application"
cp "${ATLAS_ROOT}/fixtures/scenarios/application-sync-policy-normal/configmap.yaml" \
  "${work}/apps/application/configmap.yaml"
write_configmap apps/reconciliation atlas-reconciliation desired canonical
write_configmap apps/sync atlas-sync release v1
write_configmap apps/diff atlas-diff desired git
write_configmap apps/promotion atlas-promotion release stable
mkdir -p "${work}/apps/health"
cat >"${work}/apps/health/deployment.yaml" <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atlas-health
spec:
  replicas: 1
  progressDeadlineSeconds: 10
  selector:
    matchLabels: {app: atlas-health}
  template:
    metadata:
      labels: {app: atlas-health}
    spec:
      containers:
        - name: workload
          image: python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc
          args: ["python", "-m", "http.server", "8080"]
EOF

git -C "$work" add apps
git -C "$work" commit -q -m 'baseline desired state'

git -C "$work" switch -q -c sync-failure
mkdir -p "${work}/apps/sync"
cat >"${work}/apps/sync/wave-minus-one.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlas-sync-before
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
data:
  phase: before
EOF
cat >"${work}/apps/sync/wave-zero-failure.yaml" <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: atlas-sync-failure
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 10
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: unavailable
          image: registry.invalid/atlas/does-not-exist:0
EOF
cat >"${work}/apps/sync/wave-one.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlas-sync-after
  annotations:
    argocd.argoproj.io/sync-wave: "1"
data:
  phase: after
EOF
git -C "$work" add apps/sync
git -C "$work" commit -q -m 'stop later sync wave after failure'

git -C "$work" switch -q main
git -C "$work" switch -q -c hook-wave
mkdir -p "${work}/apps/hook-wave"
cat >"${work}/apps/hook-wave/presync.yaml" <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: atlas-hook-presync
  annotations:
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: hook
          image: python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc
          command: ["python", "-c", "print('presync')"]
EOF
cat >"${work}/apps/hook-wave/wave-minus-one.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlas-hook-wave-minus-one
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
data: {wave: minus-one}
EOF
cat >"${work}/apps/hook-wave/wave-one.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlas-hook-wave-one
  annotations:
    argocd.argoproj.io/sync-wave: "1"
data: {wave: one}
EOF
cat >"${work}/apps/hook-wave/postsync.yaml" <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: atlas-hook-postsync
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: hook
          image: python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc
          command: ["python", "-c", "print('postsync')"]
EOF
git -C "$work" add apps/hook-wave
git -C "$work" commit -q -m 'exercise hook phases and sync waves'

git -C "$work" switch -q main
git -C "$work" switch -q -c promotion-candidate
write_configmap apps/promotion atlas-promotion release candidate
git -C "$work" add apps/promotion/configmap.yaml
git -C "$work" commit -q -m 'promote candidate through git revision'

git -C "$work" switch -q main
git -C "$work" switch -q -c health-bad
sed -i.bak 's#python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc#registry.invalid/atlas/does-not-exist:0#' "${work}/apps/health/deployment.yaml"
rm -- "${work}/apps/health/deployment.yaml.bak"
git -C "$work" add apps/health/deployment.yaml
git -C "$work" commit -q -m 'inject unavailable workload image'

git -C "$work" switch -q main
git clone -q --bare "$work" "$bare"
git --git-dir="$bare" symbolic-ref HEAD refs/heads/main
git --git-dir="$bare" update-server-info
find "$bare" -type d -exec chmod 0755 {} +
find "$bare" -type f -exec chmod 0644 {} +
info "local Git sourceを生成しました: ${bare}"
