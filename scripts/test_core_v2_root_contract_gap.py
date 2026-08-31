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
    rejected("core-pin-substitution", lambda value: value["core_schema_admission"].update(semantic_commit="0" * 40))
    rejected("surface-min-items-weakened", lambda value: value["core_schema_admission"]["surface_inventory_constraints"].update(items_min_items=0))
    rejected("matrix-proof-weakened", lambda value: value["core_schema_admission"]["verification_matrix_constraints"].update(required_row_evidence_min_items=0))
    rejected("validator-review-weakened", lambda value: value["core_schema_admission"]["validator_invariants"].update(review_queue_mapping_required=False))
    rejected("placeholder-root-admitted", lambda value: value["core_schema_admission"].update(placeholder_root_contract_allowed=True))
    rejected("depth-rows-forged", lambda value: value["root_adapters"]["depth_parity"].update(row_count=1))
    rejected("depth-status-promoted", lambda value: value["root_adapters"]["depth_parity"].update(completion_status="parity"))
    rejected("depth-open-axes-concealed", lambda value: value["root_adapters"]["depth_parity"].update(open_axes=[]))
    rejected("runtime-denominator-shrink", lambda value: value["scenario_denominator"].update(candidate_rows=999))
    rejected("runtime-credit-forged", lambda value: value["credit"].update(runtime=1))
    rejected("fixture-reference-pass", lambda value: value["core_standard_artifacts"]["reference_results"].update(status="passed"))
    rejected("static-pattern-credit", lambda value: value["core_standard_artifacts"]["pattern_results"]["counts"].update(rows=1))
    rejected("root-surface-early-emit", lambda value: value["root_adapters"]["surface_inventory"].update(present=True, emission_eligible=True))
    rejected("root-matrix-early-emit", lambda value: value["root_adapters"]["verification_matrix"].update(present=True, emission_eligible=True))
    rejected("refusal-mapping-retreat", lambda value: value["scenario_migration"]["mapping"].update(rejection="rejection"))
    rejected("mapping-row-retreat", lambda value: value["scenario_migration"]["counts"].update(new_rows=999))
    rejected("core-class-duplicate", lambda value: value["root_adapters"]["verification_matrix"]["scenario_classes"][2].update(core="boundary"))
    rejected("schema-adapter-row-retreat", lambda value: value["scenario_schema_adapter"].update(validated_rows=999))
    rejected("schema-adapter-early-publish", lambda value: value["scenario_schema_adapter"].update(canonical_emitted=True))
    rejected("schema-adapter-runtime-credit", lambda value: value["scenario_schema_adapter"].update(runtime_credit=1))
    rejected("blocker-retreat", lambda value: value["blockers"].pop())
    print("Core v2 root contract gap fixtures passed: positive=1 negative=24")


if __name__ == "__main__":
    main()
