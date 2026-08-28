#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/common.sh"

lab=${1:-}
phase=${2:-}
dry_run=${3:-}
case "$lab" in architecture|applicationset|connection|hook-wave|access-boundary|high-availability|observability|drift|auto-recovery|upgrade-migration|operations) ;;
  *) die "未知のextended Labです: ${lab}" ;;
esac
case "$phase" in setup|execute|verify|cleanup) ;; *) die 'usage: scripts/extended/run.sh LAB {setup|execute|verify|cleanup} [--dry-run]' ;; esac
case_file="${ATLAS_ROOT}/scripts/extended/cases/${lab}.sh"
[[ -f "$case_file" ]] || die "case implementationがありません: ${case_file}"
if [[ "$dry_run" == --dry-run ]]; then
  printf 'lab_id=%s evidence_id=%s phase=%s context=%s\n' "$(extended_lab_id "$lab")" "$(extended_evidence_id "$lab")" "$phase" "$EXPECTED_CONTEXT"
  exit 0
fi
require_commands kind kubectl jq git shasum curl
if [[ "$lab" != high-availability && "$lab" != upgrade-migration ]]; then
  assert_dedicated_context
fi
# shellcheck disable=SC1090
. "$case_file"
"phase_${phase}"
