#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/lib/lab-common.sh"

lab=${1:?Lab IDが必要です}
case "$lab" in application|reconciliation|sync|diff|health|promotion|security|failure|recovery) ;; *) die "未知のLab IDです: ${lab}" ;; esac

cleanup_on_exit() {
  "${ATLAS_ROOT}/scripts/run-lab.sh" "$lab" cleanup || true
}
trap cleanup_on_exit EXIT
"${ATLAS_ROOT}/scripts/run-lab.sh" "$lab" setup
"${ATLAS_ROOT}/scripts/run-lab.sh" "$lab" execute
"${ATLAS_ROOT}/scripts/run-lab.sh" "$lab" verify
trap - EXIT
cleanup_on_exit
