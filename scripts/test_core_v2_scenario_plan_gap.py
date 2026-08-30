#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for the Core v2 Scenario migration boundary."""

from __future__ import annotations

import copy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_core_v2_scenario_plan_gap import CORE_SCENARIOS, build  # noqa: E402


def validate(document: dict) -> None:
    denominator = document["denominator"]
    gaps = document["independent_gaps"]
    migration = document["core_schema_migration"]
    if document["status"] != "incomplete-no-runtime-substitution":
        raise ValueError("Scenario gap was promoted")
    if denominator["rows"] != 1000 or denominator["remaining_rows"] != 1000 or denominator["scenario_gaps_open"] != 1000:
        raise ValueError("Scenario denominator retreated")
    if gaps["authority_atomic_rows"] != 0 or gaps["approved_variant_denominators"] != 0 or gaps["dedicated_runtime_reports"] != 0:
        raise ValueError("Runtime/Authority gap hidden")
    if migration["required_scenarios"] != CORE_SCENARIOS or migration["explicit_id_mapping"] != {"rejection": "refusal"}:
        raise ValueError("Scenario migration mapping changed")
    if migration["coarse_aggregation_forbidden"] is not True or document["forbidden_substitutions"] != [
        "fixture-as-runtime", "metadata-only-as-runtime", "integrated-result-as-pattern-proof", "historical-artifact-as-current-rerun"
    ]:
        raise ValueError("Substitution boundary weakened")


def rejected(name: str, mutate) -> None:
    fixture = copy.deepcopy(build())
    mutate(fixture)
    try:
        validate(fixture)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    validate(build())
    rejected("false-complete", lambda value: value.update(status="complete"))
    rejected("denominator-shrink", lambda value: value["denominator"].update(rows=999))
    rejected("runtime-fabrication", lambda value: value["independent_gaps"].update(dedicated_runtime_reports=1))
    rejected("mapping-removal", lambda value: value["core_schema_migration"].update(explicit_id_mapping={}))
    rejected("fixture-substitution", lambda value: value["forbidden_substitutions"].remove("fixture-as-runtime"))
    print("Core v2 Scenario Plan gap fixtures passed: positive=1 negative=5")


if __name__ == "__main__":
    main()
