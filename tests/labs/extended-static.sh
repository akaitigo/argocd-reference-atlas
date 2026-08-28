#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
labs=(architecture applicationset connection hook-wave access-boundary high-availability observability drift auto-recovery upgrade-migration operations notifications)

find "${root}/scripts/extended" -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
for lab in "${labs[@]}"; do
  spec="${root}/labs/${lab}/lab.yaml"
  test -f "$spec"
  grep -Fq "id: lab.${lab}" "$spec"
  grep -Eq '^target_id: [a-z0-9.-]+$' "$spec"
  grep -Eq '^claim_id: claim\.[a-z0-9.-]+$' "$spec"
  grep -Fq "evidence_id: evidence.${lab}.v3-5-2" "$spec"
  for phase in setup execute verify cleanup; do
    "${root}/scripts/extended/run.sh" "$lab" "$phase" --dry-run >/dev/null
  done
done

grep -Eq '^install_sha256=[a-f0-9]{64}$' "${root}/environments/kind/argocd-v3.4.8.lock"
grep -Eq '^install_sha256=[a-f0-9]{64}$' "${root}/environments/kind/argocd-v3.5.2-ha.lock"
if grep -R -n -E 'password: [^$]|bearerToken":"[A-Za-z0-9_-]{20,}' "${root}/labs" "${root}/scripts/extended" 2>/dev/null; then
  printf '固定Credentialらしき値を検出しました\n' >&2
  exit 1
fi
status=$(sed -n 's/^status: //p' "${root}/atlas.yaml")
if [[ "$status" == complete ]]; then
  test -f "${root}/evidence/completion-certificate.json"
else
  test ! -e "${root}/evidence/completion-certificate.json"
fi
printf 'Extended Lab static checks: pass\n'
