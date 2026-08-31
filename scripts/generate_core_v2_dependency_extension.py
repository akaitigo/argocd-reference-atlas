#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Add Core v2 outputs to the dependency graph without changing baseline inputs."""

from __future__ import annotations

import json
from pathlib import Path

import evidence_dependency_graph as contract
import generate_core_standard_artifacts as core_standard


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "evidence" / "dependency-graph.json"
REPORT = ROOT / "artifacts" / "core-v2" / "evidence-dependency-extension.json"
INPUT_SPECS = {
    "source.repository-contract": {
        "kind": "source",
        "members": ["repo.yaml"],
    },
    "source.authority-lock-inventory": {
        "kind": "source",
        "members": ["sources.lock.yaml", "coverage.yaml", "definitive/surface-inventory.yaml", "atlas/claims/index.yaml"],
    },
    "harness.authority-denominator": {
        "kind": "harness",
        "members": [
            "scripts/generate_authority_locators.py",
            "scripts/validate_authority_locators.py",
            "scripts/test_authority_locator_denominator.py",
        ],
    },
    "source.authority-body-baseline": {
        "kind": "source",
        "members": ["baselines/authority-body-inventory-v1.json"],
    },
    "source.authority-human-decisions": {
        "kind": "source",
        "members": ["authority/reviews/decisions.json"],
    },
    "harness.authority-body-review": {
        "kind": "harness",
        "members": [
            "scripts/generate_authority_body_inventory.py",
            "scripts/validate_authority_body_inventory.py",
            "scripts/authority_review_queue.py",
            "scripts/generate_authority_review_queue.py",
            "scripts/validate_authority_review_queue.py",
            "scripts/test_authority_review_queue.py",
        ],
    },
    "harness.content-policy": {
        "kind": "harness",
        "members": ["scripts/validate_non_regression.py", "scripts/test_content_policy_scope.py"],
    },
    "harness.core-v2-skill-router": {
        "kind": "harness",
        "members": ["scripts/generate_core_v2_skill_router.py", "scripts/test_core_v2_skill_router.py"],
    },
    "harness.core-v2-scenario-plan": {
        "kind": "harness",
        "members": ["scripts/generate_core_v2_scenario_plan_gap.py", "scripts/test_core_v2_scenario_plan_gap.py"],
    },
    "harness.core-v2-root-contract-gap": {
        "kind": "harness",
        "members": ["scripts/generate_core_v2_root_contract_gap.py", "scripts/test_core_v2_root_contract_gap.py"],
    },
    "source.core-v2-root-admission-lock": {
        "kind": "source",
        "members": ["contracts/core-v2-root-admission-lock.json"],
    },
    "harness.core-v2-scenario-schema-gap": {
        "kind": "harness",
        "members": ["scripts/generate_core_v2_scenario_schema_gap.py", "scripts/test_core_v2_scenario_schema_gap.py"],
    },
    "source.core-standard-legacy-scenarios": {
        "kind": "source",
        "members": [
            "integrations/reference-system/manifest.yaml",
            "evidence/reference-system/results.json",
            "evidence/scenarios/index.json",
            "evidence/scenarios/runtime/index.yaml",
        ],
    },
    "harness.core-standard-artifacts": {
        "kind": "harness",
        "members": [
            "scripts/generate_core_standard_artifacts.py",
            "scripts/validate_core_standard_artifacts.py",
            "scripts/test_core_standard_artifacts.py",
        ],
    },
    "harness.surface-inventory-readiness": {
        "kind": "harness",
        "members": ["scripts/generate_surface_inventory_readiness.py", "scripts/test_surface_inventory_readiness.py", ".github/workflows/atlas-validate.yml"],
    },
    "harness.root-surface-inventory": {
        "kind": "harness",
        "members": [
            "definitive/root-surface-inventory-bindings.yaml",
            "scripts/generate_root_surface_inventory.py",
            "scripts/test_root_surface_inventory.py",
        ],
    },
    "harness.root-verification-matrix": {
        "kind": "harness",
        "members": [
            "scripts/generate_root_verification_matrix.py",
            "scripts/test_root_verification_matrix.py",
            ".github/workflows/atlas-validate.yml",
        ],
    },
    "source.root-depth-parity": {
        "kind": "source",
        "members": [
            "definitive/argocd-depth-parity.json",
            "authority/FE_DEPTH_REFERENCE.json",
            "depth.parity.yaml",
        ],
    },
    "harness.root-depth-parity": {
        "kind": "harness",
        "members": [
            "scripts/generate_root_depth_parity.py",
            "scripts/test_root_depth_parity.py",
            ".github/workflows/atlas-validate.yml",
        ],
    },
    "harness.core-v2-dependency-extension": {
        "kind": "harness",
        "members": ["scripts/generate_core_v2_dependency_extension.py", "scripts/test_core_v2_evidence_dependency_extensions.py"],
    },
}
AUTHORITY_DRAFT_DENOMINATOR = 26
AUTHORITY_BODY_DRAFT_DENOMINATOR = 26
AUTHORITY_REVIEW_BATCH_DENOMINATOR = 211
AUTHORITY_OUTPUT_PATHS = {
    "authority/extraction.snapshot.json",
    *(path.relative_to(ROOT).as_posix() for path in (ROOT / "authority" / "surfaces-draft").glob("*.json")),
}
AUTHORITY_BODY_OUTPUT_PATHS = {
    "authority/body-inventory.snapshot.json",
    *(path.relative_to(ROOT).as_posix() for path in (ROOT / "authority" / "body-inventory-draft").glob("*.json")),
}
AUTHORITY_REVIEW_BATCH_PATHS = {
    path.relative_to(ROOT).as_posix() for path in (ROOT / "authority" / "review-queue-draft").glob("*.json")
}
AUTHORITY_REVIEW_OUTPUT_PATHS = {"authority/review-queue.snapshot.json", *AUTHORITY_REVIEW_BATCH_PATHS}
AUTHORITY_REVIEW_STATE_OUTPUT_PATHS = AUTHORITY_BODY_OUTPUT_PATHS | AUTHORITY_REVIEW_OUTPUT_PATHS
CORE_V2_OUTPUT_PATHS = {
    "evals/definitive-skill-router.json",
    "artifacts/core-v2/scenario-plan-gap.json",
    "artifacts/core-v2/surface-inventory-readiness.json",
    "artifacts/core-v2/root-surface-inventory-closure.json",
    "artifacts/core-v2/root-verification-matrix-closure.json",
    "artifacts/core-v2/root-depth-parity-closure.json",
    "artifacts/core-v2/root-contract-adapter-gap.json",
    "artifacts/core-v2/scenario-proof-index-schema-gap.json",
    "artifacts/core-v2/evidence-dependency-extension.json",
}
CORE_STANDARD_OUTPUT_PATHS = {path.as_posix() for path in core_standard.output_paths()}
CORE_V2_OUTPUT_PATHS |= CORE_STANDARD_OUTPUT_PATHS
OUTPUT_PATHS = CORE_V2_OUTPUT_PATHS | AUTHORITY_OUTPUT_PATHS | AUTHORITY_REVIEW_STATE_OUTPUT_PATHS


def pretty(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def validate_extension(graph: dict) -> None:
    inputs = {item["id"]: item for item in graph["inputs"]}
    outputs = {item["path"]: item for item in graph["outputs"]}
    runs = {item["id"]: item for item in graph["runs"]}
    if len(AUTHORITY_OUTPUT_PATHS) != AUTHORITY_DRAFT_DENOMINATOR + 1:
        raise ValueError("Authority draft output denominator retreated")
    if len(AUTHORITY_BODY_OUTPUT_PATHS) != AUTHORITY_BODY_DRAFT_DENOMINATOR + 1:
        raise ValueError("Authority body output denominator retreated")
    if len(AUTHORITY_REVIEW_BATCH_PATHS) != AUTHORITY_REVIEW_BATCH_DENOMINATOR or len(AUTHORITY_REVIEW_OUTPUT_PATHS) != AUTHORITY_REVIEW_BATCH_DENOMINATOR + 1:
        raise ValueError("Authority review queue output denominator retreated")
    for identifier, spec in INPUT_SPECS.items():
        item = inputs.get(identifier)
        members = spec["members"]
        if item is None or item["kind"] != spec["kind"] or item["members"] != members or item["baseline_digest"] != item["current_digest"]:
            raise ValueError(f"Core v2 additive input is invalid: {identifier}")
        if item["current_digest"] != contract.aggregate_member_digest(ROOT, members):
            raise ValueError(f"Core v2 additive input digest mismatch: {identifier}")
    if not OUTPUT_PATHS <= set(outputs):
        raise ValueError("Core v2 additive output denominator retreated")
    expected_dependencies = {
        "evals/definitive-skill-router.json": "harness.core-v2-skill-router",
        "artifacts/core-v2/scenario-plan-gap.json": "harness.core-v2-scenario-plan",
        "artifacts/core-v2/surface-inventory-readiness.json": "harness.surface-inventory-readiness",
        "artifacts/core-v2/root-surface-inventory-closure.json": "harness.root-surface-inventory",
        "artifacts/core-v2/root-verification-matrix-closure.json": "harness.root-verification-matrix",
        "artifacts/core-v2/root-depth-parity-closure.json": "harness.root-depth-parity",
        "artifacts/core-v2/root-contract-adapter-gap.json": "harness.core-v2-root-contract-gap",
        "artifacts/core-v2/scenario-proof-index-schema-gap.json": "harness.core-v2-scenario-schema-gap",
        "artifacts/core-v2/evidence-dependency-extension.json": "harness.core-v2-dependency-extension",
    }
    for path, dependency in expected_dependencies.items():
        output = outputs[path]
        if dependency not in output["depends_on"] or output["digest"] != contract.sha256_file(ROOT / path):
            raise ValueError(f"Core v2 output binding is invalid: {path}")
        run = runs.get(output["run_id"])
        if run is None or run["attempts"] != 1 or run["result"] != "passed" or output["id"] not in run["output_ids"]:
            raise ValueError(f"Core v2 first-attempt run is invalid: {path}")
    root_depth = outputs["artifacts/core-v2/root-depth-parity-closure.json"]
    if not {"source.root-depth-parity", "harness.root-depth-parity"} <= set(root_depth["depends_on"]):
        raise ValueError("root depth parity input binding is incomplete")
    root_gap = outputs["artifacts/core-v2/root-contract-adapter-gap.json"]
    root_gap_required_paths = {
        "artifacts/core-v2/root-surface-inventory-closure.json",
        "artifacts/core-v2/root-verification-matrix-closure.json",
        "artifacts/core-v2/root-depth-parity-closure.json",
        "integrations/reference-system/manifest.json",
        "artifacts/reference-system/results.json",
        "artifacts/pattern-scenarios/results.json",
        "migrations/scenario-class-refusal-v1.json",
        "baselines/scenario-row-id-migration-v1.json",
        "evidence/scenarios/index.json",
    }
    root_gap_required = {outputs[path]["id"] for path in root_gap_required_paths} | {
        "source.core-v2-root-admission-lock",
        "harness.core-v2-root-contract-gap",
    }
    if not root_gap_required <= set(root_gap["depends_on"]):
        raise ValueError("root contract gap input binding is incomplete")
    scenario_plan = outputs["artifacts/core-v2/scenario-plan-gap.json"]
    scenario_plan_required_paths = {
        "evidence/scenarios/index.json",
        "evidence/scenarios/closure-plan.json",
        "integrations/reference-system/manifest.json",
        "artifacts/reference-system/results.json",
        "artifacts/pattern-scenarios/results.json",
        "migrations/scenario-class-refusal-v1.json",
        "baselines/scenario-row-id-migration-v1.json",
        "artifacts/core-v2/core-standard-artifacts-publish.json",
    }
    scenario_plan_required = {outputs[path]["id"] for path in scenario_plan_required_paths} | {root_gap["id"], "harness.core-v2-scenario-plan"}
    if not scenario_plan_required <= set(scenario_plan["depends_on"]):
        raise ValueError("Scenario Plan gap stale causes are not fully bound")
    if root_gap["id"] not in scenario_plan["depends_on"]:
        raise ValueError("Scenario Plan gap is not bound to the root contract gap")
    schema_gap = outputs["artifacts/core-v2/scenario-proof-index-schema-gap.json"]
    schema_gap_required_paths = {
        "evidence/scenarios/index.json",
        "integrations/reference-system/manifest.json",
        "artifacts/reference-system/results.json",
        "artifacts/pattern-scenarios/results.json",
        "migrations/scenario-class-refusal-v1.json",
        "baselines/scenario-row-id-migration-v1.json",
    }
    schema_gap_required = {outputs[path]["id"] for path in schema_gap_required_paths} | {"harness.core-v2-scenario-schema-gap"}
    if not schema_gap_required <= set(schema_gap["depends_on"]):
        raise ValueError("Scenario Schema gap input binding is incomplete")
    if schema_gap["id"] not in root_gap["depends_on"]:
        raise ValueError("root contract gap is not bound to the Scenario Schema gap")
    standard_run = runs.get("run.core-standard-artifacts")
    if standard_run is None or standard_run["attempts"] != 1 or standard_run["result"] != "passed":
        raise ValueError("Core standard artifact run binding is invalid")
    for path in CORE_STANDARD_OUTPUT_PATHS:
        output = outputs[path]
        required = {"source.core-standard-legacy-scenarios", "harness.core-standard-artifacts"}
        if not required <= set(output["depends_on"]):
            raise ValueError(f"Core standard output dependency is invalid: {path}")
        if output["run_id"] != standard_run["id"] or output["id"] not in standard_run["output_ids"]:
            raise ValueError(f"Core standard output run binding is invalid: {path}")
        if output["digest"] != contract.sha256_file(ROOT / path):
            raise ValueError(f"Core standard output digest mismatch: {path}")
    authority_run = runs.get("run.authority-denominator")
    if authority_run is None or authority_run["attempts"] != 1 or authority_run["result"] != "passed":
        raise ValueError("Authority denominator first-attempt run is invalid")
    for path in AUTHORITY_OUTPUT_PATHS:
        output = outputs[path]
        required = {"source.authority-lock-inventory", "harness.authority-denominator"}
        if not required <= set(output["depends_on"]):
            raise ValueError(f"Authority output binding is invalid: {path}")
        if output["run_id"] != authority_run["id"] or output["id"] not in authority_run["output_ids"]:
            raise ValueError(f"Authority output run binding is invalid: {path}")
        if output["digest"] != contract.sha256_file(ROOT / path):
            raise ValueError(f"Authority output digest mismatch: {path}")
    body_snapshot = outputs["authority/body-inventory.snapshot.json"]
    body_required = {"source.authority-lock-inventory", "source.authority-body-baseline", "harness.authority-body-review"}
    for path in AUTHORITY_BODY_OUTPUT_PATHS:
        output = outputs[path]
        if not body_required <= set(output["depends_on"]):
            raise ValueError(f"Authority body output binding is invalid: {path}")
        if output["run_id"] != authority_run["id"] or output["id"] not in authority_run["output_ids"] or output["digest"] != contract.sha256_file(ROOT / path):
            raise ValueError(f"Authority body output run/digest binding is invalid: {path}")
    review_required = {body_snapshot["id"], "source.authority-human-decisions", "harness.authority-body-review"}
    for path in AUTHORITY_REVIEW_OUTPUT_PATHS:
        output = outputs[path]
        if not review_required <= set(output["depends_on"]):
            raise ValueError(f"Authority review output binding is invalid: {path}")
        if output["run_id"] != authority_run["id"] or output["id"] not in authority_run["output_ids"] or output["digest"] != contract.sha256_file(ROOT / path):
            raise ValueError(f"Authority review output run/digest binding is invalid: {path}")
    review_snapshot = outputs["authority/review-queue.snapshot.json"]
    review_batch_ids = {outputs[path]["id"] for path in AUTHORITY_REVIEW_BATCH_PATHS}
    if not review_batch_ids <= set(review_snapshot["depends_on"]):
        raise ValueError("Authority review snapshot is not bound to every review batch")
    root_inventory = outputs["artifacts/core-v2/root-surface-inventory-closure.json"]
    root_inventory_required = {body_snapshot["id"], review_snapshot["id"], "source.authority-human-decisions"}
    if not root_inventory_required <= set(root_inventory["depends_on"]):
        raise ValueError("root Surface Inventory stale causes are not fully bound")
    root_matrix = outputs["artifacts/core-v2/root-verification-matrix-closure.json"]
    if not {review_snapshot["id"], outputs["evidence/scenarios/closure-plan.json"]["id"], "source.authority-human-decisions"} <= set(root_matrix["depends_on"]):
        raise ValueError("root Verification Matrix stale causes are not fully bound")
    report = outputs["artifacts/core-v2/evidence-dependency-extension.json"]
    if "source.repository-contract" not in report["depends_on"]:
        raise ValueError("Repository contract is not connected to the extension report")
    if "harness.content-policy" not in report["depends_on"]:
        raise ValueError("Content policy harness is not connected to the extension report")


def generate() -> None:
    graph = contract.build_graph()
    base_digest = contract.sha256_bytes(pretty(graph))
    for identifier, spec in INPUT_SPECS.items():
        members = spec["members"]
        member_digest = contract.aggregate_member_digest(ROOT, members)
        graph["inputs"].append({
            "id": identifier, "kind": spec["kind"], "members": members,
            "baseline_digest": member_digest, "current_digest": member_digest,
            "observed_at": graph["generated_at"],
        })

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "id": "argocd-evidence-dependency-core-v2-extension-v1",
        "status": "current-additive-extension",
        "core_commit": "072d7ca77981f51754e824d70c6d4ecd55ea67e5",
        "base_graph_digest": base_digest,
        "baseline_input_mutations": 0,
        "added_input_ids": sorted(INPUT_SPECS),
        "added_output_paths": sorted(OUTPUT_PATHS),
        "policy": {
            "monotonic_addition": True,
            "first_attempt_required": True,
            "fixture_runtime_substitution_forbidden": True,
        },
    }
    REPORT.write_bytes(pretty(report))

    outputs = graph["outputs"]
    output_by_path = {item["path"]: item["id"] for item in outputs}
    standard_dependencies = ["source.core-standard-legacy-scenarios", "harness.core-standard-artifacts", "profile.local"]
    standard_ids: dict[str, str] = {}
    gap_paths = {
        core_standard.gap_path(scenario, kind).as_posix()
        for scenario in core_standard.CORE_SCENARIOS
        for kind in ("trace", "screenshot")
    }
    for path in sorted(gap_paths):
        standard_ids[path] = contract.add_output(outputs, path, "derived-evidence", standard_dependencies, "run.core-standard-artifacts")
    manifest_path = core_standard.MANIFEST.as_posix()
    standard_ids[manifest_path] = contract.add_output(outputs, manifest_path, "derived-evidence", standard_dependencies, "run.core-standard-artifacts")
    reference_path = core_standard.REFERENCE_RESULTS.as_posix()
    standard_ids[reference_path] = contract.add_output(
        outputs, reference_path, "derived-evidence",
        [standard_ids[manifest_path], *[standard_ids[path] for path in sorted(gap_paths)], *standard_dependencies],
        "run.core-standard-artifacts",
    )
    pattern_path = core_standard.PATTERN_RESULTS.as_posix()
    standard_ids[pattern_path] = contract.add_output(
        outputs, pattern_path, "derived-evidence",
        [output_by_path["evidence/scenarios/index.json"], output_by_path["evidence/scenarios/runtime/index.yaml"], *standard_dependencies],
        "run.core-standard-artifacts",
    )
    migration_path = core_standard.MIGRATION.as_posix()
    standard_ids[migration_path] = contract.add_output(
        outputs, migration_path, "derived-evidence",
        [output_by_path["evidence/scenarios/index.json"], *standard_dependencies],
        "run.core-standard-artifacts",
    )
    baseline_path = core_standard.BASELINE.as_posix()
    standard_ids[baseline_path] = contract.add_output(
        outputs, baseline_path, "derived-evidence",
        [standard_ids[migration_path], *standard_dependencies],
        "run.core-standard-artifacts",
    )
    publish_path = core_standard.PUBLISH_MANIFEST.as_posix()
    standard_ids[publish_path] = contract.add_output(
        outputs, publish_path, "derived-evidence",
        [*standard_ids.values(), *standard_dependencies],
        "run.core-standard-artifacts",
    )
    scenario_schema_gap_id = contract.add_output(
        outputs, "artifacts/core-v2/scenario-proof-index-schema-gap.json", "closure-plan",
        [
            output_by_path["evidence/scenarios/index.json"],
            standard_ids[manifest_path], standard_ids[reference_path], standard_ids[pattern_path],
            standard_ids[migration_path], standard_ids[baseline_path],
            "harness.core-v2-scenario-schema-gap",
        ],
        "run.core-v2-scenario-schema-gap",
    )
    router_id = contract.add_output(
        outputs, "evals/definitive-skill-router.json", "skill-eval",
        [output_by_path["evals/argocd-atlas-router.definitive-skill-eval.json"], "harness.core-v2-skill-router", "source.project-policy", "profile.local"],
        "run.core-v2-skill-router",
    )
    authority_ids = [
        contract.add_output(
            outputs, path, "derived-evidence",
            ["source.authority-lock-inventory", "harness.authority-denominator"],
            "run.authority-denominator",
        )
        for path in sorted(AUTHORITY_OUTPUT_PATHS)
    ]
    body_ids = [
        contract.add_output(
            outputs, path, "derived-evidence",
            ["source.authority-lock-inventory", "source.authority-body-baseline", "harness.authority-body-review"],
            "run.authority-denominator",
        )
        for path in sorted(AUTHORITY_BODY_OUTPUT_PATHS)
    ]
    body_snapshot_id = next(outputs_item["id"] for outputs_item in outputs if outputs_item["path"] == "authority/body-inventory.snapshot.json")
    review_batch_ids = [
        contract.add_output(
            outputs, path, "derived-evidence",
            [body_snapshot_id, "source.authority-human-decisions", "harness.authority-body-review"],
            "run.authority-denominator",
        )
        for path in sorted(AUTHORITY_REVIEW_BATCH_PATHS)
    ]
    review_snapshot_id = contract.add_output(
        outputs, "authority/review-queue.snapshot.json", "derived-evidence",
        [*review_batch_ids, body_snapshot_id, "source.authority-human-decisions", "harness.authority-body-review"],
        "run.authority-denominator",
    )
    readiness_id = contract.add_output(
        outputs, "artifacts/core-v2/surface-inventory-readiness.json", "derived-evidence",
        [*authority_ids, "source.authority-lock-inventory", "harness.surface-inventory-readiness"],
        "run.surface-inventory-readiness",
    )
    root_inventory_id = contract.add_output(
        outputs, "artifacts/core-v2/root-surface-inventory-closure.json", "closure-plan",
        [readiness_id, output_by_path["evidence/scenarios/index.json"], body_snapshot_id, review_snapshot_id, "source.authority-human-decisions", "source.authority-lock-inventory", "harness.root-surface-inventory"],
        "run.root-surface-inventory-closure",
    )
    root_matrix_id = contract.add_output(
        outputs, "artifacts/core-v2/root-verification-matrix-closure.json", "closure-plan",
        [root_inventory_id, output_by_path["evidence/scenarios/index.json"], output_by_path["evidence/scenarios/closure-plan.json"], review_snapshot_id, "source.authority-human-decisions", "source.authority-lock-inventory", "harness.root-verification-matrix"],
        "run.root-verification-matrix-closure",
    )
    root_depth_id = contract.add_output(
        outputs, "artifacts/core-v2/root-depth-parity-closure.json", "closure-plan",
        ["source.root-depth-parity", output_by_path["evidence/scenarios/index.json"], "harness.root-depth-parity"],
        "run.root-depth-parity-closure",
    )
    root_contract_gap_id = contract.add_output(
        outputs, "artifacts/core-v2/root-contract-adapter-gap.json", "closure-plan",
        [
            root_inventory_id, root_matrix_id, root_depth_id,
            standard_ids[manifest_path], standard_ids[reference_path], standard_ids[pattern_path],
            standard_ids[migration_path], standard_ids[baseline_path],
            scenario_schema_gap_id,
            output_by_path["evidence/scenarios/index.json"],
            "source.core-v2-root-admission-lock",
            "harness.core-v2-root-contract-gap",
        ],
        "run.core-v2-root-contract-gap",
    )
    plan_id = contract.add_output(
        outputs, "artifacts/core-v2/scenario-plan-gap.json", "closure-plan",
        [
            output_by_path["evidence/scenarios/index.json"],
            output_by_path["evidence/scenarios/closure-plan.json"],
            standard_ids[manifest_path],
            standard_ids[reference_path],
            standard_ids[pattern_path],
            standard_ids[migration_path],
            standard_ids[baseline_path],
            standard_ids[publish_path],
            root_contract_gap_id,
            "harness.core-v2-scenario-plan",
        ],
        "run.core-v2-scenario-plan-gap",
    )
    report_id = contract.add_output(
        outputs, "artifacts/core-v2/evidence-dependency-extension.json", "derived-evidence",
        [router_id, plan_id, readiness_id, root_inventory_id, root_matrix_id, root_depth_id, root_contract_gap_id, standard_ids[publish_path], *authority_ids, *body_ids, *review_batch_ids, review_snapshot_id, "source.repository-contract", "harness.content-policy", "harness.core-v2-dependency-extension"],
        "run.core-v2-dependency-extension",
    )
    new_runs = [
        contract.run_document("run.core-standard-artifacts", "derived", "make core-standard-artifacts", graph["generated_at"], list(standard_ids.values())),
        contract.run_document("run.core-v2-skill-router", "derived", "python3 scripts/generate_core_v2_skill_router.py && python3 scripts/test_core_v2_skill_router.py && atlas audit . --gate skill-router", graph["generated_at"], [router_id]),
        contract.run_document("run.core-v2-scenario-schema-gap", "derived", "make scenario-proof-index-adapter", graph["generated_at"], [scenario_schema_gap_id]),
        contract.run_document("run.core-v2-root-contract-gap", "derived", "make root-contract-adapter-gap", graph["generated_at"], [root_contract_gap_id]),
        contract.run_document("run.core-v2-scenario-plan-gap", "derived", "make core-v2-scenario-plan-gap", graph["generated_at"], [plan_id]),
        contract.run_document("run.authority-denominator", "derived", "make authority-locators && make authority-validate", graph["generated_at"], [*authority_ids, *body_ids, *review_batch_ids, review_snapshot_id]),
        contract.run_document("run.surface-inventory-readiness", "derived", "python3 scripts/generate_surface_inventory_readiness.py && python3 scripts/test_surface_inventory_readiness.py", graph["generated_at"], [readiness_id]),
        contract.run_document("run.root-surface-inventory-closure", "derived", "python3 scripts/generate_root_surface_inventory.py && python3 scripts/test_root_surface_inventory.py", graph["generated_at"], [root_inventory_id]),
        contract.run_document("run.root-verification-matrix-closure", "derived", "python3 scripts/generate_root_verification_matrix.py && python3 scripts/test_root_verification_matrix.py", graph["generated_at"], [root_matrix_id]),
        contract.run_document("run.root-depth-parity-closure", "derived", "python3 scripts/generate_root_depth_parity.py && python3 scripts/test_root_depth_parity.py", graph["generated_at"], [root_depth_id]),
        contract.run_document("run.core-v2-dependency-extension", "derived", "python3 scripts/generate_core_v2_dependency_extension.py && python3 scripts/test_core_v2_evidence_dependency_extensions.py", graph["generated_at"], [report_id]),
    ]
    graph["runs"].extend(new_runs)
    graph["outputs"] = sorted(outputs, key=lambda item: item["path"])
    graph["required_outputs"] = sorted(item["path"] for item in outputs)
    graph["runs"] = sorted(graph["runs"], key=lambda item: item["id"])

    input_map = {item["id"]: item for item in graph["inputs"]}
    output_map = {item["id"]: item for item in graph["outputs"]}
    for run in new_runs:
        ancestors: set[str] = set()
        for output_id in run["output_ids"]:
            ancestors |= contract.input_ancestors(output_id, output_map, set(input_map))
        run["input_bindings"] = [
            {"input_id": identifier, "digest": input_map[identifier]["current_digest"]}
            for identifier in sorted(ancestors)
        ]

    contract.atomic_write(GRAPH, pretty(graph))
    contract.validate_graph(ROOT, graph)
    validate_extension(graph)
    print(f"Core v2 dependency extension generated: inputs={len(graph['inputs'])} outputs={len(graph['outputs'])} runs={len(graph['runs'])}")


if __name__ == "__main__":
    generate()
