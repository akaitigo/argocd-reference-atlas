#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Scenario gap Closure evaluatorのpositive／anti-laundering契約を検査する。"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/generate_scenario_proofs.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("argocd_scenario_gap_closure", GENERATOR)
    if spec is None or spec.loader is None:
        raise ValueError("Scenario Proof generatorをloadできません")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fixture() -> tuple[dict, dict]:
    contract = {
        "source": {"path": "definitive/scenario-variant-contract.yaml", "digest": "sha256:test", "bytes": 1},
        "status": "approved-exhaustive",
        "expected_variant_ids": ["manual", "automated"],
        "exhaustive": True,
        "gap": None,
    }
    variants = []
    artifact_kinds = {
        "resource_state": "kubernetes-resource-state",
        "controller_log": "argocd-controller-log",
        "metric": "argocd-prometheus-metric",
        "trace": "scenario-execution-trace",
    }
    for variant_id in contract["expected_variant_ids"]:
        variants.append({
            "variant_id": variant_id,
            "attempts": 1,
            "outcome": "expected",
            "final_status": "passed",
            "error": None,
            "oracle": {"status": "pass", "assertions": ["desired-live-converged"]},
            "source": {"path": f"dedicated/{variant_id}/source", "digest": "sha256:test", "bytes": 1, "owner": f"runtime.test:{variant_id}:source"},
            "harness": {"path": f"dedicated/{variant_id}/harness", "digest": "sha256:test", "bytes": 1, "owner": f"runtime.test:{variant_id}:harness"},
            "artifacts": {channel: {"path": f"dedicated/{variant_id}/{channel}", "kind": artifact_kinds[channel]} for channel in artifact_kinds},
        })
    dedicated = {
        "reference": {"path": "evidence/scenarios/runtime/reports/test.json", "digest": "sha256:test", "bytes": 1},
        "source_verified": True,
        "harness_verified": True,
        "artifact_bindings_verified": True,
        "artifact_paths_distinct": True,
        "report": {
            "id": "runtime.test",
            "surface_id": "application.spec.sync-policy",
            "scenario": "normal",
            "execution": {"retries": 0},
            "runtime_identity": {
                "profile": "cluster",
                "real_argocd_kubernetes_runtime": True,
                "argocd_version": "v3.5.2",
                "kubernetes_api_server_version": "v1.34.1",
                "kubernetes_kubelet_version": "v1.34.0",
                "cluster_uid": "cluster-test",
                "topology_digest": "sha256:test",
                "observed_argocd_components": ["argocd-application-controller", "argocd-repo-server"],
            },
            "variants": variants,
        },
    }
    return contract, dedicated


def main() -> None:
    module = load_generator()
    expected_components = ["argocd-application-controller", "argocd-repo-server"]

    contract, dedicated = fixture()
    positive = module.evaluate_gap_closure("application.spec.sync-policy", "normal", contract, dedicated, expected_components)
    require(positive["scenario_gap_closed"] is True and positive["failed_conditions"] == [], "全Closure条件を満たすpositive fixtureが閉じません")

    mutations = []
    missing_variant = copy.deepcopy(dedicated)
    missing_variant["report"]["variants"].pop()
    mutations.append(("all-variants", contract, missing_variant))
    retry = copy.deepcopy(dedicated)
    retry["report"]["execution"]["retries"] = 1
    mutations.append(("retry-zero", contract, retry))
    attempt = copy.deepcopy(dedicated)
    attempt["report"]["variants"][0]["attempts"] = 2
    mutations.append(("first-attempt", contract, attempt))
    oracle = copy.deepcopy(dedicated)
    oracle["report"]["variants"][0]["oracle"]["status"] = "fail"
    mutations.append(("oracle", contract, oracle))
    source = copy.deepcopy(dedicated)
    source["source_verified"] = False
    mutations.append(("source-digest", contract, source))
    harness = copy.deepcopy(dedicated)
    harness["harness_verified"] = False
    mutations.append(("harness-digest", contract, harness))
    runtime = copy.deepcopy(dedicated)
    runtime["report"]["runtime_identity"]["argocd_version"] = None
    mutations.append(("runtime-identity", contract, runtime))
    mock = copy.deepcopy(dedicated)
    mock["report"]["runtime_identity"]["real_argocd_kubernetes_runtime"] = False
    mutations.append(("mock-runtime", contract, mock))
    scope = copy.deepcopy(dedicated)
    scope["report"]["surface_id"] = "application.spec.sources"
    mutations.append(("surface-scope", contract, scope))
    artifact = copy.deepcopy(dedicated)
    artifact["report"]["variants"][0]["artifacts"].pop("metric")
    mutations.append(("four-artifacts", contract, artifact))
    metadata_reuse = copy.deepcopy(dedicated)
    metadata_reuse["artifact_paths_distinct"] = False
    mutations.append(("metadata-reuse", contract, metadata_reuse))
    pending_contract = copy.deepcopy(contract)
    pending_contract.update({"status": "pending-authority-human-review", "expected_variant_ids": [], "exhaustive": False, "gap": "pending"})
    mutations.append(("variant-denominator", pending_contract, dedicated))

    for name, candidate_contract, candidate_runtime in mutations:
        result = module.evaluate_gap_closure("application.spec.sync-policy", "normal", candidate_contract, candidate_runtime, expected_components)
        require(result["scenario_gap_closed"] is False and bool(result["failed_conditions"]), f"negative fixtureがGapを閉じました: {name}")

    integrated_only = module.evaluate_gap_closure("application.spec.sync-policy", "normal", contract, None, expected_components)
    require(integrated_only["scenario_gap_closed"] is False, "統合結果だけでScenario gapが閉じました")
    metadata_only_rejected = False
    try:
        module.load_dedicated_runtime_reports({"reports": [{"id": "runtime.metadata-only", "path": "evidence/scenarios/runtime/reports/missing.json", "digest": "sha256:missing", "bytes": 1}]})
    except ValueError:
        metadata_only_rejected = True
    require(metadata_only_rejected, "実reportファイルなしのArtifact metadataを受理しました")
    print(f"Scenario gap Closure contract tests passed: positive=1 negative={len(mutations) + 2}")


if __name__ == "__main__":
    main()
