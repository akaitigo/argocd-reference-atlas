#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
labs=(application reconciliation sync diff health promotion security failure recovery)

find "${root}/scripts" -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
for lab in "${labs[@]}"; do
  test -f "${root}/labs/${lab}/lab.yaml"
  grep -Fq "id: ${lab}" "${root}/labs/${lab}/lab.yaml"
  for phase in setup execute verify cleanup; do
    "${root}/scripts/run-lab.sh" "$lab" "$phase" --dry-run >/dev/null
  done
done

grep -Eq '^install_sha256=[a-f0-9]{64}$' "${root}/environments/kind/argocd-v3.5.2.lock"
grep -Eq '^version_sha256=[a-f0-9]{64}$' "${root}/environments/kind/argocd-v3.5.2.lock"
grep -Eq '^kind_node_image=.*@sha256:[a-f0-9]{64}$' "${root}/environments/kind/argocd-v3.5.2.lock"
grep -Eq '^source_server_image=.*@sha256:[a-f0-9]{64}$' "${root}/environments/kind/argocd-v3.5.2.lock"
kind_node_image=$(sed -n 's/^kind_node_image=//p' "${root}/environments/kind/argocd-v3.5.2.lock")
source_server_image=$(sed -n 's/^source_server_image=//p' "${root}/environments/kind/argocd-v3.5.2.lock")
grep -Fq "image: ${kind_node_image}" "${root}/environments/kind/kind-config.yaml.tmpl"
grep -Fq "image: ${source_server_image}" "${root}/environments/kind/source-server.yaml"
grep -Fq "$source_server_image" "${root}/scripts/build-local-source.sh"
status=$(sed -n 's/^status: //p' "${root}/atlas.yaml")
if [[ "$status" == complete ]]; then
  test -f "${root}/evidence/completion-certificate.json"
else
  test ! -e "${root}/evidence/completion-certificate.json"
fi
if grep -R -n -E 'placeholder|TODO' "${root}/labs" "${root}/evidence" 2>/dev/null; then
  printf 'LabまたはEvidenceにplaceholder表現があります\n' >&2
  exit 1
fi
printf 'Lab static checks: pass\n'
