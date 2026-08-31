#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Scenario Proof Schema adapterの縮小・偽credit・早期公開を拒否する。"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import generate_core_v2_scenario_schema_gap as contract


def rejected(name: str, mutate) -> None:
    report = copy.deepcopy(json.loads(contract.OUTPUT.read_text(encoding="utf-8")))
    mutate(report)
    try:
        contract.validate_report(report)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def test_corrupt_staging_rejected() -> None:
    documents = contract.build_documents()
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory) / ".next"
        contract.write_staging(documents, staging)
        first = next(path for path in documents if path.name.endswith(".proof.json"))
        (staging / first).write_text("{}\n", encoding="utf-8")
        try:
            contract.validate_staging(documents, staging)
        except ValueError:
            return
    raise AssertionError("corrupt Scenario Schema staging was accepted")


def test_atomic_report_retains_current() -> None:
    report = json.loads(contract.OUTPUT.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "report.json"
        original = b'{"prior":"success"}\n'
        target.write_bytes(original)
        try:
            contract.publish_report(report, target, inject_failure=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError("injected report publish failure succeeded")
        if target.read_bytes() != original:
            raise AssertionError("failed report publish changed prior report")


def main() -> None:
    report = json.loads(contract.OUTPUT.read_text(encoding="utf-8"))
    contract.validate_report(report)
    rejected("false-complete", lambda value: value.update(status="complete"))
    rejected("schema-row-shrink", lambda value: value["schema_validation"].update(row_files=999))
    rejected("denominator-shrink", lambda value: value["denominator"].update(rows=999))
    rejected("runtime-credit-forged", lambda value: value["credit"].update(runtime=1))
    rejected("semantic-credit-forged", lambda value: value["credit"].update(semantic=1))
    rejected("completion-credit-forged", lambda value: value["credit"].update(completion=1))
    rejected("canonical-early-publish", lambda value: value["canonical_publication"].update(emitted=True))
    rejected("legacy-index-not-preserved", lambda value: value["canonical_publication"].update(legacy_index_preserved=False))
    rejected("refusal-mapping-retreat", lambda value: value["scenario_classes"].__setitem__(2, "rejection"))
    rejected("mapping-count-retreat", lambda value: value["row_identity"]["mapping_counts"].update(new_rows=999))
    rejected("remaining-gap-hidden", lambda value: value["remaining_gaps"].update(remaining_runtime_rows=0))
    test_corrupt_staging_rejected()
    test_atomic_report_retains_current()
    print("Core v2 Scenario Schema gap fixtures passed: positive=1 negative=13")


if __name__ == "__main__":
    main()
