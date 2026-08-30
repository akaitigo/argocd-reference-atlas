#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Core標準gap Artifactの縮小・偽Runtime credit・partial publishを拒否する。"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import generate_core_standard_artifacts as contract
import validate_core_standard_artifacts as verifier


def rejected(name: str, mutate) -> None:
    bundle = verifier.load_bundle()
    mutate(bundle)
    try:
        verifier.validate_bundle(bundle)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def test_atomic_rollback() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        staging, backup = root / ".next", root / ".previous"
        paths = [Path("one.json"), Path("nested/two.json")]
        originals = {path: f"old:{path}\n".encode() for path in paths}
        replacements = {path: f"new:{path}\n".encode() for path in paths}
        for path, payload in originals.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        contract.write_staging(replacements, staging)
        try:
            contract.publish_staged(root, staging, backup, paths, inject_failure_after=0)
        except RuntimeError:
            pass
        else:
            raise AssertionError("injected partial publish succeeded")
        for path, payload in originals.items():
            if (root / path).read_bytes() != payload:
                raise AssertionError(f"rollback did not retain prior generation: {path}")


def test_staging_rejection_retains_current() -> None:
    current = {
        path: (contract.ROOT / path).read_bytes()
        for path in contract.output_paths()
    }
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory) / ".next"
        documents = contract.build_documents()
        contract.write_staging(documents, staging)
        (staging / contract.MANIFEST).write_text("{}\n", encoding="utf-8")
        try:
            contract.validate_staged(documents, staging)
        except (KeyError, ValueError):
            pass
        else:
            raise AssertionError("invalid staging passed pre-publish verification")
    for path, payload in current.items():
        if (contract.ROOT / path).read_bytes() != payload:
            raise AssertionError(f"failed staging changed current generation: {path}")


def main() -> None:
    verifier.validate_current()
    rejected("mapping-retreat", lambda value: value[contract.MIGRATION]["rows"].pop())
    rejected("new-id-duplicate", lambda value: value[contract.MIGRATION]["rows"][1].update(new_row_id=value[contract.MIGRATION]["rows"][0]["new_row_id"]))
    rejection_index = next(index for index, item in enumerate(verifier.load_bundle()[contract.MIGRATION]["rows"]) if item["legacy_scenario"] == "rejection")
    rejected("legacy-rejection-leak", lambda value: value[contract.MIGRATION]["rows"][rejection_index].update(new_row_id=value[contract.MIGRATION]["rows"][rejection_index]["old_row_id"]))
    rejected("mapping-runtime-credit-forged", lambda value: value[contract.MIGRATION]["rows"][0].update(runtime_credit=True))
    rejected("reference-pass-forged", lambda value: value[contract.REFERENCE_RESULTS].update(status="passed"))
    rejected("fixture-runtime-credit-forged", lambda value: value[contract.REFERENCE_RESULTS]["environment"].update(fixture_runtime_credit=True))
    rejected("historical-runtime-credit-forged", lambda value: value[contract.PATTERN_RESULTS]["environment"].update(historical_evidence_runtime_credit=True))
    rejected("pattern-pass-forged", lambda value: value[contract.PATTERN_RESULTS].update(status="passed"))
    rejected("pattern-static-record-injected", lambda value: value[contract.PATTERN_RESULTS]["tests"].append(copy.deepcopy(value[contract.REFERENCE_RESULTS]["tests"][0])))
    rejected("scenario-class-retreat", lambda value: value[contract.MANIFEST]["scenarios"].pop())
    rejected("baseline-structure-shrink", lambda value: value[contract.BASELINE].update(new_row_count=999))
    rejected("publish-output-retreat", lambda value: value[contract.PUBLISH_MANIFEST]["files"].pop())
    test_staging_rejection_retains_current()
    test_atomic_rollback()
    print("Core standard gap artifact fixtures passed: positive=1 negative=14")


if __name__ == "__main__":
    main()
