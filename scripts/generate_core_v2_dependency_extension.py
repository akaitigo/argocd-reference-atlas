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
    "harness.core-v2-skill-router": ["scripts/generate_core_v2_skill_router.py", "scripts/test_core_v2_skill_router.py"],
    "harness.core-v2-scenario-plan": ["scripts/generate_core_v2_scenario_plan_gap.py", "scripts/test_core_v2_scenario_plan_gap.py"],
    "harness.core-v2-dependency-extension": ["scripts/generate_core_v2_dependency_extension.py", "scripts/test_core_v2_evidence_dependency_extensions.py"],
}
OUTPUT_PATHS = {
    "evals/definitive-skill-router.json",
    "artifacts/core-v2/scenario-plan-gap.json",
    "artifacts/core-v2/evidence-dependency-extension.json",
}


def pretty(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def validate_extension(graph: dict) -> None:
    inputs = {item["id"]: item for item in graph["inputs"]}
    outputs = {item["path"]: item for item in graph["outputs"]}
    runs = {item["id"]: item for item in graph["runs"]}
    for identifier, members in INPUT_SPECS.items():
        item = inputs.get(identifier)
        if item is None or item["members"] != members or item["baseline_digest"] != item["current_digest"]:
            raise ValueError(f"Core v2 additive input is invalid: {identifier}")
        if item["current_digest"] != contract.aggregate_member_digest(ROOT, members):
            raise ValueError(f"Core v2 additive input digest mismatch: {identifier}")
    if not OUTPUT_PATHS <= set(outputs):
        raise ValueError("Core v2 additive output denominator retreated")
    expected_dependencies = {
        "evals/definitive-skill-router.json": "harness.core-v2-skill-router",
        "artifacts/core-v2/scenario-plan-gap.json": "harness.core-v2-scenario-plan",
        "artifacts/core-v2/evidence-dependency-extension.json": "harness.core-v2-dependency-extension",
    }
    for path, dependency in expected_dependencies.items():
        output = outputs[path]
        if dependency not in output["depends_on"] or output["digest"] != contract.sha256_file(ROOT / path):
            raise ValueError(f"Core v2 output binding is invalid: {path}")
        run = runs.get(output["run_id"])
        if run is None or run["attempts"] != 1 or run["result"] != "passed" or output["id"] not in run["output_ids"]:
            raise ValueError(f"Core v2 first-attempt run is invalid: {path}")


def generate() -> None:
    graph = contract.build_graph()
    base_digest = contract.sha256_bytes(pretty(graph))
    for identifier, members in INPUT_SPECS.items():
        member_digest = contract.aggregate_member_digest(ROOT, members)
        graph["inputs"].append({
            "id": identifier, "kind": "harness", "members": members,
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
    report_id = contract.add_output(
        outputs, "artifacts/core-v2/evidence-dependency-extension.json", "derived-evidence",
        [router_id, plan_id, "harness.core-v2-dependency-extension"],
        "run.core-v2-dependency-extension",
    )
    new_runs = [
        contract.run_document("run.core-v2-skill-router", "derived", "python3 scripts/generate_core_v2_skill_router.py && python3 scripts/test_core_v2_skill_router.py && atlas audit . --gate skill-router", graph["generated_at"], [router_id]),
        contract.run_document("run.core-v2-scenario-plan-gap", "derived", "python3 scripts/generate_core_v2_scenario_plan_gap.py && python3 scripts/test_core_v2_scenario_plan_gap.py", graph["generated_at"], [plan_id]),
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
