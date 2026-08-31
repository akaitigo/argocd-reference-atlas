#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Compile Core v2 root Surface Inventory only from human-reviewed Authority results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
BINDINGS = ROOT / "definitive/root-surface-inventory-bindings.yaml"
READINESS = ROOT / "artifacts/core-v2/surface-inventory-readiness.json"
DECISIONS = ROOT / "authority/reviews/decisions.json"
EXTRACTION = ROOT / "authority/extraction.snapshot.json"
BODY = ROOT / "authority/body-inventory.snapshot.json"
REVIEW = ROOT / "authority/review-queue.snapshot.json"
SCENARIOS = ROOT / "evidence/scenarios/index.json"
COVERAGE = ROOT / "coverage.yaml"
OUTPUT = ROOT / "artifacts/core-v2/root-surface-inventory-closure.json"
ROOT_INVENTORY = ROOT / "surface.inventory.yaml"
EXPECTED_SCENARIOS = {"normal", "boundary", "rejection", "failure", "recovery", "migration", "operations", "security", "performance", "compatibility"}
INPUT_PATHS = [BINDINGS, READINESS, DECISIONS, EXTRACTION, BODY, REVIEW, SCENARIOS, COVERAGE]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path.relative_to(ROOT)}")
    return value


def decision_results(decisions: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    decision_ids: set[str] = set()
    surface_ids: set[str] = set()
    behavior_ids: set[str] = set()
    for decision in decisions["decisions"]:
        decision_ids.add(decision["decision_id"])
        if decision["review_method"] != "manual-primary-source":
            raise ValueError("Authority decisionはmanual-primary-sourceでなければなりません")
        for item in decision["result_items"]:
            target = surface_ids if item["item_type"] == "surface" else behavior_ids
            target.add(item["id"])
    return decision_ids, surface_ids, behavior_ids


def validate_binding_contract(bindings: dict[str, Any], decisions: dict[str, Any]) -> None:
    expected_policy = {
        "source": "authority/reviews/decisions.json",
        "final_authority_artifact_suffix": ".authority-surfaces.yaml",
        "candidate_is_final_surface": False,
        "machine_proposal_is_human_decision": False,
        "dedicated_target_and_claim_required": True,
        "ten_scenario_proofs_required": True,
        "completion_eligible_runtime_proof_required": True,
    }
    if bindings.get("schema_version") != 1 or bindings.get("atlas_id") != "argocd-reference-atlas" or bindings.get("policy") != expected_policy:
        raise ValueError("root Surface Inventory binding policyが不正です")
    if decisions["status"] != "closed" and bindings["items"]:
        raise ValueError("Human Review Queue未完了でroot binding itemを追加できません")
    required = {
        "id", "authority_artifact_id", "authority_artifact_path", "authority_artifact_digest", "authority_surface_id",
        "review_decision_ids", "locator", "kind", "capability_id", "behavior_id", "variant_ids", "target_id", "title",
        "surface_ids", "rationale", "claim_id", "scenario_matrix",
    }
    decision_ids, reviewed_surfaces, reviewed_behaviors = decision_results(decisions)
    seen: set[str] = set()
    for item in bindings["items"]:
        if set(item) != required:
            raise ValueError(f"root binding field集合が不正です: {item.get('id')}")
        if item["id"] in seen:
            raise ValueError(f"root binding IDが重複しています: {item['id']}")
        seen.add(item["id"])
        if not set(item["review_decision_ids"]) <= decision_ids:
            raise ValueError(f"未確認decisionを参照しています: {item['id']}")
        qualified_surface = f"{item['authority_artifact_id']}.{item['authority_surface_id']}"
        if qualified_surface not in reviewed_surfaces or item["behavior_id"] not in reviewed_behaviors:
            raise ValueError(f"Human Review resultにないSurface/Behaviorです: {item['id']}")
        if not item["authority_artifact_path"].endswith(".authority-surfaces.yaml"):
            raise ValueError(f"final Authority Artifactではありません: {item['id']}")
        artifact = ROOT / item["authority_artifact_path"]
        if not artifact.is_file() or digest(artifact) != item["authority_artifact_digest"]:
            raise ValueError(f"final Authority Artifact bindingが不正です: {item['id']}")
        matrix = item["scenario_matrix"]
        if set(matrix) != EXPECTED_SCENARIOS:
            raise ValueError(f"10 Scenario専用Proofが揃っていません: {item['id']}")
        for scenario, row in matrix.items():
            required_row_fields = {
                "proof_path", "proof_obligation_id", "evidence_id", "execution_requirement",
                "profile", "applicability", "rationale",
            }
            if set(row) != required_row_fields or row["applicability"] != "required":
                raise ValueError(f"10 Scenario row契約が不正です: {item['id']}:{scenario}")
            if row["execution_requirement"] not in {"runtime", "platform"} or row["profile"] not in {
                "local", "container", "vm", "cluster", "simulator", "cloud-live", "hardware-in-the-loop",
            }:
                raise ValueError(f"実行Profileが実Proof要件を満たしません: {item['id']}:{scenario}")
            if len(row["rationale"]) < 20 or not (ROOT / row["proof_path"]).is_file():
                raise ValueError(f"10 Scenario専用Proofが不正です: {item['id']}:{scenario}")


def build() -> dict[str, Any]:
    bindings = load(BINDINGS)
    readiness = load(READINESS)
    decisions = load(DECISIONS)
    extraction = load(EXTRACTION)
    body = load(BODY)
    review = load(REVIEW)
    scenarios = load(SCENARIOS)
    validate_binding_contract(bindings, decisions)
    decision_ids, reviewed_surfaces, reviewed_behaviors = decision_results(decisions)
    final_artifacts = sorted(ROOT.glob("authority/**/*.authority-surfaces.yaml"))
    blockers = []
    if not extraction["summary"]["authority_text_surfaces_exhaustive"]:
        blockers.append("authority-text-not-exhaustive")
    if not body["summary"]["authority_semantics_exhaustive"]:
        blockers.append("authority-semantics-not-exhaustive")
    if decisions["status"] != "closed" or not decision_ids:
        blockers.append("authority-human-decisions-not-closed")
    if not reviewed_surfaces or not reviewed_behaviors:
        blockers.append("reviewed-surface-or-atomic-behavior-zero")
    if extraction["summary"]["core_v2_eligible_surfaces"] == 0:
        blockers.append("core-v2-eligible-surfaces-zero")
    if not final_artifacts:
        blockers.append("final-authority-artifacts-zero")
    if not bindings["items"]:
        blockers.append("root-inventory-bindings-zero")
    if scenarios["summary"]["completion_eligible_rows"] == 0:
        blockers.append("completion-eligible-scenario-rows-zero")
    return {
        "schema_version": 1,
        "id": "argocd-root-surface-inventory-closure-v1",
        "status": "ready-to-emit" if not blockers else "blocked-human-authority-and-proof-closure",
        "inputs": {path.relative_to(ROOT).as_posix(): digest(path) for path in INPUT_PATHS},
        "dependency_contract": {
            "graph_output": "artifacts/core-v2/root-surface-inventory-closure.json",
            "tracked_input_paths": [path.relative_to(ROOT).as_posix() for path in INPUT_PATHS],
            "stale_on_any_input_digest_change": True,
            "required_rerun": "python3 scripts/generate_root_surface_inventory.py && python3 scripts/test_root_surface_inventory.py",
            "digest_only_closure_forbidden": True,
        },
        "policy": {
            "emit_only_when_all_blockers_closed": True,
            "unreviewed_candidate_promotion_forbidden": True,
            "machine_human_review_substitution_forbidden": True,
            "baseline_or_scope_reduction_forbidden": True,
            "real_evidence_binding_required": True,
        },
        "denominator": {
            "authority_raw_anchors": body["summary"]["raw_anchor_candidates"],
            "authority_pending_human": body["summary"]["pending_human_anchors"],
            "candidate_edges": readiness["summary"]["candidate_edges"],
            "candidate_inventory_unmapped": readiness["summary"]["candidate_inventory_unmapped"],
            "scenario_rows": scenarios["summary"]["rows"],
        },
        "closure": {
            "human_decisions": len(decision_ids),
            "reviewed_surfaces": len(reviewed_surfaces),
            "reviewed_atomic_behaviors": len(reviewed_behaviors),
            "core_v2_eligible_surfaces": extraction["summary"]["core_v2_eligible_surfaces"],
            "final_authority_artifacts": len(final_artifacts),
            "root_binding_items": len(bindings["items"]),
            "dedicated_runtime_rows": scenarios["summary"]["dedicated_runtime_execution_complete_rows"],
            "completion_eligible_scenario_rows": scenarios["summary"]["completion_eligible_rows"],
            "semantic_credit": body["summary"]["promoted_surface_artifacts"],
        },
        "root_inventory": {
            "path": "surface.inventory.yaml",
            "present": ROOT_INVENTORY.is_file(),
            "emission_eligible": not blockers,
            "blockers": blockers,
        },
    }


def compile_inventory(plan: dict[str, Any]) -> dict[str, Any]:
    if plan["root_inventory"]["blockers"]:
        raise ValueError("root Surface InventoryはHuman Authority/Proof Closure前に発行できません")
    bindings = load(BINDINGS)
    artifacts: dict[str, dict[str, str]] = {}
    items = []
    for binding in bindings["items"]:
        artifacts[binding["authority_artifact_id"]] = {
            "id": binding["authority_artifact_id"],
            "source_id": load(ROOT / binding["authority_artifact_path"])["source_id"],
            "path": binding["authority_artifact_path"],
            "digest": binding["authority_artifact_digest"],
        }
        items.append({
            "id": binding["id"], "authority_artifact_id": binding["authority_artifact_id"],
            "authority_surface_id": binding["authority_surface_id"], "locator": binding["locator"], "kind": binding["kind"],
            "capability_id": binding["capability_id"], "behavior_id": binding["behavior_id"], "variant_ids": binding["variant_ids"],
            "target_id": binding["target_id"], "title": binding["title"], "surface_ids": binding["surface_ids"],
            "classification": "included", "rationale": binding["rationale"], "claim_ids": [binding["claim_id"]],
        })
    coverage = load(COVERAGE)
    return {
        "schema_version": 2, "atlas_id": "argocd-reference-atlas", "epoch": coverage["epoch"],
        "authority_lock_digest": coverage["authority_lock_digest"],
        "authority_artifacts": sorted(artifacts.values(), key=lambda item: item["id"]),
        "items": sorted(items, key=lambda item: item["id"]),
    }


def validate(document: dict[str, Any]) -> None:
    if document != build():
        raise ValueError("root Surface Inventory closure artifactが現在入力からの導出値と一致しません")
    if document["closure"]["human_decisions"] == 0 and document["root_inventory"]["emission_eligible"]:
        raise ValueError("Human decision 0でroot Inventoryを発行可能にしています")
    if document["closure"]["human_decisions"] == 0 and (
        document["closure"]["semantic_credit"] != 0 or document["root_inventory"]["present"]
    ):
        raise ValueError("未review状態でSemantic creditまたはroot Inventoryがあります")
    dependency = document["dependency_contract"]
    expected_paths = [path.relative_to(ROOT).as_posix() for path in INPUT_PATHS]
    if dependency != {
        "graph_output": "artifacts/core-v2/root-surface-inventory-closure.json",
        "tracked_input_paths": expected_paths,
        "stale_on_any_input_digest_change": True,
        "required_rerun": "python3 scripts/generate_root_surface_inventory.py && python3 scripts/test_root_surface_inventory.py",
        "digest_only_closure_forbidden": True,
    } or list(document["inputs"]) != expected_paths:
        raise ValueError("root Surface Inventoryのstale Graph契約が不完全です")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    plan = build()
    if args.emit:
        compiled = compile_inventory(plan)
        ROOT_INVENTORY.write_text(yaml.safe_dump(compiled, allow_unicode=True, sort_keys=False), encoding="utf-8")
    elif args.check:
        validate(load(OUTPUT))
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validate(plan)
    print(f"Root Surface Inventory closure: status={plan['status']} bindings={plan['closure']['root_binding_items']} blockers={len(plan['root_inventory']['blockers'])}")


if __name__ == "__main__":
    main()
