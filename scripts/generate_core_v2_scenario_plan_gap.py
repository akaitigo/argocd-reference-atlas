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
    return {
        "schema_version": 1,
        "id": "argocd-core-v2-scenario-plan-gap-v1",
        "status": "incomplete-no-runtime-substitution",
        "core_commit": CORE_COMMIT,
        "inputs": {
            "evidence/scenarios/index.json": digest(INDEX),
            "evidence/scenarios/closure-plan.json": digest(PLAN),
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
            "current_rows_preserved": summary["rows"],
            "coarse_aggregation_forbidden": True,
            "in_place_overwrite_before_migration_proof": False,
        },
        "independent_gaps": {
            "authority_atomic_rows": summary["authority_atomic_bindings"],
            "approved_variant_denominators": summary["variant_denominators_exhaustive"],
            "dedicated_runtime_reports": summary["dedicated_runtime_reports"],
            "completion_eligible_rows": summary["completion_eligible_rows"],
            "integrated_runtime_passed": summary["integrated_runtime_passed"],
            "missing_core_artifacts": missing_files,
        },
        "core_gate_status": {
            "scenario_trace": "blocked-core-schema-migration-and-integrated-runtime-artifacts",
            "scenario_plan": "blocked-pattern-scenario-runtime-report",
            "evidence_durability": "blocked-pattern-scenario-runtime-report",
            "configured_make_check": "passed",
        },
        "runtime_preflight": {
            "state": "blocked-no-dedicated-local-kind-runtime-proof",
            "dedicated_local_kind_required": True,
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
        "human_independent_next_actions": [
            "Core標準Artifactを専用stagingへ加法生成する。",
            "旧row IDから新row IDへの全件Mappingと構造非後退を検証する。",
            "Runtime未実行rowをpattern-specific-gapのまま保持する。",
            "専用local Kindがない間は外部Contextへ接続せずRuntime Gapを保持する。",
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
