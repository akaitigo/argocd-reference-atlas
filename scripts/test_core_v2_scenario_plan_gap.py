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
    gates = document["core_gate_status"]
    preflight = document["runtime_preflight"]
    if document["status"] != "incomplete-no-runtime-substitution":
        raise ValueError("Scenario gap was promoted")
    if denominator["rows"] != 1000 or denominator["remaining_rows"] != 987 or denominator["scenario_gaps_open"] != 1000:
        raise ValueError("Scenario denominator retreated")
    if gaps["authority_atomic_rows"] != 0 or gaps["approved_variant_denominators"] != 0 or gaps["dedicated_runtime_reports"] != 13 or gaps["dedicated_runtime_execution_complete_rows"] != 13:
        raise ValueError("Runtime/Authority gap hidden")
    if migration["required_scenarios"] != CORE_SCENARIOS or migration["explicit_id_mapping"] != {"rejection": "refusal"}:
        raise ValueError("Scenario migration mapping changed")
    if migration["coarse_aggregation_forbidden"] is not True or document["forbidden_substitutions"] != [
        "fixture-as-runtime", "metadata-only-as-runtime", "integrated-result-as-pattern-proof", "historical-artifact-as-current-rerun"
    ]:
        raise ValueError("Substitution boundary weakened")
    if set(gates) != {"scenario_trace", "scenario_plan", "evidence_durability", "configured_make_check"}:
        raise ValueError("Core Scenario gate denominator retreated")
    if any(gates[name].startswith("passed") for name in ("scenario_trace", "scenario_plan", "evidence_durability")):
        raise ValueError("Unclosed Core Scenario gate was promoted")
    if preflight != {
        "state": "partial-dedicated-local-kind-runtime-proof",
        "dedicated_local_kind_required": True,
        "completed_dedicated_rows": 13,
        "external_context_access_forbidden": True,
        "fixture_runtime_credit": False,
    }:
        raise ValueError("Runtime preflight boundary changed")


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
    rejected("runtime-fabrication", lambda value: value["independent_gaps"].update(dedicated_runtime_reports=6))
    rejected("mapping-removal", lambda value: value["core_schema_migration"].update(explicit_id_mapping={}))
    rejected("fixture-substitution", lambda value: value["forbidden_substitutions"].remove("fixture-as-runtime"))
    rejected("gate-false-pass", lambda value: value["core_gate_status"].update(scenario_trace="passed"))
    rejected("external-context-access", lambda value: value["runtime_preflight"].update(external_context_access_forbidden=False))
    rejected("fixture-runtime-credit", lambda value: value["runtime_preflight"].update(fixture_runtime_credit=True))
    print("Core v2 Scenario Plan gap fixtures passed: positive=1 negative=8")


if __name__ == "__main__":
    main()
