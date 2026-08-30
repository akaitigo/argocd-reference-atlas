#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Add Core v2 outputs to the dependency graph without changing baseline inputs."""

from __future__ import annotations

import json
from pathlib import Path

import evidence_dependency_graph as contract


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
    "harness.surface-inventory-readiness": {
        "kind": "harness",
        "members": ["scripts/generate_surface_inventory_readiness.py", "scripts/test_surface_inventory_readiness.py"],
    },
    "harness.core-v2-dependency-extension": {
        "kind": "harness",
        "members": ["scripts/generate_core_v2_dependency_extension.py", "scripts/test_core_v2_evidence_dependency_extensions.py"],
    },
}
AUTHORITY_DRAFT_DENOMINATOR = 26
AUTHORITY_OUTPUT_PATHS = {
    "authority/extraction.snapshot.json",
    *(path.relative_to(ROOT).as_posix() for path in (ROOT / "authority" / "surfaces-draft").glob("*.json")),
}
CORE_V2_OUTPUT_PATHS = {
    "evals/definitive-skill-router.json",
    "artifacts/core-v2/scenario-plan-gap.json",
    "artifacts/core-v2/surface-inventory-readiness.json",
    "artifacts/core-v2/evidence-dependency-extension.json",
}
OUTPUT_PATHS = CORE_V2_OUTPUT_PATHS | AUTHORITY_OUTPUT_PATHS


def pretty(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def validate_extension(graph: dict) -> None:
    inputs = {item["id"]: item for item in graph["inputs"]}
    outputs = {item["path"]: item for item in graph["outputs"]}
    runs = {item["id"]: item for item in graph["runs"]}
    if len(AUTHORITY_OUTPUT_PATHS) != AUTHORITY_DRAFT_DENOMINATOR + 1:
        raise ValueError("Authority draft output denominator retreated")
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
        "artifacts/core-v2/evidence-dependency-extension.json": "harness.core-v2-dependency-extension",
    }
    for path, dependency in expected_dependencies.items():
        output = outputs[path]
        if dependency not in output["depends_on"] or output["digest"] != contract.sha256_file(ROOT / path):
            raise ValueError(f"Core v2 output binding is invalid: {path}")
        run = runs.get(output["run_id"])
        if run is None or run["attempts"] != 1 or run["result"] != "passed" or output["id"] not in run["output_ids"]:
            raise ValueError(f"Core v2 first-attempt run is invalid: {path}")
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
    router_id = contract.add_output(
        outputs, "evals/definitive-skill-router.json", "skill-eval",
        [output_by_path["evals/argocd-atlas-router.definitive-skill-eval.json"], "harness.core-v2-skill-router", "source.project-policy", "profile.local"],
        "run.core-v2-skill-router",
    )
    plan_id = contract.add_output(
        outputs, "artifacts/core-v2/scenario-plan-gap.json", "closure-plan",
        [output_by_path["evidence/scenarios/index.json"], output_by_path["evidence/scenarios/closure-plan.json"], "harness.core-v2-scenario-plan"],
        "run.core-v2-scenario-plan-gap",
    )
    authority_ids = [
        contract.add_output(
            outputs, path, "derived-evidence",
            ["source.authority-lock-inventory", "harness.authority-denominator"],
            "run.authority-denominator",
        )
        for path in sorted(AUTHORITY_OUTPUT_PATHS)
    ]
    readiness_id = contract.add_output(
        outputs, "artifacts/core-v2/surface-inventory-readiness.json", "derived-evidence",
        [*authority_ids, "source.authority-lock-inventory", "harness.surface-inventory-readiness"],
        "run.surface-inventory-readiness",
    )
    report_id = contract.add_output(
        outputs, "artifacts/core-v2/evidence-dependency-extension.json", "derived-evidence",
        [router_id, plan_id, readiness_id, *authority_ids, "source.repository-contract", "harness.content-policy", "harness.core-v2-dependency-extension"],
        "run.core-v2-dependency-extension",
    )
    new_runs = [
        contract.run_document("run.core-v2-skill-router", "derived", "python3 scripts/generate_core_v2_skill_router.py && python3 scripts/test_core_v2_skill_router.py && atlas audit . --gate skill-router", graph["generated_at"], [router_id]),
        contract.run_document("run.core-v2-scenario-plan-gap", "derived", "python3 scripts/generate_core_v2_scenario_plan_gap.py && python3 scripts/test_core_v2_scenario_plan_gap.py", graph["generated_at"], [plan_id]),
        contract.run_document("run.authority-denominator", "derived", "make authority-locators && make authority-validate", graph["generated_at"], authority_ids),
        contract.run_document("run.surface-inventory-readiness", "derived", "python3 scripts/generate_surface_inventory_readiness.py && python3 scripts/test_surface_inventory_readiness.py", graph["generated_at"], [readiness_id]),
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
