#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for root Verification Matrix fail-closed compilation."""

from __future__ import annotations

import json

from generate_root_verification_matrix import OUTPUT, compile_matrix, validate


def rejected(name: str, mutate) -> None:
    fixture = json.loads(OUTPUT.read_text(encoding="utf-8"))
    mutate(fixture)
    try:
        validate(fixture)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    document = json.loads(OUTPUT.read_text(encoding="utf-8"))
    validate(document)
    try:
        compile_matrix(document)
    except ValueError:
        pass
    else:
        raise AssertionError("Human Review/Proof gapのままroot Matrix emitが成功しました")
    rejected("class-retreat", lambda value: value["scenario_classes"].pop())
    rejected("core-class-duplicate", lambda value: value["scenario_classes"][2].update(core_scenario="boundary"))
    rejected("legacy-rejection-leaked", lambda value: value["scenario_classes"][2].update(core_scenario="rejection"))
    rejected("candidate-credit-forged", lambda value: value["denominator"].update(legacy_rows_completion_credit=1000))
    rejected("pending-denominator-concealed", lambda value: value["denominator"].update(reviewed_denominator_status="established"))
    rejected("reviewed-behavior-forged", lambda value: value["denominator"].update(reviewed_atomic_behaviors=100))
    rejected("authority-binding-forged", lambda value: value["closure"].update(authority_atomic_bindings=1))
    rejected("completion-eligible-forged", lambda value: value["closure"].update(completion_eligible_rows=1))
    rejected("matrix-present-forged", lambda value: value["root_matrix"].update(present=True))
    rejected("blocker-omission", lambda value: value["root_matrix"]["blockers"].pop())
    rejected("scenario-gap-concealed", lambda value: value["scenario_classes"][0].update(status="closed", gap=None))
    rejected("stale-input-retreat", lambda value: value["dependency_contract"]["tracked_input_paths"].remove("authority/reviews/decisions.json"))
    rejected("stale-rerun-omission", lambda value: value["dependency_contract"].update(required_rerun=""))
    print("Root Verification Matrix fixtures passed: positive=1 negative=14")


if __name__ == "__main__":
    main()
