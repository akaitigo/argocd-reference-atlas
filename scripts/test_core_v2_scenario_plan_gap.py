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
    standard = document["core_standard_artifacts"]
    root_adapter = document["root_contract_adapter"]
    if document["status"] != "incomplete-no-runtime-substitution":
        raise ValueError("Scenario gap was promoted")
    if denominator["rows"] != 1000 or denominator["remaining_rows"] != 987 or denominator["scenario_gaps_open"] != 1000:
        raise ValueError("Scenario denominator retreated")
    if gaps["authority_atomic_rows"] != 0 or gaps["approved_variant_denominators"] != 0 or gaps["dedicated_runtime_reports"] != 13 or gaps["dedicated_runtime_execution_complete_rows"] != 13:
        raise ValueError("Runtime/Authority gap hidden")
    if migration["required_scenarios"] != CORE_SCENARIOS or migration["explicit_id_mapping"] != {"rejection": "refusal"}:
        raise ValueError("Scenario migration mapping changed")
    if migration["full_row_mapping"]["rows"] != 1000 or migration["full_row_mapping"]["renamed_rows"] != 100 or migration["full_row_mapping"]["runtime_credit"] != 0 or not migration["structure_baseline"]["digest"]:
        raise ValueError("Scenario full-row migration or baseline changed")
    if migration["coarse_aggregation_forbidden"] is not True or document["forbidden_substitutions"] != [
        "fixture-as-runtime", "metadata-only-as-runtime", "integrated-result-as-pattern-proof", "historical-artifact-as-current-rerun"
    ]:
        raise ValueError("Substitution boundary weakened")
    if set(gates) != {"scenario_trace", "scenario_plan", "evidence_durability", "configured_make_check"}:
        raise ValueError("Core Scenario gate denominator retreated")
    if any(gates[name].startswith("passed") for name in ("scenario_trace", "scenario_plan", "evidence_durability")):
        raise ValueError("Unclosed Core Scenario gate was promoted")
    if gaps["missing_core_artifacts"] != [] or standard["manifest"]["status"] != "bounded-integration-proof" or standard["reference_results"]["status"] != "failed" or standard["pattern_results"]["status"] != "failed":
        raise ValueError("Core standard gap artifact status changed")
    if standard["reference_results"]["passed"] != 0 or standard["pattern_results"]["records"] != 0 or standard["runtime_credit"] != 0 or standard["completion_eligible"] != 0:
        raise ValueError("Core standard gap artifact gained runtime/completion credit")
    if root_adapter != {
        "path": "artifacts/core-v2/root-contract-adapter-gap.json",
        "digest": root_adapter["digest"],
        "status": "incomplete-human-and-runtime-gaps",
        "authority_pending_human": 63889,
        "semantic_credit": 0,
        "runtime_credit": 0,
        "completion_eligible": 0,
        "root_surface_inventory_emitted": False,
        "root_verification_matrix_emitted": False,
        "rejection_to_refusal_rows": 100,
    } or not root_adapter["digest"]:
        raise ValueError("root contract adapter gapが縮小または昇格しています")
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
    rejected("full-mapping-retreat", lambda value: value["core_schema_migration"]["full_row_mapping"].update(rows=999))
    rejected("fixture-substitution", lambda value: value["forbidden_substitutions"].remove("fixture-as-runtime"))
    rejected("gate-false-pass", lambda value: value["core_gate_status"].update(scenario_trace="passed"))
    rejected("external-context-access", lambda value: value["runtime_preflight"].update(external_context_access_forbidden=False))
    rejected("fixture-runtime-credit", lambda value: value["runtime_preflight"].update(fixture_runtime_credit=True))
    rejected("core-standard-runtime-credit", lambda value: value["core_standard_artifacts"].update(runtime_credit=1))
    rejected("core-standard-false-pass", lambda value: value["core_standard_artifacts"]["pattern_results"].update(status="passed"))
    rejected("root-adapter-semantic-credit", lambda value: value["root_contract_adapter"].update(semantic_credit=1))
    rejected("root-adapter-runtime-credit", lambda value: value["root_contract_adapter"].update(runtime_credit=1))
    rejected("root-adapter-early-emit", lambda value: value["root_contract_adapter"].update(root_surface_inventory_emitted=True))
    print("Core v2 Scenario Plan gap fixtures passed: positive=1 negative=14")


if __name__ == "__main__":
    main()
