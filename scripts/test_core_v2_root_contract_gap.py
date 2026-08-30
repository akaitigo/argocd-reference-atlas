#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Core v2 root契約Gapの縮小・偽credit・早期発行を拒否する。"""

from __future__ import annotations

import copy

from generate_core_v2_root_contract_gap import build, validate


def rejected(name: str, mutate) -> None:
    document = copy.deepcopy(build())
    mutate(document)
    try:
        validate(document)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    validate(build())
    rejected("false-complete", lambda value: value.update(status="complete"))
    rejected("authority-denominator-shrink", lambda value: value["authority"].update(raw_anchors=63888))
    rejected("semantic-credit-forged", lambda value: value["authority"].update(semantic_credit=1))
    rejected("runtime-denominator-shrink", lambda value: value["scenario_denominator"].update(candidate_rows=999))
    rejected("runtime-credit-forged", lambda value: value["credit"].update(runtime=1))
    rejected("fixture-reference-pass", lambda value: value["core_standard_artifacts"]["reference_results"].update(status="passed"))
    rejected("static-pattern-credit", lambda value: value["core_standard_artifacts"]["pattern_results"]["counts"].update(rows=1))
    rejected("root-surface-early-emit", lambda value: value["root_adapters"]["surface_inventory"].update(present=True, emission_eligible=True))
    rejected("root-matrix-early-emit", lambda value: value["root_adapters"]["verification_matrix"].update(present=True, emission_eligible=True))
    rejected("refusal-mapping-retreat", lambda value: value["scenario_migration"]["mapping"].update(rejection="rejection"))
    rejected("mapping-row-retreat", lambda value: value["scenario_migration"]["counts"].update(new_rows=999))
    rejected("core-class-duplicate", lambda value: value["root_adapters"]["verification_matrix"]["scenario_classes"][2].update(core="boundary"))
    rejected("blocker-retreat", lambda value: value["blockers"].pop())
    print("Core v2 root contract gap fixtures passed: positive=1 negative=13")


if __name__ == "__main__":
    main()
