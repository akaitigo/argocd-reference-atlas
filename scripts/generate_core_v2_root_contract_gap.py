#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Core標準Artifactとroot adapterを一つのfail-closed Gapへ束縛する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROOT_SURFACE = Path("artifacts/core-v2/root-surface-inventory-closure.json")
ROOT_MATRIX = Path("artifacts/core-v2/root-verification-matrix-closure.json")
CORE_MANIFEST = Path("integrations/reference-system/manifest.json")
REFERENCE_RESULTS = Path("artifacts/reference-system/results.json")
PATTERN_RESULTS = Path("artifacts/pattern-scenarios/results.json")
MIGRATION = Path("migrations/scenario-class-refusal-v1.json")
MIGRATION_BASELINE = Path("baselines/scenario-row-id-migration-v1.json")
SCENARIO_INDEX = Path("evidence/scenarios/index.json")
OUTPUT = Path("artifacts/core-v2/root-contract-adapter-gap.json")
CORE_SCENARIOS = (
    "normal", "boundary", "refusal", "failure", "recovery",
    "migration", "operations", "security", "performance", "compatibility",
)
LEGACY_TO_CORE = {
    "normal": "normal", "boundary": "boundary", "rejection": "refusal",
    "failure": "failure", "recovery": "recovery", "migration": "migration",
    "operations": "operations", "security": "security",
    "performance": "performance", "compatibility": "compatibility",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path}")
    return value


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def build() -> dict[str, Any]:
    surface = load(ROOT_SURFACE)
    matrix = load(ROOT_MATRIX)
    manifest = load(CORE_MANIFEST)
    reference = load(REFERENCE_RESULTS)
    pattern = load(PATTERN_RESULTS)
    migration = load(MIGRATION)
    baseline = load(MIGRATION_BASELINE)
    scenarios = load(SCENARIO_INDEX)
    matrix_classes = [
        {
            "legacy": item["scenario"],
            "core": item["core_scenario"],
            "status": item["status"],
            "dedicated_runtime_rows": item["dedicated_runtime_rows"],
            "completion_eligible_rows": item["completion_eligible_rows"],
        }
        for item in matrix["scenario_classes"]
    ]
    blockers = [
        "core-reference-system-runtime-not-run",
        "pattern-scenario-runtime-incomplete",
        *[f"root-surface:{item}" for item in surface["root_inventory"]["blockers"]],
        *[f"root-matrix:{item}" for item in matrix["root_matrix"]["blockers"]],
    ]
    return {
        "schema_version": 1,
        "id": "argocd-core-v2-root-contract-adapter-gap-v1",
        "status": "incomplete-human-and-runtime-gaps",
        "inputs": {
            path.as_posix(): digest(path)
            for path in (
                ROOT_SURFACE, ROOT_MATRIX, CORE_MANIFEST, REFERENCE_RESULTS,
                PATTERN_RESULTS, MIGRATION, MIGRATION_BASELINE, SCENARIO_INDEX,
            )
        },
        "policy": {
            "adapter_is_runtime_evidence": False,
            "adapter_is_human_review": False,
            "fixture_or_static_runtime_substitution_forbidden": True,
            "emit_root_contract_only_after_all_blockers_closed": True,
            "legacy_row_replacement_before_migration_forbidden": True,
        },
        "authority": {
            "raw_anchors": surface["denominator"]["authority_raw_anchors"],
            "pending_human": surface["denominator"]["authority_pending_human"],
            "human_decisions": surface["closure"]["human_decisions"],
            "reviewed_atomic_behaviors": surface["closure"]["reviewed_atomic_behaviors"],
            "semantic_credit": surface["closure"]["semantic_credit"],
        },
        "scenario_denominator": {
            "candidate_behaviors": matrix["denominator"]["legacy_candidate_behaviors"],
            "candidate_rows": matrix["denominator"]["legacy_candidate_rows"],
            "candidate_rows_open": matrix["denominator"]["legacy_candidate_rows_open"],
            "dedicated_runtime_rows": scenarios["summary"]["dedicated_runtime_execution_complete_rows"],
            "remaining_runtime_rows": 1000 - scenarios["summary"]["dedicated_runtime_execution_complete_rows"],
            "authority_atomic_bindings": scenarios["summary"]["authority_atomic_bindings"],
            "completion_eligible_rows": scenarios["summary"]["completion_eligible_rows"],
        },
        "core_standard_artifacts": {
            "manifest": {"path": CORE_MANIFEST.as_posix(), "status": manifest["status"], "runtime": manifest["runtime"]},
            "reference_results": {"path": REFERENCE_RESULTS.as_posix(), "status": reference["status"], "counts": reference["counts"]},
            "pattern_results": {"path": PATTERN_RESULTS.as_posix(), "status": pattern["status"], "counts": pattern["counts"]},
            "runtime_credit": 0,
            "completion_eligible": 0,
        },
        "root_adapters": {
            "surface_inventory": {
                "path": ROOT_SURFACE.as_posix(),
                "status": surface["status"],
                "root_path": surface["root_inventory"]["path"],
                "present": surface["root_inventory"]["present"],
                "emission_eligible": surface["root_inventory"]["emission_eligible"],
                "blockers": surface["root_inventory"]["blockers"],
            },
            "verification_matrix": {
                "path": ROOT_MATRIX.as_posix(),
                "status": matrix["status"],
                "root_path": matrix["root_matrix"]["path"],
                "present": matrix["root_matrix"]["present"],
                "emission_eligible": matrix["root_matrix"]["emission_eligible"],
                "reviewed_denominator_status": matrix["denominator"]["reviewed_denominator_status"],
                "scenario_classes": matrix_classes,
                "blockers": matrix["root_matrix"]["blockers"],
            },
        },
        "scenario_migration": {
            "path": MIGRATION.as_posix(),
            "baseline_path": MIGRATION_BASELINE.as_posix(),
            "mapping": LEGACY_TO_CORE,
            "counts": migration["counts"],
            "old_set_digest": baseline["old_set_digest"],
            "new_set_digest": baseline["new_set_digest"],
        },
        "credit": {
            "runtime": 0,
            "semantic": 0,
            "completion": 0,
            "root_surface_inventory_emitted": False,
            "root_verification_matrix_emitted": False,
        },
        "blockers": blockers,
    }


def validate(document: dict[str, Any]) -> None:
    authority = document["authority"]
    scenario = document["scenario_denominator"]
    standard = document["core_standard_artifacts"]
    adapters = document["root_adapters"]
    migration = document["scenario_migration"]
    credit = document["credit"]
    require(document["status"] == "incomplete-human-and-runtime-gaps" and bool(document["blockers"]), "root契約Gapが完了扱いです")
    require(authority == {"raw_anchors": 63889, "pending_human": 63889, "human_decisions": 0, "reviewed_atomic_behaviors": 0, "semantic_credit": 0}, "Authority denominatorまたはsemantic creditが変化しています")
    require(scenario == {"candidate_behaviors": 100, "candidate_rows": 1000, "candidate_rows_open": 1000, "dedicated_runtime_rows": 13, "remaining_runtime_rows": 987, "authority_atomic_bindings": 0, "completion_eligible_rows": 0}, "Scenario denominatorまたはRuntime Gapが変化しています")
    require(standard["manifest"]["status"] == "bounded-integration-proof" and standard["manifest"]["runtime"] == "gap-only-no-runtime-credit", "Reference manifestがRuntimeを偽装しています")
    require(standard["reference_results"]["status"] == "failed" and standard["reference_results"]["counts"]["passed"] == 0, "Reference resultが未実行Gapを失っています")
    require(standard["pattern_results"]["status"] == "failed" and standard["pattern_results"]["counts"]["rows"] == 0, "Pattern resultが専用Runtimeを偽装しています")
    require(standard["runtime_credit"] == standard["completion_eligible"] == 0, "Core標準Artifactへcreditを付与しています")
    for name in ("surface_inventory", "verification_matrix"):
        adapter = adapters[name]
        require(adapter["status"] == "blocked-human-authority-and-proof-closure", f"root adapterが未Closureを隠しています: {name}")
        require(adapter["present"] is False and adapter["emission_eligible"] is False and bool(adapter["blockers"]), f"root出力を早期発行しています: {name}")
    classes = adapters["verification_matrix"]["scenario_classes"]
    require(len(classes) == 10 and [item["core"] for item in classes] == list(CORE_SCENARIOS), "Core 10 Scenario class mappingが不正です")
    require(len({item["core"] for item in classes}) == 10 and all(item["status"] == "gap" for item in classes), "Core Scenario classが重複または昇格しています")
    require(migration["mapping"] == LEGACY_TO_CORE and migration["counts"] == {"old_rows": 1000, "new_rows": 1000, "identity": 900, "renamed_rejection_to_refusal": 100, "runtime_credit": 0, "completion_eligible": 0}, "rejection→refusal全件mappingが非後退ではありません")
    require(credit == {"runtime": 0, "semantic": 0, "completion": 0, "root_surface_inventory_emitted": False, "root_verification_matrix_emitted": False}, "adapterが証明creditを持っています")
    require(document == build(), "root契約Gapが現在inputからの決定論的導出値と一致しません")


def main() -> None:
    document = build()
    validate(document)
    target = ROOT / OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Core v2 root contract gap generated: authority=0 runtime=13/1000 completion=0")


if __name__ == "__main__":
    main()
