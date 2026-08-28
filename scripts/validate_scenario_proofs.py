#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Reference System／Scenario Proofの集合、digest、非流用境界を検証する。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/generate_scenario_proofs.py"
BASELINE = ROOT / "baselines/scenario-proof-closure-v1.json"


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


def validate_gap_closure(proof: dict[str, Any]) -> None:
    closure = proof.get("scenario_gap_closure", {})
    required_conditions = {
        "variant_denominator_exhaustive", "exact_surface_scenario_scope", "all_variants_driven",
        "real_argocd_kubernetes_runtime", "retry_zero", "first_attempt_pass", "oracle_pass",
        "source_digest_bound", "harness_digest_bound", "runtime_identity_complete",
        "per_variant_resource_state_artifact", "per_variant_controller_log_artifact",
        "per_variant_metric_artifact", "per_variant_trace_artifact",
        "artifact_paths_dedicated_and_distinct", "integrated_or_other_metadata_reuse_absent",
    }
    conditions = closure.get("conditions", {})
    require(set(conditions) == required_conditions, f"Scenario Closure条件集合が不正です: {proof['id']}")
    artifacts = closure.get("artifacts", {})
    require(set(artifacts) == {"resource_state", "controller_log", "metric", "trace"}, f"Closure専用4 Artifact Channelがありません: {proof['id']}")
    for channel, value in artifacts.items():
        expected_artifact = conditions[f"per_variant_{channel}_artifact"]
        require(value.get("status") == ("artifact" if expected_artifact else "explicit-gap"), f"Closure Artifact状態が条件と一致しません: {proof['id']} {channel}")
        require((value.get("gap") is None) is expected_artifact, f"Closure Artifact gapが不正です: {proof['id']} {channel}")
        if expected_artifact:
            require(bool(value.get("artifacts")), f"Closure Artifact bindingが空です: {proof['id']} {channel}")
    closed = all(conditions.values())
    require(closure.get("scenario_gap_closed") is closed and closure.get("status") == ("closed" if closed else "open"), f"Scenario Closure集計が条件と一致しません: {proof['id']}")
    require(set(closure.get("failed_conditions", [])) == {key for key, value in conditions.items() if not value}, f"Scenario Closure失敗条件が不一致です: {proof['id']}")
    require(closure.get("closure_evidence_source") == "dedicated-surface-scenario-runtime-registry-only", f"Scenario Closure Evidence sourceが不正です: {proof['id']}")
    prohibited = set(closure.get("prohibited_substitutions", []))
    require({"integrated-reference-result", "historical-bundle-evidence", "other-surface-scenario-variant-artifact-metadata", "mock-or-static-runtime"} <= prohibited, f"Scenario Closureの流用禁止条件が不足しています: {proof['id']}")
    if closed:
        require(closure.get("dedicated_runtime_report") and closure.get("dedicated_runtime_record_ids"), f"専用Runtime reportなしでGapを閉じています: {proof['id']}")
        require(closure["variant_contract"]["exhaustive"] is True and bool(closure["variant_contract"]["expected_variant_ids"]), f"全Variant分母なしでGapを閉じています: {proof['id']}")
        require(closure.get("source_bindings") and closure.get("harness_bindings") and closure.get("runtime_identity") and closure.get("oracle_records"), f"Closure bindingが不足しています: {proof['id']}")
    else:
        require(bool(closure.get("failed_conditions")), f"Open Scenario gapに失敗条件がありません: {proof['id']}")


def main() -> None:
    module = load_generator()
    expected_reference, expected_outputs = module.build_all()
    expected_by_path = {path: value for path, value in expected_outputs}
    expected_publish_paths = [module.RESULT.relative_to(module.EVIDENCE_ROOT), *[
        path.relative_to(module.EVIDENCE_ROOT) for path in expected_by_path
    ]]
    publish_manifest = module.validate_publish_manifest(
        module.EVIDENCE_ROOT,
        module.ATOMIC_PUBLISH_MANIFEST.relative_to(module.EVIDENCE_ROOT),
        expected_publish_paths,
    )
    require(publish_manifest["reference"]["commit"] == module.ATOMIC_PUBLISH_REFERENCE["commit"], "Atomic Evidence正本commitが不正です")
    require(publish_manifest["retention_contract"] == {
        "publish_on": "full-run-passed",
        "failed_run": "retain-prior-success",
        "swap": "staged-directory-rename-with-rollback",
        "partial_overwrite": "rejected",
        "mixed_generation": "rejected",
    }, "Atomic Evidence保持契約が不正です")
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
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    proof_ids = sorted(item["id"] for item in index["files"])
    proof_paths = sorted(item["path"] for item in index["files"])
    set_digest = lambda values: "sha256:" + hashlib.sha256(("\n".join(values) + "\n").encode("utf-8")).hexdigest()
    require(baseline["source_commit"] == "9fae2601a019c84bb2af9f7b00621c16a21468bd" and baseline["proof_count"] == len(proof_ids), "Scenario Proof非後退baseline identity／countが不正です")
    require(set_digest(proof_ids) == baseline["proof_id_set_digest"] and set_digest(proof_paths) == baseline["proof_path_set_digest"], "既存Scenario Proof IDまたはpathが削除・置換・集約されています")
    require(index["reference"]["commit"] == "f2e4c4b19156f8e993f48cdcbce23679ad881924", "FE Scenario gap Closure正本commitが不正です")
    require(index["reference"]["files"] == module.FE_REFERENCE["files"], "FE Scenario gap Closure正本file digestが不正です")
    require(index["atomic_publish"]["reference"] == module.ATOMIC_PUBLISH_REFERENCE, "FE Atomic Evidence正本がindexへ接続されていません")
    require(index["atomic_publish"]["retention_contract"] == publish_manifest["retention_contract"], "indexとpublish manifestの保持契約が一致しません")
    variant_contract = module.load_yaml(module.VARIANT_CONTRACT)
    runtime_registry = module.load_yaml(module.RUNTIME_REGISTRY)
    require(variant_contract["reference"]["commit"] == index["reference"]["commit"] and variant_contract["denominator"]["exhaustive"] is False and variant_contract["denominator"]["surface_overrides"] == [], "現行Variant denominatorの未承認境界が不正です")
    require(runtime_registry["reports"] == [] and runtime_registry["status"] == "incomplete-no-dedicated-runtime-reports", "現行専用Runtime registryの0件境界が不正です")
    require(index["source_bindings"]["variant_contract"] == module.binding(module.VARIANT_CONTRACT) and index["source_bindings"]["dedicated_runtime_registry"] == module.binding(module.RUNTIME_REGISTRY), "Variant／専用Runtime contract digestがindexへ接続されていません")
    require(summary["behaviors"] == 100 and summary["scenarios"] == 10 and summary["rows"] == 1000 and summary["dedicated_artifacts"] == 1000, "100 Surface × 10 Scenario分母が不正です")
    require(summary["scenario_gaps_closed"] == 0 and summary["scenario_gaps_open"] == 1000, "専用全Variant RuntimeなしでScenario gapを閉じています")
    require(summary["variant_denominators_exhaustive"] == 0 and summary["dedicated_runtime_reports"] == 0, "未承認Variant分母または存在しない専用Runtime reportを算入しています")
    require(summary["supporting_runtime_artifacts"] + summary["supporting_artifacts"] + summary["no_supporting_artifacts"] == 1000, "補助Evidence分類が分母を閉じていません")
    floor = baseline["supporting_evidence_floor"]
    require(summary["supporting_runtime_artifacts"] >= floor["supporting_runtime_artifacts"] and summary["supporting_runtime_artifacts"] + summary["supporting_artifacts"] >= floor["supporting_artifacts_total"], "既存Supporting Evidenceが非後退floorを下回っています")
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
        require(proof["observation_role"] == "supporting-historical-not-scenario-gap-closure", f"既存観測ArtifactをClosure用と誤分類しています: {proof['id']}")
        require(all(binding["role"] == "supporting-historical-not-scenario-gap-closure" and binding["closure_credit"] is False for binding in proof["evidence_bindings"]), f"既存EvidenceをScenario Closureへ流用しています: {proof['id']}")
        require(proof["supporting_evidence_assessment"]["closure_credit"] is False, f"補助EvidenceにClosure creditがあります: {proof['id']}")
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
        validate_gap_closure(proof)
        supporting_status = proof["supporting_evidence_assessment"]["status"]
        if supporting_status == "supporting-runtime-artifact":
            require(bool(proof["evidence_bindings"]) and proof["closure"]["supporting_real_kubernetes_runtime"] is True and proof["closure"]["supporting_runtime_identity_complete"] is True and proof["controller_kubernetes_behavior"]["component_identity_complete"] is True, f"補助Runtime Artifact分類が不正です: {proof['id']}")
        elif supporting_status == "supporting-artifact":
            require(bool(proof["evidence_bindings"]) and proof["closure"]["supporting_real_kubernetes_runtime"] is True and (proof["closure"]["supporting_runtime_identity_complete"] is False or proof["controller_kubernetes_behavior"]["component_identity_complete"] is False), f"補助Artifact分類が不正です: {proof['id']}")
        else:
            require(supporting_status == "no-supporting-artifact" and proof["evidence_bindings"] == [] and bool(proof["gaps"]), f"補助ArtifactなしのGapが明示されていません: {proof['id']}")
        require(proof["status"] == "scenario-gap-open" and proof["closure"]["scenario_gap_closed"] is False, f"現行専用Runtime 0件でScenario gapを閉じています: {proof['id']}")

    print(
        "Scenario Proof Matrix validated: "
        f"integrated-audit=10/10 integrated-runtime=0 "
        f"rows={summary['rows']} closed={summary['scenario_gaps_closed']} open={summary['scenario_gaps_open']} "
        f"supporting-runtime={summary['supporting_runtime_artifacts']} supporting-artifact={summary['supporting_artifacts']} "
        f"authority-atomic=0 completion=0"
    )


if __name__ == "__main__":
    main()
