#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/common.sh"

lab=${1:?Lab IDが必要です}
cleanup_on_exit() { "${ATLAS_ROOT}/scripts/extended/run.sh" "$lab" cleanup || true; }
trap cleanup_on_exit EXIT
"${ATLAS_ROOT}/scripts/extended/run.sh" "$lab" setup
"${ATLAS_ROOT}/scripts/extended/run.sh" "$lab" execute
"${ATLAS_ROOT}/scripts/extended/run.sh" "$lab" verify
python3 "${ATLAS_ROOT}/scripts/evidence/record_extended.py" "$lab"
trap - EXIT
cleanup_on_exit
