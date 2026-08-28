#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""原子的Evidence公開の成功、保持、混在拒否、rollbackを失敗注入で検証する。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from lib.atomic_evidence_publish import (
    AtomicEvidencePublishError,
    FullRunNotPassed,
    publish_evidence_tree,
    validate_publish_manifest,
    write_publish_manifest,
)


REFERENCE = "7175de4305afb308722d5b83475e91c18da64957"
MANIFEST = Path("reports/atomic-publish-manifest.json")
EXPECTED = [Path("reports/index.json"), Path("reports/rows/one.json")]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def seed_previous(output: Path) -> None:
    (output / "reports/rows").mkdir(parents=True)
    (output / "reports/index.json").write_text('{"generation":"previous"}\n', encoding="utf-8")
    (output / "reports/rows/one.json").write_text('{"generation":"previous"}\n', encoding="utf-8")
    write_publish_manifest(output, MANIFEST, EXPECTED, reporter_id="test-reporter", reference_commit=REFERENCE)


def write_next(staging: Path) -> None:
    (staging / "reports/rows").mkdir(parents=True, exist_ok=True)
    (staging / "reports/index.json").write_text('{"generation":"next"}\n', encoding="utf-8")
    (staging / "reports/rows/one.json").write_text('{"generation":"next"}\n', encoding="utf-8")
    write_publish_manifest(staging, MANIFEST, EXPECTED, reporter_id="test-reporter", reference_commit=REFERENCE)


def validate(staging: Path) -> None:
    validate_publish_manifest(staging, MANIFEST, EXPECTED)


def snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def paths(parent: Path) -> tuple[Path, Path, Path]:
    return parent / "evidence", parent / ".evidence-next", parent / ".evidence-previous"


def test_success() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output, staging, backup = paths(Path(directory))
        seed_previous(output)
        publish_evidence_tree(output, staging, backup, write_next, validate, full_run_passed=True)
        require(b'"next"' in (output / "reports/index.json").read_bytes(), "pass runが公開されません")
        require(not staging.exists() and not backup.exists(), "成功後にstagingまたはbackupが残りました")


def test_failed_run_retains_previous() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output, staging, backup = paths(Path(directory))
        seed_previous(output)
        previous = snapshot(output)
        failed = False
        try:
            publish_evidence_tree(output, staging, backup, write_next, validate, full_run_passed=False)
        except FullRunNotPassed:
            failed = True
        require(failed, "失敗runが公開処理を通過しました")
        require(snapshot(output) == previous, "失敗runが直前成功Evidenceを変更しました")
        require(not staging.exists() and not backup.exists(), "失敗runのstagingが残りました")


def test_partial_overwrite_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output, staging, backup = paths(Path(directory))
        seed_previous(output)
        previous = snapshot(output)

        def partial(candidate: Path) -> None:
            (candidate / "reports/index.json").write_text('{"generation":"partial"}\n', encoding="utf-8")
            write_publish_manifest(candidate, MANIFEST, [EXPECTED[0]], reporter_id="test-reporter", reference_commit=REFERENCE)

        failed = False
        try:
            publish_evidence_tree(output, staging, backup, partial, validate, full_run_passed=True)
        except AtomicEvidencePublishError:
            failed = True
        require(failed, "部分上書きを受理しました")
        require(snapshot(output) == previous, "部分上書きが直前成功Evidenceを変更しました")


def test_mixed_generation_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output, staging, backup = paths(Path(directory))
        seed_previous(output)
        previous = snapshot(output)

        def mixed(candidate: Path) -> None:
            write_next(candidate)
            (candidate / "reports/rows/one.json").write_text('{"generation":"previous"}\n', encoding="utf-8")

        failed = False
        try:
            publish_evidence_tree(output, staging, backup, mixed, validate, full_run_passed=True)
        except AtomicEvidencePublishError:
            failed = True
        require(failed, "新旧generation混在を受理しました")
        require(snapshot(output) == previous, "混在runが直前成功Evidenceを変更しました")


def test_swap_failure_rolls_back() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output, staging, backup = paths(Path(directory))
        seed_previous(output)
        previous = snapshot(output)
        calls = 0

        def fail_second_rename(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected staging swap failure")
            os.rename(source, destination)

        failed = False
        try:
            publish_evidence_tree(
                output,
                staging,
                backup,
                write_next,
                validate,
                full_run_passed=True,
                rename=fail_second_rename,
            )
        except AtomicEvidencePublishError:
            failed = True
        require(failed and calls == 3, "swap失敗時にrollback renameが実行されません")
        require(snapshot(output) == previous, "swap失敗後に直前成功Evidenceへ戻りません")
        require(not staging.exists() and not backup.exists(), "rollback後にstagingまたはbackupが残りました")


def main() -> None:
    tests = [
        test_success,
        test_failed_run_retains_previous,
        test_partial_overwrite_rejected,
        test_mixed_generation_rejected,
        test_swap_failure_rolls_back,
    ]
    for test in tests:
        test()
    print(f"Atomic Evidence publish contract tests passed: positive=1 negative={len(tests) - 1}")


if __name__ == "__main__":
    main()
