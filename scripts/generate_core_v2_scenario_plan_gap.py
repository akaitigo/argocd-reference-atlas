#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Describe the honest Core v2 Scenario migration boundary without runtime substitution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "evidence" / "scenarios" / "index.json"
PLAN = ROOT / "evidence" / "scenarios" / "closure-plan.json"
OUTPUT = ROOT / "artifacts" / "core-v2" / "scenario-plan-gap.json"
CORE_MANIFEST = ROOT / "integrations" / "reference-system" / "manifest.json"
CORE_REFERENCE_RESULTS = ROOT / "artifacts" / "reference-system" / "results.json"
CORE_PATTERN_RESULTS = ROOT / "artifacts" / "pattern-scenarios" / "results.json"
SCENARIO_MIGRATION = ROOT / "migrations" / "scenario-class-refusal-v1.json"
SCENARIO_MIGRATION_BASELINE = ROOT / "baselines" / "scenario-row-id-migration-v1.json"
CORE_STANDARD_PUBLISH = ROOT / "artifacts" / "core-v2" / "core-standard-artifacts-publish.json"
ROOT_CONTRACT_ADAPTER = ROOT / "artifacts" / "core-v2" / "root-contract-adapter-gap.json"
CORE_COMMIT = "072d7ca77981f51754e824d70c6d4ecd55ea67e5"
CORE_SCENARIOS = ["normal", "boundary", "refusal", "failure", "recovery", "migration", "operations", "security", "performance", "compatibility"]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    index = json.loads(INDEX.read_text())
    plan = json.loads(PLAN.read_text())
    summary = index["summary"]
    current_scenarios = sorted(index["by_scenario"])
    missing_files = [
        path for path in (
            "integrations/reference-system/manifest.json",
            "artifacts/reference-system/results.json",
            "artifacts/pattern-scenarios/results.json",
        ) if not (ROOT / path).is_file()
    ]
    standard_manifest = json.loads(CORE_MANIFEST.read_text()) if CORE_MANIFEST.is_file() else {}
    reference_results = json.loads(CORE_REFERENCE_RESULTS.read_text()) if CORE_REFERENCE_RESULTS.is_file() else {}
    pattern_results = json.loads(CORE_PATTERN_RESULTS.read_text()) if CORE_PATTERN_RESULTS.is_file() else {}
    migration = json.loads(SCENARIO_MIGRATION.read_text()) if SCENARIO_MIGRATION.is_file() else {}
    root_adapter = json.loads(ROOT_CONTRACT_ADAPTER.read_text()) if ROOT_CONTRACT_ADAPTER.is_file() else {}
    return {
        "schema_version": 1,
        "id": "argocd-core-v2-scenario-plan-gap-v1",
        "status": "incomplete-no-runtime-substitution",
        "core_commit": CORE_COMMIT,
        "inputs": {
            "evidence/scenarios/index.json": digest(INDEX),
            "evidence/scenarios/closure-plan.json": digest(PLAN),
            "artifacts/core-v2/root-contract-adapter-gap.json": digest(ROOT_CONTRACT_ADAPTER),
        },
        "denominator": {
            "patterns": summary["behaviors"],
            "scenarios": summary["scenarios"],
            "rows": summary["rows"],
            "remaining_rows": plan["summary"]["remaining_rows"],
            "scenario_gaps_open": summary["scenario_gaps_open"],
            "scenario_gaps_closed": summary["scenario_gaps_closed"],
        },
        "core_schema_migration": {
            "current_scenarios": current_scenarios,
            "required_scenarios": CORE_SCENARIOS,
            "explicit_id_mapping": {"rejection": "refusal"},
            "full_row_mapping": {
                "path": SCENARIO_MIGRATION.relative_to(ROOT).as_posix(),
                "digest": digest(SCENARIO_MIGRATION) if SCENARIO_MIGRATION.is_file() else None,
                "rows": migration.get("counts", {}).get("old_rows", 0),
                "renamed_rows": migration.get("counts", {}).get("renamed_rejection_to_refusal", 0),
                "runtime_credit": migration.get("counts", {}).get("runtime_credit", 0),
            },
            "structure_baseline": {
                "path": SCENARIO_MIGRATION_BASELINE.relative_to(ROOT).as_posix(),
                "digest": digest(SCENARIO_MIGRATION_BASELINE) if SCENARIO_MIGRATION_BASELINE.is_file() else None,
            },
            "current_rows_preserved": summary["rows"],
            "coarse_aggregation_forbidden": True,
            "in_place_overwrite_before_migration_proof": False,
        },
        "independent_gaps": {
            "authority_atomic_rows": summary["authority_atomic_bindings"],
            "approved_variant_denominators": summary["variant_denominators_exhaustive"],
            "dedicated_runtime_reports": summary["dedicated_runtime_reports"],
            "dedicated_runtime_execution_complete_rows": summary["dedicated_runtime_execution_complete_rows"],
            "completion_eligible_rows": summary["completion_eligible_rows"],
            "integrated_runtime_passed": summary["integrated_runtime_passed"],
            "missing_core_artifacts": missing_files,
        },
        "core_gate_status": {
            "scenario_trace": "blocked-root-scenario-proof-schema-and-runtime-closure",
            "scenario_plan": "blocked-pattern-scenario-runtime-report",
            "evidence_durability": "blocked-pattern-scenario-runtime-report",
            "configured_make_check": "passed",
        },
        "core_standard_artifacts": {
            "manifest": {"path": CORE_MANIFEST.relative_to(ROOT).as_posix(), "status": standard_manifest.get("status")},
            "reference_results": {"path": CORE_REFERENCE_RESULTS.relative_to(ROOT).as_posix(), "status": reference_results.get("status"), "passed": reference_results.get("counts", {}).get("passed", 0)},
            "pattern_results": {"path": CORE_PATTERN_RESULTS.relative_to(ROOT).as_posix(), "status": pattern_results.get("status"), "records": len(pattern_results.get("tests", []))},
            "atomic_publish": {"path": CORE_STANDARD_PUBLISH.relative_to(ROOT).as_posix(), "digest": digest(CORE_STANDARD_PUBLISH) if CORE_STANDARD_PUBLISH.is_file() else None},
            "runtime_credit": 0,
            "completion_eligible": 0,
        },
        "root_contract_adapter": {
            "path": ROOT_CONTRACT_ADAPTER.relative_to(ROOT).as_posix(),
            "digest": digest(ROOT_CONTRACT_ADAPTER),
            "status": root_adapter.get("status"),
            "authority_pending_human": root_adapter.get("authority", {}).get("pending_human"),
            "semantic_credit": root_adapter.get("credit", {}).get("semantic"),
            "runtime_credit": root_adapter.get("credit", {}).get("runtime"),
            "completion_eligible": root_adapter.get("credit", {}).get("completion"),
            "root_surface_inventory_emitted": root_adapter.get("credit", {}).get("root_surface_inventory_emitted"),
            "root_verification_matrix_emitted": root_adapter.get("credit", {}).get("root_verification_matrix_emitted"),
            "rejection_to_refusal_rows": root_adapter.get("scenario_migration", {}).get("counts", {}).get("renamed_rejection_to_refusal"),
        },
        "runtime_preflight": {
            "state": "partial-dedicated-local-kind-runtime-proof",
            "dedicated_local_kind_required": True,
            "completed_dedicated_rows": plan["summary"]["completed_dedicated_rows"],
            "external_context_access_forbidden": True,
            "fixture_runtime_credit": False,
        },
        "closure_requirements": {
            "first_attempt_only": True,
            "retries": 0,
            "dedicated_runtime_identity": True,
            "dedicated_oracle": True,
            "required_trace_streams": ["action", "network", "resource"],
            "separate_artifacts_per_variant": True,
            "source_and_harness_digests": True,
        },
        "forbidden_substitutions": [
            "fixture-as-runtime",
            "metadata-only-as-runtime",
            "integrated-result-as-pattern-proof",
            "historical-artifact-as-current-rerun",
        ],
        "human_independent_completed_actions": [
            "Core標準Artifactを専用stagingへ加法生成する。",
            "旧row IDから新row IDへの全件Mappingと構造非後退を検証する。",
            "Runtime未実行rowをpattern-specific-gapのまま保持する。",
            "Core標準Artifactとroot inventory／matrix adapterを正本Gapへ束縛する。",
        ],
        "human_independent_next_actions": [
            "専用local Kindがない間は外部Contextへ接続せずRuntime Gapを保持する。",
            "exclusive heavy slot取得後にsecurity-004専用Runtimeを再実行する。",
        ],
    }


def main() -> None:
    document = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    print(
        "Core v2 Scenario Plan gap recorded: "
        f"rows={document['denominator']['rows']} open={document['denominator']['scenario_gaps_open']} "
        f"runtime={document['independent_gaps']['dedicated_runtime_reports']}"
    )


if __name__ == "__main__":
    main()
