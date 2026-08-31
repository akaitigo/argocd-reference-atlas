#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Compile the Core v2 root Matrix only from reviewed, completion-eligible rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from generate_root_surface_inventory import BINDINGS, OUTPUT as INVENTORY_CLOSURE, load


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "evidence/scenarios/index.json"
DECISIONS = ROOT / "authority/reviews/decisions.json"
COVERAGE = ROOT / "coverage.yaml"
OUTPUT = ROOT / "artifacts/core-v2/root-verification-matrix-closure.json"
ROOT_INVENTORY = ROOT / "surface.inventory.yaml"
ROOT_MATRIX = ROOT / "verification.matrix.yaml"
SCENARIO_ORDER = ("normal", "boundary", "rejection", "failure", "recovery", "migration", "operations", "security", "performance", "compatibility")
CORE_SCENARIO_BY_LEGACY = {scenario: ("refusal" if scenario == "rejection" else scenario) for scenario in SCENARIO_ORDER}
CORE_SCENARIOS = {"normal", "boundary", "refusal", "failure", "recovery", "migration", "operations", "security", "performance", "compatibility"}
INPUT_PATHS = [BINDINGS, INVENTORY_CLOSURE, SCENARIOS, DECISIONS, COVERAGE]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, Any]:
    bindings = load(BINDINGS)
    inventory_closure = load(INVENTORY_CLOSURE)
    scenarios = load(SCENARIOS)
    decisions = load(DECISIONS)
    reviewed_behaviors = inventory_closure["closure"]["reviewed_atomic_behaviors"]
    expected_rows = reviewed_behaviors * len(SCENARIO_ORDER)
    completion_eligible = scenarios["summary"]["completion_eligible_rows"]
    authority_bindings = scenarios["summary"]["authority_atomic_bindings"]
    blockers = []
    if not ROOT_INVENTORY.is_file() or not inventory_closure["root_inventory"]["emission_eligible"]:
        blockers.append("root-surface-inventory-not-emitted")
    if reviewed_behaviors == 0:
        blockers.append("reviewed-atomic-behaviors-zero")
    if not bindings["items"]:
        blockers.append("root-inventory-bindings-zero")
    if authority_bindings == 0:
        blockers.append("authority-atomic-bindings-zero")
    if completion_eligible == 0:
        blockers.append("completion-eligible-scenario-rows-zero")
    if expected_rows == 0:
        blockers.append("reviewed-matrix-cell-denominator-zero")
    if expected_rows != completion_eligible:
        blockers.append("reviewed-matrix-proof-closure-incomplete")
    if decisions["status"] != "closed":
        blockers.append("authority-human-decisions-not-closed")

    by_scenario = scenarios["by_scenario"]
    scenario_classes = []
    for scenario in SCENARIO_ORDER:
        legacy = by_scenario[scenario]
        scenario_classes.append({
            "scenario": scenario,
            "core_scenario": CORE_SCENARIO_BY_LEGACY[scenario],
            "reviewed_behavior_cells": reviewed_behaviors,
            "legacy_candidate_rows": legacy["rows"],
            "dedicated_runtime_rows": legacy["dedicated_runtime_execution_complete"],
            "authority_atomic_bindings": legacy["authority_atomic_bindings"],
            "completion_eligible_rows": legacy["completion_eligible"],
            "status": "closed" if reviewed_behaviors > 0 and legacy["completion_eligible"] == reviewed_behaviors else "gap",
            "gap": None if reviewed_behaviors > 0 and legacy["completion_eligible"] == reviewed_behaviors else "Human-reviewed Atomic behaviorと専用completion-eligible Proofの接続が未成立。",
        })

    return {
        "schema_version": 1,
        "id": "argocd-root-verification-matrix-closure-v1",
        "status": "ready-to-emit" if not blockers else "blocked-human-authority-and-proof-closure",
        "inputs": {path.relative_to(ROOT).as_posix(): digest(path) for path in INPUT_PATHS},
        "dependency_contract": {
            "graph_output": "artifacts/core-v2/root-verification-matrix-closure.json",
            "tracked_input_paths": [path.relative_to(ROOT).as_posix() for path in INPUT_PATHS],
            "stale_on_any_input_digest_change": True,
            "required_rerun": "python3 scripts/generate_root_verification_matrix.py && python3 scripts/test_root_verification_matrix.py",
            "digest_only_closure_forbidden": True,
        },
        "policy": {
            "ten_classes_per_reviewed_atomic_behavior": True,
            "generated_candidate_rows_receive_no_credit": True,
            "unproven_cells_remain_gap": True,
            "dedicated_proof_evidence_target_claim_required": True,
            "evidence_reuse_forbidden": True,
            "runtime_or_platform_execution_required": True,
            "fixture_or_static_runtime_substitution_forbidden": True,
            "emit_only_when_all_blockers_closed": True,
        },
        "denominator": {
            "scenario_classes": len(SCENARIO_ORDER),
            "reviewed_denominator_status": "pending-human-authority-review" if reviewed_behaviors == 0 else "established",
            "reviewed_atomic_behaviors": reviewed_behaviors,
            "expected_reviewed_matrix_rows": expected_rows,
            "legacy_candidate_behaviors": scenarios["summary"]["behaviors"],
            "legacy_candidate_rows": scenarios["summary"]["rows"],
            "legacy_candidate_rows_open": scenarios["summary"]["scenario_gaps_open"],
            "legacy_rows_completion_credit": 0,
        },
        "closure": {
            "root_binding_items": len(bindings["items"]),
            "dedicated_runtime_rows": scenarios["summary"]["dedicated_runtime_execution_complete_rows"],
            "authority_atomic_bindings": authority_bindings,
            "completion_eligible_rows": completion_eligible,
            "closed_reviewed_matrix_rows": completion_eligible,
            "remaining_reviewed_matrix_rows": max(expected_rows - completion_eligible, 0),
        },
        "scenario_classes": scenario_classes,
        "root_matrix": {
            "path": "verification.matrix.yaml",
            "present": ROOT_MATRIX.is_file(),
            "emission_eligible": not blockers,
            "blockers": blockers,
        },
    }


def compile_matrix(plan: dict[str, Any]) -> dict[str, Any]:
    if plan["root_matrix"]["blockers"]:
        raise ValueError("root Verification MatrixはHuman Authority/Proof Closure前に発行できません")
    bindings = load(BINDINGS)
    coverage = load(COVERAGE)
    rows: list[dict[str, Any]] = []
    used_proofs: set[str] = set()
    used_evidence: set[str] = set()
    for binding in bindings["items"]:
        for scenario in SCENARIO_ORDER:
            source = binding["scenario_matrix"][scenario]
            proof_id, evidence_id = source["proof_obligation_id"], source["evidence_id"]
            if proof_id in used_proofs or evidence_id in used_evidence:
                raise ValueError(f"Scenario専用Proof/Evidenceが再利用されています: {binding['behavior_id']}:{scenario}")
            used_proofs.add(proof_id)
            used_evidence.add(evidence_id)
            rows.append({
                "behavior_id": binding["behavior_id"],
                "scenario": CORE_SCENARIO_BY_LEGACY[scenario],
                "applicability": source["applicability"],
                "rationale": source["rationale"],
                "proof_obligation_id": proof_id,
                "evidence_ids": [evidence_id],
                "execution_requirement": source["execution_requirement"],
                "profile": source["profile"],
            })
    return {
        "schema_version": 2,
        "atlas_id": "argocd-reference-atlas",
        "epoch": coverage["epoch"],
        "rows": rows,
    }


def validate(document: dict[str, Any]) -> None:
    if document != build():
        raise ValueError("root Verification Matrix closure artifactが現在入力からの導出値と一致しません")
    denominator = document["denominator"]
    closure = document["closure"]
    if denominator["scenario_classes"] != 10 or len(document["scenario_classes"]) != 10:
        raise ValueError("10-class Matrix denominatorが縮小されています")
    core_scenarios = [item["core_scenario"] for item in document["scenario_classes"]]
    if len(set(core_scenarios)) != 10 or set(core_scenarios) != CORE_SCENARIOS:
        raise ValueError("Core Matrix 10-class identityが重複または欠落しています")
    legacy_to_core = {item["scenario"]: item["core_scenario"] for item in document["scenario_classes"]}
    if legacy_to_core.get("rejection") != "refusal" or "rejection" in core_scenarios:
        raise ValueError("legacy rejectionをCore refusalへ正規化していません")
    if denominator["legacy_candidate_rows"] != 1000 or denominator["legacy_rows_completion_credit"] != 0:
        raise ValueError("既存candidate Matrixをroot達成へ算入しています")
    if denominator["reviewed_atomic_behaviors"] == 0 and denominator["reviewed_denominator_status"] != "pending-human-authority-review":
        raise ValueError("未成立のreviewed denominatorを確定扱いしています")
    if closure["authority_atomic_bindings"] == 0 and closure["completion_eligible_rows"] != 0:
        raise ValueError("Authority atomic bindingなしでMatrixを閉じています")
    if denominator["reviewed_atomic_behaviors"] == 0 and document["root_matrix"]["emission_eligible"]:
        raise ValueError("reviewed Atomic behavior 0でroot Matrixを発行可能にしています")
    if not document["root_matrix"]["emission_eligible"] and document["root_matrix"]["present"]:
        raise ValueError("未完状態でroot Verification Matrixがあります")
    dependency = document["dependency_contract"]
    expected_paths = [path.relative_to(ROOT).as_posix() for path in INPUT_PATHS]
    if dependency != {
        "graph_output": "artifacts/core-v2/root-verification-matrix-closure.json",
        "tracked_input_paths": expected_paths,
        "stale_on_any_input_digest_change": True,
        "required_rerun": "python3 scripts/generate_root_verification_matrix.py && python3 scripts/test_root_verification_matrix.py",
        "digest_only_closure_forbidden": True,
    } or list(document["inputs"]) != expected_paths:
        raise ValueError("root Verification Matrixのstale Graph契約が不完全です")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    plan = build()
    if args.emit:
        compiled = compile_matrix(plan)
        ROOT_MATRIX.write_text(yaml.safe_dump(compiled, allow_unicode=True, sort_keys=False), encoding="utf-8")
    elif args.check:
        validate(load(OUTPUT))
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validate(plan)
    print(f"Root Verification Matrix closure: status={plan['status']} rows={plan['closure']['closed_reviewed_matrix_rows']}/{plan['denominator']['expected_reviewed_matrix_rows']} blockers={len(plan['root_matrix']['blockers'])}")


if __name__ == "__main__":
    main()
