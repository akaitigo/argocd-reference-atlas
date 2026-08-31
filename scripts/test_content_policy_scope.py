#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Content policyのtracked Subject境界を固定するfixture。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from validate_non_regression import validate_content_policy


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def rejected(name: str, root: Path, paths: list[Path]) -> None:
    try:
        validate_content_policy(root, paths)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="argocd-content-policy-") as value:
        root = Path(value)
        subject = write(root, "docs/subject.md", "再現可能なEvidenceを示す。\n")
        dependency = write(root, ".atlas-core/AGENTS.md", "決定" + "版\n")
        untracked = write(root, "checkout/dependency.md", "世界" + "一\n")
        validate_content_policy(root, [subject])
        validate_content_policy(root, [subject, dependency])
        rejected("tracked-subject-propaganda", root, [write(root, "docs/bad.md", "決定" + "版\n")])
        rejected("tracked-subject-author-praise", root, [write(root, "README.md", "作者を" + "称賛\n")])
        rejected("tracked-subject-namespace-praise", root, [write(root, "policy.yaml", "note: akaitigo" + "氏\n")])
        if not untracked.is_file():
            raise AssertionError("untracked dependency fixture was not created")
    print("Content policy scope fixtures passed: positive=2 negative=3")


if __name__ == "__main__":
    main()
