#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""10 Scenario統合AuditとSurface固有Scenario Proofを決定論的に生成する。"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "integrations/reference-system/manifest.yaml"
INVENTORY = ROOT / "definitive/surface-inventory.yaml"
SOURCES = ROOT / "sources.lock.yaml"
ENVIRONMENT_LOCK = ROOT / "environments/kind/argocd-v3.5.2.lock"
RESULT = ROOT / "evidence/reference-system/results.json"
PROOF_ROOT = ROOT / "evidence/scenarios/behaviors"
INDEX = ROOT / "evidence/scenarios/index.json"
VALIDATOR = ROOT / "scripts/validate_scenario_proofs.py"
SCENARIOS = ["normal", "boundary", "rejection", "failure", "recovery", "migration", "operations", "security", "performance", "compatibility"]
FE_REFERENCE = {
    "repository": "frontend-behavior-atlas",
    "commit": "deadad18b6588d2c907170a451c3b5cea5ea4192",
    "files": {
        "docs/REFERENCE_SYSTEM.md": "sha256:3e751a7394fa79ad805cf229d053311fbdee86bdfc7efc0e89542999d45e7d1c",
        "docs/DEFINITIVE_GATE_V2_REFERENCE.md": "sha256:6c8bb8d45a66b7595f22a23596cfa0ab495a4fd593740d9dab6ce138e4d4af89",
        "scripts/lib/scenario-proof.ts": "sha256:e8ac9f30fef762be5ff37826e357a195faafb411cd7c0803126e27b1792d2bfa",
        "scripts/generate-scenario-proofs.ts": "sha256:4b095074665cec1c66c80948baaafaaafeef31919b3afa6c3064681d7a951241",
        "scripts/verify-scenario-proofs.ts": "sha256:2ebe02b5400dce8cbb8d022d35b90c921fedfc6be9af29ca795f1e4b323f9dda",
        "scripts/test-scenario-proofs.ts": "sha256:fdfa98248b9ede97e8aa406a97b1020643d46ce29d31629f833ced8998f295f6",
        "scripts/verify-reference-system-evidence.ts": "sha256:0f356e451128294789d7bc6f8b343bc85940258cb612b710d775a7674e10f66c",
    },
}

EVIDENCE_SCENARIOS = {
    "evidence.application.v3-5-2": {"normal"},
    "evidence.applicationset.v3-5-2": {"normal", "boundary", "recovery"},
    "evidence.reconciliation.v3-5-2": {"normal", "failure", "recovery"},
    "evidence.sync.v3-5-2": {"normal", "boundary", "operations"},
    "evidence.operations.v3-5-2": {"normal", "operations"},
    "evidence.access-boundary.v3-5-2": {"boundary", "rejection", "failure", "recovery", "security"},
    "evidence.connection.v3-5-2": {"normal", "boundary", "rejection", "failure", "security"},
    "evidence.auto-recovery.v3-5-2": {"failure", "recovery"},
    "evidence.hook-wave.v3-5-2": {"normal", "boundary", "failure", "operations"},
    "evidence.diff.v3-5-2": {"normal", "boundary", "rejection", "operations"},
    "evidence.health.v3-5-2": {"normal", "failure", "recovery"},
    "evidence.drift.v3-5-2": {"boundary", "failure", "recovery", "operations"},
    "evidence.security.v3-5-2": {"rejection", "security"},
    "evidence.high-availability.v3-5-2": {"failure", "recovery", "operations"},
    "evidence.observability.v3-5-2": {"normal", "failure", "recovery", "operations"},
    "evidence.recovery.v3-5-2": {"recovery", "migration", "operations", "security"},
    "evidence.failure.v3-5-2": {"failure", "recovery"},
    "evidence.upgrade-migration.v3-5-2": {"migration", "compatibility"},
    "evidence.notifications.v3-5-2": {"normal", "failure", "recovery", "operations", "security"},
}


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Object YAMLではありません: {path.relative_to(ROOT)}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Object JSONではありません: {path.relative_to(ROOT)}")
    return value


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def binding(path: Path) -> dict[str, Any]:
    return {"path": path.relative_to(ROOT).as_posix(), "digest": sha256_file(path), "bytes": path.stat().st_size}


def pointer(path: list[str]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in path)


def channel_pointers(value: Any) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {"resource_state": [], "controller_log": [], "metric": [], "trace": []}
    resource_keys = {"application", "applications", "applicationsets", "resources", "workloads", "projects", "pods", "nodes", "deployments", "state", "status", "operationstate"}

    def walk(node: Any, path: list[str]) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = [*path, str(key)]
                lowered = str(key).lower().replace("_", "")
                nonempty = child not in ({}, [], "", None)
                if nonempty and lowered in resource_keys:
                    found["resource_state"].append(pointer(child_path))
                raw_key = str(key).lower()
                if nonempty and (lowered in {"log", "logs", "controllerlog", "controllerlogs", "componentlog", "componentlogs"} or raw_key.endswith("_log") or raw_key.endswith("_logs")):
                    found["controller_log"].append(pointer(child_path))
                if nonempty and "metric" in lowered:
                    found["metric"].append(pointer(child_path))
                if nonempty and (lowered == "trace" or lowered.endswith("trace")):
                    found["trace"].append(pointer(child_path))
                walk(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node[:20]):
                walk(child, [*path, str(index)])

    walk(value, [])
    return {key: sorted(set(paths))[:8] for key, paths in found.items()}


def component_contract(item: dict[str, Any]) -> tuple[list[str], str]:
    item_id = item["id"]
    area = item["area"]
    if area == "applicationset":
        return ["argocd-applicationset-controller"], "applicationset-custom-resource-reconciliation"
    if area == "notifications":
        return ["argocd-notifications-controller"], "notification-subscription-reconciliation"
    if area in {"application", "sync", "diff", "health", "drift"}:
        return ["argocd-application-controller", "argocd-repo-server"], "application-custom-resource-reconciliation"
    if area in {"project", "auth"}:
        return ["argocd-server", "argocd-application-controller"], "authorization-and-project-boundary"
    if area == "connection":
        return ["argocd-server", "argocd-repo-server", "argocd-application-controller"], "secret-backed-repository-cluster-connection"
    if area in {"secret-boundary", "extensions"}:
        return ["argocd-repo-server", "argocd-server"], "secret-reference-and-extension-isolation"
    if area == "availability":
        if item_id == "ha.redis":
            return ["redis-ha"], "stateful-leader-replacement"
        if item_id == "ha.applicationset-controller":
            return ["argocd-applicationset-controller"], "deployment-replica-failover"
        if item_id == "ha.api-server":
            return ["argocd-server"], "deployment-replica-failover"
        return ["argocd-application-controller", "argocd-repo-server"], "controller-pod-replacement-and-sharding"
    if area == "observability":
        return ["argocd-application-controller", "argocd-server", "argocd-repo-server"], "component-telemetry-emission"
    if area == "recovery":
        return ["argocd-application-controller", "argocd-server", "argocd-repo-server", "redis-ha"], "failure-detection-and-state-recovery"
    if area in {"migration", "compatibility"}:
        return ["argocd-application-controller", "argocd-server", "argocd-repo-server"], "crd-and-controller-version-transition"
    if area == "performance":
        return ["argocd-application-controller", "argocd-repo-server"], "controller-queue-and-resource-capacity"
    return ["argocd-application-controller", "argocd-server", "argocd-repo-server", "argocd-applicationset-controller", "argocd-notifications-controller"], "cross-controller-gitops-integration"


def evidence_data(evidence_id: str) -> dict[str, Any]:
    record_path = ROOT / "evidence/records" / f"{evidence_id}.evidence.yaml"
    record = load_yaml(record_path)
    artifact_path = ROOT / record["artifact"]["uri"]
    artifact = load_json(artifact_path)
    artifact_matches = (
        sha256_file(artifact_path) == record["artifact"]["digest"]
        and artifact_path.stat().st_size == record["artifact"]["size_bytes"]
    )
    raw_text = artifact_path.read_text(encoding="utf-8")
    api_versions = sorted(set(re.findall(r'"gitVersion"\s*:\s*"(v1\.[0-9]+\.[0-9]+)"', raw_text)))
    node_versions = sorted(set(re.findall(r'"kubeletVersion"\s*:\s*"(v1\.[0-9]+\.[0-9]+)"', raw_text)))
    lock_match = re.search(r"kindest/node:(v1\.[0-9]+\.[0-9]+)@sha256:([0-9a-f]{64})", ENVIRONMENT_LOCK.read_text(encoding="utf-8"))
    node_image = lock_match.group(1) if lock_match else None
    expected_components: set[str] = set()
    for token, component in {
        "argocd-application-controller": "argocd-application-controller",
        "argocd-applicationset-controller": "argocd-applicationset-controller",
        "argocd-notifications-controller": "argocd-notifications-controller",
        "argocd-repo-server": "argocd-repo-server",
        "argocd-server": "argocd-server",
        "redis-ha": "redis-ha",
    }.items():
        if token in raw_text:
            expected_components.add(component)
    return {
        "id": evidence_id,
        "record": record,
        "record_binding": binding(record_path),
        "artifact_value": artifact,
        "artifact_binding": binding(artifact_path),
        "artifact_matches_record": artifact_matches,
        "channels": channel_pointers(artifact),
        "runtime_identity": {
            "profile": record["environment"].get("profile"),
            "producer": record.get("producer"),
            "command": record.get("command"),
            "manifest_digest": record["environment"].get("manifest_digest"),
            "cluster_name": record["environment"].get("cluster_name"),
            "kubernetes_context": record["environment"].get("kubernetes_context"),
            "argocd_version": record["environment"].get("argocd_version"),
            "kubernetes_api_server_versions": api_versions,
            "kubernetes_kubelet_versions": node_versions,
            "kubernetes_node_image_version": node_image,
            "kubernetes_environment_lock": binding(ENVIRONMENT_LOCK),
            "observed_components": sorted(expected_components),
            "real_kubernetes_runtime": record["environment"].get("profile") == "cluster" and artifact_matches,
            "version_identity_complete": bool(record["environment"].get("argocd_version") and (api_versions or node_versions)),
        },
    }


def observation(channel: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = []
    for item in evidence:
        pointers = item["channels"][channel]
        if pointers:
            artifacts.append({
                "evidence_id": item["id"],
                "artifact": item["artifact_binding"],
                "json_pointers": pointers,
            })
    if artifacts:
        kinds = {
            "resource_state": "resource-state-json",
            "controller_log": "controller-log",
            "metric": "metric-sample",
            "trace": "structured-lab-trace-not-otlp",
        }
        return {"status": "artifact", "artifact_kind": kinds[channel], "artifacts": artifacts, "gap": None}
    labels = {
        "resource_state": "Behavior固有resource state Artifactがない。",
        "controller_log": "Behavior固有controller log Artifactがない。",
        "metric": "Behavior固有metric Artifactがない。",
        "trace": "Behavior固有trace Artifactがない。OTLP traceは別Gapとして未Closure。",
    }
    return {"status": "explicit-gap", "artifact_kind": None, "artifacts": [], "gap": labels[channel]}


def build_reference_result(manifest: dict[str, Any], evidence_cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for scenario in manifest["scenarios"]:
        bound = [evidence_cache[evidence_id] for evidence_id in scenario["evidence_ids"]]
        checks_pass = all(item["artifact_matches_record"] and item["record"]["verdict"] == "pass" for item in bound)
        observations = {channel: observation(channel, bound) for channel in ("resource_state", "controller_log", "metric", "trace")}
        gaps = ["single-topology-runtime-execution-not-performed"]
        if observations["trace"]["status"] == "explicit-gap":
            gaps.append("scenario-specific-trace-not-captured")
        if scenario["id"] == "performance":
            gaps.append("capacity-benchmark-and-regression-baseline-missing")
        if scenario["id"] == "compatibility":
            gaps.append("broad-argocd-kubernetes-version-matrix-missing")
        rows.append({
            "id": f"reference.scenario.{scenario['id']}",
            "scenario": scenario["id"],
            "execution": "offline-bound-evidence-integration",
            "outcome": "bounded-evidence-audit" if checks_pass else "invalid-evidence-binding",
            "attempts": 1,
            "final_status": "evaluated" if checks_pass else "failed",
            "runtime_attempts": 0,
            "status": "bounded-component-evidence" if checks_pass else "invalid-evidence-binding",
            "component_evidence_ids": scenario["evidence_ids"],
            "controller_components": scenario["controller_components"],
            "kubernetes_behaviors": scenario["kubernetes_behaviors"],
            "assertions": scenario["assertions"],
            "runtime_identities": [item["runtime_identity"] for item in bound],
            "artifact_bindings": [item["artifact_binding"] for item in bound],
            "observations": observations,
            "single_topology_execution": False,
            "integrated_runtime_proof": False,
            "completion_eligible": False,
            "gaps": gaps,
        })
    return {
        "schema_version": 1,
        "id": manifest["id"],
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "status": "incomplete-single-topology-runtime-and-authority-atomic",
        "reference": FE_REFERENCE,
        "execution": {
            "command": "make scenario-proofs",
            "mode": "offline-bound-evidence-integration",
            "scenario_order": SCENARIOS,
            "source_bindings": {
                "manifest": binding(MANIFEST),
                "surface_inventory": binding(INVENTORY),
                "sources_lock": binding(SOURCES),
                "environment_lock": binding(ENVIRONMENT_LOCK),
                "generator": binding(Path(__file__).resolve()),
            },
        },
        "counts": {
            "total": len(rows),
            "evaluated": len(rows),
            "bounded_component_evidence": sum(item["status"] == "bounded-component-evidence" for item in rows),
            "integrated_runtime_passed": 0,
            "single_topology_executed": 0,
            "completion_eligible": 0,
        },
        "tests": rows,
        "completion_limits": manifest["completion_limits"],
    }


def build_proof(
    item: dict[str, Any],
    scenario: str,
    item_evidence: dict[str, list[str]],
    evidence_cache: dict[str, dict[str, Any]],
    source: dict[str, Any],
    reference_result: dict[str, Any],
    reference_digest: str,
) -> dict[str, Any]:
    candidate_ids = item_evidence.get(item["id"], [])
    evidence_ids = [
        evidence_id for evidence_id in candidate_ids
        if scenario in EVIDENCE_SCENARIOS.get(evidence_id, set()) and item["state"] != "missing"
    ]
    bound = [evidence_cache[evidence_id] for evidence_id in evidence_ids]
    components, kubernetes_behavior = component_contract(item)
    local_obligation = item["kind"].endswith("obligation") or item["locator"].startswith(("definitive/", "labs/"))
    observations = {channel: observation(channel, bound) for channel in ("resource_state", "controller_log", "metric", "trace")}
    runtime_identities = [data["runtime_identity"] for data in bound]
    runtime_identity_complete = bool(runtime_identities) and all(identity["version_identity_complete"] for identity in runtime_identities)
    observed_components = sorted({component for identity in runtime_identities for component in identity["observed_components"]})
    component_identity_complete = bool(observed_components) and set(components) <= set(observed_components)
    argocd_versions = sorted({str(identity["argocd_version"]) for identity in runtime_identities if identity["argocd_version"]})
    kubernetes_api_versions = sorted({version for identity in runtime_identities for version in identity["kubernetes_api_server_versions"]})
    kubernetes_kubelet_versions = sorted({version for identity in runtime_identities for version in identity["kubernetes_kubelet_versions"]})
    runtime_identity = {
        "status": "complete" if runtime_identity_complete else ("partial" if bound else "explicit-gap"),
        "argocd_versions": argocd_versions,
        "kubernetes_api_server_versions": kubernetes_api_versions,
        "kubernetes_kubelet_versions": kubernetes_kubelet_versions,
        "profiles": sorted({str(identity["profile"]) for identity in runtime_identities if identity["profile"]}),
        "artifact_evidence_ids": evidence_ids,
        "gap": None if runtime_identity_complete else ("Artifact内のArgo CD／Kubernetes version identityが不完全。" if bound else "Behavior固有Runtime ArtifactがなくArgo CD／Kubernetes version identityを確定できない。"),
    }
    integrated = next(row for row in reference_result["tests"] if row["scenario"] == scenario)
    gaps = []
    if not bound:
        gaps.append("Behavior固有の当該Scenario Evidenceがない。")
    if bound and not runtime_identity_complete:
        gaps.append("Argo CD／Kubernetes runtime version identityがArtifact内で完結していない。")
    if bound and not component_identity_complete:
        gaps.append("期待Controller identityをArtifactから直接確認できない。")
    for channel, value in observations.items():
        if value["status"] == "explicit-gap":
            gaps.append(f"{channel}: {value['gap']}")
    gaps.extend([
        "統合Scenario AuditをBehavior固有Proofへ流用しない。",
        "Authority raw anchorの人手DecisionがなくAtomic behaviorへ昇格していない。",
    ])
    if bound and runtime_identity_complete and component_identity_complete:
        status = "bounded-runtime-proof"
    elif bound:
        status = "bounded-artifact-proof"
    else:
        status = "behavior-specific-gap"
    return {
        "schema_version": 1,
        "id": f"proof.behavior.{item['id']}.{scenario}",
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "behavior_scope": "current-surface-not-human-reviewed-authority-atomic",
        "behavior_id": item["id"],
        "area": item["area"],
        "kind": item["kind"],
        "target_id": item["target_id"],
        "surface_state": item["state"],
        "scenario": scenario,
        "attempts": 1,
        "status": status,
        "authority_binding": {
            "status": "explicit-gap" if local_obligation else "locked-source-candidate",
            "source_id": None if local_obligation else source["id"],
            "source_digest": None if local_obligation else source["digest"],
            "candidate_locator": item["locator"],
            "locator_scope": "local-proof-obligation-not-authority" if local_obligation else "locked-argocd-source-tree-candidate",
            "authority_gap": "このlocatorはローカルProof obligationであり一次資料Atomic bindingではない。" if local_obligation else "人手Review DecisionがなくSource locator候補からAtomic behaviorへ昇格していない。",
            "review_decision_id": None,
            "human_reviewed": False,
            "authority_atomic_binding": False,
        },
        "controller_kubernetes_behavior": {
            "expected_argocd_components": components,
            "observed_argocd_components": observed_components,
            "component_identity_status": "complete" if component_identity_complete else "explicit-gap",
            "component_identity_complete": component_identity_complete,
            "component_identity_gap": None if component_identity_complete else "期待する全Argo CD component identityをBehavior固有Artifactから確認できない。",
            "kubernetes_behavior": kubernetes_behavior,
        },
        "runtime_identity": runtime_identity,
        "runtime_identities": runtime_identities,
        "evidence_bindings": [{
            "evidence_id": data["id"],
            "record": data["record_binding"],
            "artifact": data["artifact_binding"],
            "artifact_matches_record": data["artifact_matches_record"],
        } for data in bound],
        "observations": observations,
        "integrated_reference": {
            "manifest": binding(MANIFEST),
            "result": {"path": RESULT.relative_to(ROOT).as_posix(), "digest": reference_digest, "bytes": len(canonical(reference_result))},
            "scenario_row_id": integrated["id"],
            "outcome": integrated["outcome"],
            "attempts": integrated["attempts"],
            "final_status": integrated["final_status"],
            "runtime_attempts": integrated["runtime_attempts"],
            "scenario_evaluated": True,
            "single_topology_execution": False,
            "used_as_behavior_specific_evidence": False,
        },
        "closure": {
            "dedicated_row": True,
            "dedicated_artifact": True,
            "behavior_specific_evidence": bool(bound),
            "real_kubernetes_runtime": bool(bound) and all(identity["real_kubernetes_runtime"] for identity in runtime_identities),
            "runtime_identity_complete": runtime_identity_complete,
            "authority_atomic_binding": False,
            "completion_eligible": False,
        },
        "gaps": gaps,
    }


def build_all() -> tuple[dict[str, Any], list[tuple[Path, dict[str, Any]]]]:
    manifest = load_yaml(MANIFEST)
    inventory = load_yaml(INVENTORY)
    source_lock = load_yaml(SOURCES)
    source = next(item for item in source_lock["sources"] if item["id"] == inventory["authority"]["source_id"])
    if [item["id"] for item in manifest["scenarios"]] != SCENARIOS:
        raise ValueError("Reference System Scenario集合または順序が不正です")
    evidence_ids = sorted({evidence_id for scenario in manifest["scenarios"] for evidence_id in scenario["evidence_ids"]})
    evidence_cache = {evidence_id: evidence_data(evidence_id) for evidence_id in evidence_ids}
    reference_result = build_reference_result(manifest, evidence_cache)
    reference_digest = sha256_bytes(canonical(reference_result))
    item_evidence: dict[str, list[str]] = defaultdict(list)
    for evidence_binding in inventory["evidence_bindings"]:
        for item_id in evidence_binding["item_ids"]:
            item_evidence[item_id].append(evidence_binding["evidence_id"])
    proofs: list[tuple[Path, dict[str, Any]]] = []
    for item in inventory["items"]:
        for scenario in SCENARIOS:
            path = PROOF_ROOT / item["id"] / f"{scenario}.proof.json"
            proofs.append((path, build_proof(item, scenario, item_evidence, evidence_cache, source, reference_result, reference_digest)))
    status_counts = Counter(proof["status"] for _, proof in proofs)
    by_scenario = {}
    for scenario in SCENARIOS:
        rows = [proof for _, proof in proofs if proof["scenario"] == scenario]
        by_scenario[scenario] = {
            "rows": len(rows),
            "bounded_runtime_proofs": sum(item["status"] == "bounded-runtime-proof" for item in rows),
            "bounded_artifact_proofs": sum(item["status"] == "bounded-artifact-proof" for item in rows),
            "behavior_specific_gaps": sum(item["status"] == "behavior-specific-gap" for item in rows),
            "runtime_identity_complete": sum(item["closure"]["runtime_identity_complete"] for item in rows),
            "authority_atomic_bindings": 0,
            "completion_eligible": 0,
        }
    files = [{
        "id": proof["id"],
        "behavior_id": proof["behavior_id"],
        "scenario": proof["scenario"],
        "path": path.relative_to(ROOT).as_posix(),
        "digest": sha256_bytes(canonical(proof)),
        "status": proof["status"],
    } for path, proof in proofs]
    index = {
        "schema_version": 1,
        "id": "argocd-scenario-proof-matrix-v1",
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "status": "incomplete-authority-atomic-and-runtime-closure",
        "reference": FE_REFERENCE,
        "denominator": f"{len(inventory['items'])}-current-surface-items-x-{len(SCENARIOS)}-scenarios",
        "scenario_order": SCENARIOS,
        "source_bindings": {
            "generator": binding(Path(__file__).resolve()),
            "validator": binding(VALIDATOR),
            "manifest": binding(MANIFEST),
            "surface_inventory": binding(INVENTORY),
            "sources_lock": binding(SOURCES),
            "environment_lock": binding(ENVIRONMENT_LOCK),
            "integrated_result": {"path": RESULT.relative_to(ROOT).as_posix(), "digest": reference_digest, "bytes": len(canonical(reference_result))},
        },
        "summary": {
            "behaviors": len(inventory["items"]),
            "scenarios": len(SCENARIOS),
            "rows": len(proofs),
            "dedicated_artifacts": len(proofs),
            "bounded_runtime_proofs": status_counts["bounded-runtime-proof"],
            "bounded_artifact_proofs": status_counts["bounded-artifact-proof"],
            "behavior_specific_gaps": status_counts["behavior-specific-gap"],
            "runtime_identity_complete": sum(proof["closure"]["runtime_identity_complete"] for _, proof in proofs),
            "integrated_scenario_rows": len(reference_result["tests"]),
            "integrated_runtime_passed": 0,
            "authority_atomic_bindings": 0,
            "completion_eligible_rows": 0,
        },
        "by_scenario": by_scenario,
        "files": files,
        "completion_limits": [
            "現行100 SurfaceはAuthority人手Review済みAtomic behavior母集団ではない。",
            "10 Scenario offline integration auditを各Behavior固有Runtime Proofへ流用しない。",
            "各rowのresource state、controller log、metric、traceはArtifact bindingまたは明示gapのまま保持する。",
            "同一Topology実行、Performance、広域Compatibility、OTLP traceのGapが残る。",
            "Authority atomic bindingなしではcompletion eligibleを0から増やさない。",
        ],
    }
    return reference_result, [(INDEX, index), *proofs]


def main() -> None:
    reference_result, outputs = build_all()
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_bytes(canonical(reference_result))
    if PROOF_ROOT.exists():
        shutil.rmtree(PROOF_ROOT)
    for path, value in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))
    index = outputs[0][1]
    summary = index["summary"]
    print(
        "Generated Scenario Proof Matrix: "
        f"rows={summary['rows']} runtime={summary['bounded_runtime_proofs']} artifact={summary['bounded_artifact_proofs']} "
        f"gaps={summary['behavior_specific_gaps']} authority-atomic=0 completion=0"
    )


if __name__ == "__main__":
    main()
