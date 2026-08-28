#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Reference System／Scenario Proofの集合、digest、非流用境界を検証する。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/generate_scenario_proofs.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("argocd_scenario_proof_generator", GENERATOR)
    if spec is None or spec.loader is None:
        raise ValueError("Scenario Proof generatorをloadできません")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_observations(module: Any, proof: dict[str, Any]) -> None:
    observations = proof.get("observations", {})
    require(set(observations) == {"resource_state", "controller_log", "metric", "trace"}, f"4観測Channelがありません: {proof['id']}")
    for channel, observation in observations.items():
        require(observation.get("status") in {"artifact", "explicit-gap"}, f"観測状態が不正です: {proof['id']} {channel}")
        if observation["status"] == "artifact":
            require(observation.get("gap") is None and bool(observation.get("artifacts")), f"Artifact観測が空です: {proof['id']} {channel}")
            for artifact in observation["artifacts"]:
                artifact_path = ROOT / artifact["artifact"]["path"]
                require(artifact_path.is_file(), f"観測Artifactがありません: {artifact_path}")
                require(module.binding(artifact_path) == artifact["artifact"], f"観測Artifact digestが不一致です: {proof['id']} {channel}")
                require(bool(artifact.get("json_pointers")), f"観測Artifact locatorがありません: {proof['id']} {channel}")
        else:
            require(observation.get("artifacts") == [] and bool(observation.get("gap")), f"明示gapが不完全です: {proof['id']} {channel}")


def main() -> None:
    module = load_generator()
    expected_reference, expected_outputs = module.build_all()
    expected_by_path = {path: value for path, value in expected_outputs}
    require(module.RESULT.is_file(), "Reference System resultがありません")
    actual_reference = json.loads(module.RESULT.read_text(encoding="utf-8"))
    require(actual_reference == expected_reference, "Reference System resultが入力Evidenceと一致しません")
    require(actual_reference["counts"] == {
        "total": 10,
        "evaluated": 10,
        "bounded_component_evidence": 10,
        "integrated_runtime_passed": 0,
        "single_topology_executed": 0,
        "completion_eligible": 0,
    }, "10 Scenario統合Auditの集計または非Completion境界が不正です")
    require([row["scenario"] for row in actual_reference["tests"]] == module.SCENARIOS, "10 Scenario集合または順序が不正です")
    for row in actual_reference["tests"]:
        require(row["outcome"] == "bounded-evidence-audit" and row["attempts"] == 1 and row["final_status"] == "evaluated" and row["runtime_attempts"] == 0, f"統合AuditのAttempt／Outcome境界が不正です: {row['id']}")
        require(row["single_topology_execution"] is False and row["integrated_runtime_proof"] is False and row["completion_eligible"] is False, f"統合Runtimeを過大主張しています: {row['id']}")
        validate_observations(module, row)
        require(bool(row["gaps"]), f"統合Scenarioの単一Topology gapがありません: {row['id']}")

    actual_files = {path for path in module.PROOF_ROOT.glob("*/*.proof.json")}
    expected_proof_files = {path for path in expected_by_path if path != module.INDEX}
    require(actual_files == expected_proof_files, f"Scenario Proof file集合が不一致です: actual={len(actual_files)} expected={len(expected_proof_files)}")
    for path, expected in expected_by_path.items():
        require(path.is_file(), f"Scenario Proof生成物がありません: {path.relative_to(ROOT)}")
        actual = json.loads(path.read_text(encoding="utf-8"))
        require(actual == expected, f"Scenario Proof生成物が入力またはgeneratorと一致しません: {path.relative_to(ROOT)}")

    index = expected_by_path[module.INDEX]
    summary = index["summary"]
    require(index["reference"]["commit"] == "deadad18b6588d2c907170a451c3b5cea5ea4192", "FE Reference commitが不正です")
    require(summary["behaviors"] == 100 and summary["scenarios"] == 10 and summary["rows"] == 1000 and summary["dedicated_artifacts"] == 1000, "100 Surface × 10 Scenario分母が不正です")
    require(summary["bounded_runtime_proofs"] + summary["bounded_artifact_proofs"] + summary["behavior_specific_gaps"] == 1000, "runtime proof、artifact proof、明示gapが分母を閉じていません")
    require(summary["integrated_scenario_rows"] == 10 and summary["integrated_runtime_passed"] == 0, "統合ScenarioとRuntime成功の分離が不正です")
    require(summary["authority_atomic_bindings"] == 0 and summary["completion_eligible_rows"] == 0, "Authority atomic bindingなしでCompletion eligibleが増えています")

    for path in sorted(expected_proof_files):
        proof = expected_by_path[path]
        require(proof["attempts"] == 1, f"Scenario Proof生成Attemptが不正です: {proof['id']}")
        require(proof["closure"]["dedicated_row"] is True and proof["closure"]["dedicated_artifact"] is True, f"専用row／artifactがありません: {proof['id']}")
        require(proof["authority_binding"]["human_reviewed"] is False and proof["closure"]["authority_atomic_binding"] is False and proof["closure"]["completion_eligible"] is False, f"Authority／Completion境界が不正です: {proof['id']}")
        authority = proof["authority_binding"]
        require(authority.get("status") in {"locked-source-candidate", "explicit-gap"} and bool(authority.get("authority_gap")), f"Authority candidate／gapが不正です: {proof['id']}")
        if authority["status"] == "explicit-gap":
            require(authority["source_id"] is None and authority["source_digest"] is None and authority["locator_scope"] == "local-proof-obligation-not-authority", f"ローカルObligationをAuthorityへ偽装しています: {proof['id']}")
        else:
            require(authority["source_id"] == "argocd-source-tree" and str(authority["source_digest"]).startswith("sha256:"), f"固定Authority Source候補がありません: {proof['id']}")
        integrated = proof["integrated_reference"]
        require(integrated["outcome"] == "bounded-evidence-audit" and integrated["attempts"] == 1 and integrated["final_status"] == "evaluated" and integrated["runtime_attempts"] == 0, f"統合Reference Attempt／Outcomeが不正です: {proof['id']}")
        require(integrated["used_as_behavior_specific_evidence"] is False and integrated["single_topology_execution"] is False, f"統合System成功をBehavior固有Proofへ流用しています: {proof['id']}")
        require(bool(proof["controller_kubernetes_behavior"]["expected_argocd_components"]) and bool(proof["controller_kubernetes_behavior"]["kubernetes_behavior"]), f"Controller／Kubernetes behavior identityがありません: {proof['id']}")
        runtime_identity = proof.get("runtime_identity", {})
        require(runtime_identity.get("status") in {"complete", "partial", "explicit-gap"}, f"Runtime identity状態がありません: {proof['id']}")
        if runtime_identity["status"] == "complete":
            require(bool(runtime_identity["argocd_versions"]) and bool(runtime_identity["kubernetes_api_server_versions"] or runtime_identity["kubernetes_kubelet_versions"]) and runtime_identity["gap"] is None, f"complete Runtime identityが不完全です: {proof['id']}")
        else:
            require(bool(runtime_identity.get("gap")), f"Runtime identity gapが明示されていません: {proof['id']}")
        component_identity = proof["controller_kubernetes_behavior"]
        require(component_identity.get("component_identity_status") in {"complete", "explicit-gap"}, f"Controller identity状態が不正です: {proof['id']}")
        require((component_identity["component_identity_gap"] is None) == component_identity["component_identity_complete"], f"Controller identity gapが不正です: {proof['id']}")
        validate_observations(module, proof)
        if proof["status"] == "bounded-runtime-proof":
            require(bool(proof["evidence_bindings"]) and proof["closure"]["real_kubernetes_runtime"] is True and proof["closure"]["runtime_identity_complete"] is True and proof["controller_kubernetes_behavior"]["component_identity_complete"] is True, f"完全なRuntime／Component identityなしのbounded runtime proofです: {proof['id']}")
        elif proof["status"] == "bounded-artifact-proof":
            require(bool(proof["evidence_bindings"]) and proof["closure"]["real_kubernetes_runtime"] is True and (proof["closure"]["runtime_identity_complete"] is False or proof["controller_kubernetes_behavior"]["component_identity_complete"] is False), f"identity gapなしのbounded artifact proofです: {proof['id']}")
        else:
            require(proof["status"] == "behavior-specific-gap" and proof["evidence_bindings"] == [] and bool(proof["gaps"]), f"Behavior gapが明示されていません: {proof['id']}")

    print(
        "Scenario Proof Matrix validated: "
        f"integrated-audit=10/10 integrated-runtime=0 "
        f"rows={summary['rows']} runtime={summary['bounded_runtime_proofs']} artifact={summary['bounded_artifact_proofs']} "
        f"gaps={summary['behavior_specific_gaps']} authority-atomic=0 completion=0"
    )


if __name__ == "__main__":
    main()
