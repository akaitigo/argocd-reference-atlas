#!/bin/sh
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0

set -eu

base_revision=${1:-}
head_revision=${2:-HEAD}

if [ -z "$base_revision" ]; then
  echo "エラー: 使い方: scripts/validate_dco.sh <base-revision> [head-revision]" >&2
  exit 2
fi

commits=$(git rev-list "$base_revision..$head_revision")
if [ -z "$commits" ]; then
  echo "検証済み: 対象Commitはありません"
  exit 0
fi

failed=0
for commit in $commits; do
  if ! git show -s --format=%B "$commit" | grep -Eq '^Signed-off-by: .+ <[^<>[:space:]]+@[^<>[:space:]]+>$'; then
    echo "エラー: $commit に有効なSigned-off-by行がありません" >&2
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  exit 1
fi

echo "検証済み: DCO Sign-off"
