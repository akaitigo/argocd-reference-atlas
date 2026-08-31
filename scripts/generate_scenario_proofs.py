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

from lib.atomic_evidence_publish import publish_evidence_tree, validate_publish_manifest, write_publish_manifest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence"
EVIDENCE_STAGING_ROOT = ROOT / ".evidence-next"
EVIDENCE_BACKUP_ROOT = ROOT / ".evidence-previous"
MANIFEST = ROOT / "integrations/reference-system/manifest.yaml"
INVENTORY = ROOT / "definitive/surface-inventory.yaml"
COVERAGE = ROOT / "coverage.yaml"
VARIANT_CONTRACT = ROOT / "definitive/scenario-variant-contract.yaml"
SOURCES = ROOT / "sources.lock.yaml"
ENVIRONMENT_LOCK = ROOT / "environments/kind/argocd-v3.5.2.lock"
RESULT = ROOT / "evidence/reference-system/results.json"
PROOF_ROOT = ROOT / "evidence/scenarios/behaviors"
INDEX = ROOT / "evidence/scenarios/index.json"
RUNTIME_REGISTRY = ROOT / "evidence/scenarios/runtime/index.yaml"
ATOMIC_PUBLISH_MANIFEST = ROOT / "evidence/scenarios/atomic-publish-manifest.json"
VALIDATOR = ROOT / "scripts/validate_scenario_proofs.py"
SCENARIOS = ["normal", "boundary", "rejection", "failure", "recovery", "migration", "operations", "security", "performance", "compatibility"]
FE_REFERENCE = {
    "repository": "frontend-behavior-atlas",
    "commit": "f2e4c4b19156f8e993f48cdcbce23679ad881924",
    "files": {
        "docs/REFERENCE_SYSTEM.md": "sha256:5562aa75e57c518c402c31d97885083bed3d1e3abc0af2ecade5c5cb3f188d49",
        "docs/DEFINITIVE_GATE_V2_REFERENCE.md": "sha256:8e6ec1b9277d5bf0a7d8a36618c42212b2037ca43643e64ec0e79150de19a690",
        "scripts/lib/scenario-proof.ts": "sha256:8b89ff8d0f042b181abe22a2fb1280546f7534f0525a931c6437a177fdb2432f",
        "scripts/verify-pattern-scenario-evidence.ts": "sha256:3643d1dd6ab6830d1a729fc0684a6691e8fc7af4b2d85bae3e5ec01d89113469",
        "scripts/verify-scenario-proofs.ts": "sha256:d6192f7da3b160300690f3a4168846711b366b77f8fc6c28918733db221005cd",
        "scripts/test-scenario-proofs.ts": "sha256:78e578e66df9d6d3bb59d52f32440e6fd03bf492a67be96afdcea7f2a71d0628",
        "playwright.pattern-scenario.config.ts": "sha256:93360ee588f65f04692500106e94a4e2e0be9b75645fe87f8fbe87245cb7716a",
    },
}
ATOMIC_PUBLISH_REFERENCE = {
    "repository": "frontend-behavior-atlas",
    "commit": "7175de4305afb308722d5b83475e91c18da64957",
    "file": "scripts/reporters/pattern-scenario-evidence-reporter.ts",
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


def exact_file_binding(value: Any, *, expected_prefix: str | None = None) -> bool:
    if not isinstance(value, dict) or set(value) < {"path", "digest", "bytes"}:
        return False
    relative = str(value["path"])
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        return False
    if expected_prefix is not None and not relative.startswith(expected_prefix):
        return False
    return path.is_file() and binding(path) == {key: value[key] for key in ("path", "digest", "bytes")}


def resolve_json_pointer(value: Any, pointer_value: str) -> Any:
    if not isinstance(pointer_value, str) or not pointer_value.startswith("/"):
        raise ValueError(f"Oracle JSON Pointerが不正です: {pointer_value}")
    current = value
    for raw in pointer_value[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ValueError(f"Oracle JSON PointerがArtifactに存在しません: {pointer_value}")
    return current


def validate_runtime_oracle(report_id: str, variant: dict[str, Any]) -> bool:
    assertions = variant.get("oracle", {}).get("assertions", [])
    if variant.get("oracle", {}).get("status") != "pass" or not isinstance(assertions, list) or not assertions:
        return False
    channels = {"resource_state", "controller_log", "metric", "trace"}
    observed_channels = set()
    for assertion in assertions:
        channel = assertion.get("channel")
        if channel not in channels or assertion.get("operator") != "equals":
            raise ValueError(f"Dedicated Runtime Oracle assertionが不正です: {report_id}")
        artifact = variant.get("artifacts", {}).get(channel, {})
        if not exact_file_binding(artifact):
            return False
        actual = resolve_json_pointer(load_json(ROOT / artifact["path"]), assertion.get("pointer"))
        if actual != assertion.get("expected"):
            raise ValueError(f"Dedicated Runtime OracleがArtifact実値と不一致です: {report_id} {channel} {assertion.get('pointer')}")
        observed_channels.add(channel)
    return observed_channels == channels


def load_dedicated_runtime_reports(registry: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    reports: dict[tuple[str, str], dict[str, Any]] = {}
    used_artifact_paths: set[str] = set()
    for reference in registry.get("reports", []):
        if not exact_file_binding(reference):
            raise ValueError(f"Dedicated Runtime report bindingが不正です: {reference.get('path')}")
        report = load_json(ROOT / reference["path"])
        if report.get("id") != reference.get("id"):
            raise ValueError(f"Dedicated Runtime report IDがregistryと一致しません: {reference.get('id')}")
        surface_id = report.get("surface_id")
        scenario = report.get("scenario")
        key = (surface_id, scenario)
        if not isinstance(surface_id, str) or scenario not in SCENARIOS or key in reports:
            raise ValueError(f"Dedicated Runtime report scopeが不正または重複しています: {key}")
        variant_records = report.get("variants", [])
        if not isinstance(variant_records, list):
            raise ValueError(f"Dedicated Runtime variantsが配列ではありません: {report['id']}")
        variant_ids: set[str] = set()
        source_verified = bool(variant_records)
        harness_verified = bool(variant_records)
        oracle_verified = bool(variant_records)
        artifact_bindings_verified = True
        artifact_paths_distinct = True
        for variant in variant_records:
            variant_id = variant.get("variant_id")
            if not isinstance(variant_id, str) or not variant_id or variant_id in variant_ids:
                raise ValueError(f"Dedicated Runtime Variant IDが不正または重複しています: {report['id']}")
            variant_ids.add(variant_id)
            variant_source_verified = variant.get("source", {}).get("owner") == f"{report['id']}:{variant_id}:source" and exact_file_binding(variant.get("source"))
            variant_harness_verified = variant.get("harness", {}).get("owner") == f"{report['id']}:{variant_id}:harness" and exact_file_binding(variant.get("harness"))
            source_verified = source_verified and variant_source_verified
            harness_verified = harness_verified and variant_harness_verified
            if variant.get("source") and not variant_source_verified:
                raise ValueError(f"Dedicated Runtime Variant Source bindingが不正です: {report['id']} {variant_id}")
            if variant.get("harness") and not variant_harness_verified:
                raise ValueError(f"Dedicated Runtime Variant Harness bindingが不正です: {report['id']} {variant_id}")
            expected_prefix = f"evidence/scenarios/runtime/artifacts/{report['id']}/{variant_id}/"
            local_paths: set[str] = set()
            artifact_kinds = {
                "resource_state": "kubernetes-resource-state",
                "controller_log": "argocd-controller-log",
                "metric": "argocd-prometheus-metric",
                "trace": "scenario-execution-trace",
            }
            for channel in ("resource_state", "controller_log", "metric", "trace"):
                artifact = variant.get("artifacts", {}).get(channel)
                if artifact is None:
                    artifact_bindings_verified = False
                    continue
                owner = f"{report['id']}:{variant_id}:{channel}"
                verified = artifact.get("owner") == owner and artifact.get("kind") == artifact_kinds[channel] and exact_file_binding(artifact, expected_prefix=expected_prefix)
                artifact_bindings_verified = artifact_bindings_verified and verified
                artifact_path = artifact.get("path")
                if artifact_path in local_paths or artifact_path in used_artifact_paths:
                    artifact_paths_distinct = False
                if isinstance(artifact_path, str):
                    local_paths.add(artifact_path)
                    used_artifact_paths.add(artifact_path)
            variant_oracle_verified = validate_runtime_oracle(report["id"], variant)
            oracle_verified = oracle_verified and variant_oracle_verified
            if variant.get("oracle") and not variant_oracle_verified:
                raise ValueError(f"Dedicated Runtime Oracle bindingが不正です: {report['id']} {variant_id}")
        reports[key] = {
            "reference": {key: reference[key] for key in ("path", "digest", "bytes")},
            "report": report,
            "source_verified": source_verified,
            "harness_verified": harness_verified,
            "oracle_verified": oracle_verified,
            "artifact_bindings_verified": artifact_bindings_verified,
            "artifact_paths_distinct": artifact_paths_distinct,
        }
    return reports


def surface_variant_contract(surface_id: str, contract: dict[str, Any]) -> dict[str, Any]:
    denominator = contract["denominator"]
    override = next((item for item in denominator.get("surface_overrides", []) if item.get("surface_id") == surface_id), None)
    status = override.get("status") if override else denominator["default_status"]
    variants = override.get("variants", []) if override else []
    ids = [item["id"] if isinstance(item, dict) else item for item in variants]
    if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError(f"Surface Variant IDが不正または重複しています: {surface_id}")
    exhaustive = status == "approved-exhaustive" and bool(ids)
    return {
        "source": binding(VARIANT_CONTRACT),
        "status": status,
        "expected_variant_ids": ids,
        "exhaustive": exhaustive,
        "gap": None if exhaustive else "Authority人手Review済みの非空かつexhaustiveなSurface Variant分母がない。",
    }


def evaluate_gap_closure(
    surface_id: str,
    scenario: str,
    variant_contract: dict[str, Any],
    dedicated: dict[str, Any] | None,
    expected_components: list[str],
) -> dict[str, Any]:
    report = dedicated["report"] if dedicated else {}
    records = report.get("variants", []) if dedicated else []
    execution = report.get("execution", {})
    runtime = report.get("runtime_identity", {})
    expected_variants = variant_contract["expected_variant_ids"]
    actual_variants = [record.get("variant_id") for record in records]
    all_variants = bool(expected_variants) and sorted(actual_variants) == sorted(expected_variants)
    retry_zero = bool(records) and execution.get("retries") == 0
    first_attempt_pass = bool(records) and all(
        record.get("attempts") == 1
        and record.get("outcome") == "expected"
        and record.get("final_status") == "passed"
        and record.get("error") is None
        for record in records
    )
    oracle_pass = bool(records) and bool(dedicated and dedicated.get("oracle_verified")) and all(
        record.get("oracle", {}).get("status") == "pass"
        and bool(record.get("oracle", {}).get("assertions"))
        for record in records
    )
    real_runtime = bool(records) and (
        runtime.get("profile") == "cluster"
        and runtime.get("real_argocd_kubernetes_runtime") is True
    )
    runtime_identity_complete = real_runtime and (
        bool(runtime.get("argocd_version"))
        and bool(runtime.get("kubernetes_api_server_version"))
        and bool(runtime.get("kubernetes_kubelet_version"))
        and bool(runtime.get("cluster_uid"))
        and bool(runtime.get("topology_digest"))
        and set(expected_components) <= set(runtime.get("observed_argocd_components", []))
    )
    exact_scope = bool(records) and report.get("surface_id") == surface_id and report.get("scenario") == scenario
    channels = ("resource_state", "controller_log", "metric", "trace")
    artifact_conditions = {
        f"per_variant_{channel}_artifact": bool(records)
        and all(isinstance(record.get("artifacts", {}).get(channel), dict) for record in records)
        and bool(dedicated and dedicated["artifact_bindings_verified"])
        for channel in channels
    }
    conditions = {
        "variant_denominator_exhaustive": variant_contract["exhaustive"],
        "exact_surface_scenario_scope": exact_scope,
        "all_variants_driven": all_variants,
        "real_argocd_kubernetes_runtime": real_runtime,
        "retry_zero": retry_zero,
        "first_attempt_pass": first_attempt_pass,
        "oracle_pass": oracle_pass,
        "source_digest_bound": bool(dedicated and dedicated["source_verified"]),
        "harness_digest_bound": bool(dedicated and dedicated["harness_verified"]),
        "runtime_identity_complete": runtime_identity_complete,
        **artifact_conditions,
        "artifact_paths_dedicated_and_distinct": bool(dedicated and dedicated["artifact_bindings_verified"] and dedicated["artifact_paths_distinct"]),
        "integrated_or_other_metadata_reuse_absent": bool(dedicated and dedicated["artifact_bindings_verified"] and dedicated["artifact_paths_distinct"]),
    }
    runtime_conditions = {key: value for key, value in conditions.items() if key != "variant_denominator_exhaustive"}
    dedicated_runtime_execution_complete = bool(runtime_conditions) and all(runtime_conditions.values())
    closed = all(conditions.values())
    closure_artifacts = {}
    for channel in channels:
        artifacts = [
            {"variant_id": record.get("variant_id"), "artifact": record.get("artifacts", {}).get(channel)}
            for record in records
            if isinstance(record.get("artifacts", {}).get(channel), dict)
        ]
        condition = conditions[f"per_variant_{channel}_artifact"]
        closure_artifacts[channel] = {
            "status": "artifact" if condition else "explicit-gap",
            "artifacts": artifacts,
            "gap": None if condition else f"全Variant所有の専用{channel} Artifactが揃っていない。",
        }
    return {
        "status": "closed" if closed else "open",
        "scenario_gap_closed": closed,
        "dedicated_runtime_execution_complete": dedicated_runtime_execution_complete,
        "variant_contract": variant_contract,
        "dedicated_runtime_report": dedicated["reference"] if dedicated else None,
        "dedicated_runtime_record_ids": [f"{report.get('id')}:{variant}" for variant in actual_variants] if dedicated else [],
        "source_bindings": [
            {"variant_id": record.get("variant_id"), "source": record.get("source")}
            for record in records
        ],
        "harness_bindings": [
            {"variant_id": record.get("variant_id"), "harness": record.get("harness")}
            for record in records
        ],
        "runtime_identity": runtime if dedicated else None,
        "oracle_records": [
            {"variant_id": record.get("variant_id"), "oracle": record.get("oracle")}
            for record in records
        ],
        "artifacts": closure_artifacts,
        "conditions": conditions,
        "failed_conditions": [key for key, passed in conditions.items() if not passed],
        "closure_evidence_source": "dedicated-surface-scenario-runtime-registry-only",
        "prohibited_substitutions": [
            "integrated-reference-result",
            "historical-bundle-evidence",
            "other-surface-scenario-variant-artifact-metadata",
            "mock-or-static-runtime",
        ],
    }


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
    target_set: str,
    scenario: str,
    item_evidence: dict[str, list[str]],
    evidence_cache: dict[str, dict[str, Any]],
    source: dict[str, Any],
    reference_result: dict[str, Any],
    reference_digest: str,
    variant_contract: dict[str, Any],
    dedicated_runtime: dict[str, Any] | None,
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
    scenario_gap_closure = evaluate_gap_closure(item["id"], scenario, variant_contract, dedicated_runtime, components)
    gaps.extend([
        *[f"closure-condition: {condition}" for condition in scenario_gap_closure["failed_conditions"]],
        "統合Scenario AuditをBehavior固有Proofへ流用しない。",
        "Authority raw anchorの人手DecisionがなくAtomic behaviorへ昇格していない。",
    ])
    if bound and runtime_identity_complete and component_identity_complete:
        supporting_status = "supporting-runtime-artifact"
    elif bound:
        supporting_status = "supporting-artifact"
    else:
        supporting_status = "no-supporting-artifact"
    return {
        "schema_version": 1,
        "id": f"proof.behavior.{item['id']}.{scenario}",
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "behavior_scope": "current-surface-not-human-reviewed-authority-atomic",
        "behavior_id": item["id"],
        "pattern_id": item["id"],
        "area": item["area"],
        "kind": item["kind"],
        "target_id": item["target_id"],
        "target_set": target_set,
        "source_bindings": [],
        "surface_state": item["state"],
        "scenario": scenario,
        "attempts": 1,
        "status": "scenario-gap-closed" if scenario_gap_closure["scenario_gap_closed"] else "scenario-gap-open",
        "supporting_evidence_assessment": {
            "status": supporting_status,
            "closure_credit": False,
            "reason": "既存Lab Artifactは専用Surface×Scenario×全Variant Runtime reportではないためClosureへ算入しない。",
        },
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
            "role": "supporting-historical-not-scenario-gap-closure",
            "closure_credit": False,
        } for data in bound],
        "observations": observations,
        "observation_role": "supporting-historical-not-scenario-gap-closure",
        "scenario_gap_closure": scenario_gap_closure,
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
            "supporting_behavior_specific_evidence": bool(bound),
            "supporting_real_kubernetes_runtime": bool(bound) and all(identity["real_kubernetes_runtime"] for identity in runtime_identities),
            "supporting_runtime_identity_complete": runtime_identity_complete,
            "scenario_gap_closed": scenario_gap_closure["scenario_gap_closed"],
            "dedicated_runtime_execution_complete": scenario_gap_closure["dedicated_runtime_execution_complete"],
            "authority_atomic_binding": False,
            "completion_eligible": False,
        },
        "gaps": gaps,
    }


def build_all() -> tuple[dict[str, Any], list[tuple[Path, dict[str, Any]]]]:
    manifest = load_yaml(MANIFEST)
    inventory = load_yaml(INVENTORY)
    coverage = load_yaml(COVERAGE)
    target_sets = {target["id"]: target["target_set"] for target in coverage["targets"]}
    variant_contract_document = load_yaml(VARIANT_CONTRACT)
    runtime_registry = load_yaml(RUNTIME_REGISTRY)
    dedicated_runtime_reports = load_dedicated_runtime_reports(runtime_registry)
    source_lock = load_yaml(SOURCES)
    source = next(item for item in source_lock["sources"] if item["id"] == inventory["authority"]["source_id"])
    if variant_contract_document.get("id") != "argocd-scenario-variant-contract-v1" or variant_contract_document.get("reference", {}).get("commit") != FE_REFERENCE["commit"]:
        raise ValueError("Scenario Variant contract identityまたはFE Referenceが不正です")
    if runtime_registry.get("id") != "argocd-dedicated-surface-scenario-runtime-registry-v1":
        raise ValueError("Dedicated Runtime registry identityが不正です")
    inventory_ids = {item["id"] for item in inventory["items"]}
    override_ids = [item.get("surface_id") for item in variant_contract_document["denominator"].get("surface_overrides", [])]
    if len(override_ids) != len(set(override_ids)) or set(override_ids) - inventory_ids:
        raise ValueError("Scenario Variant overrideが重複または未知Surfaceを参照しています")
    if {surface_id for surface_id, _ in dedicated_runtime_reports} - inventory_ids:
        raise ValueError("Dedicated Runtime reportが未知Surfaceを参照しています")
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
        variants = surface_variant_contract(item["id"], variant_contract_document)
        for scenario in SCENARIOS:
            path = PROOF_ROOT / item["id"] / f"{scenario}.proof.json"
            dedicated = dedicated_runtime_reports.get((item["id"], scenario))
            proofs.append((path, build_proof(item, target_sets[item["target_id"]], scenario, item_evidence, evidence_cache, source, reference_result, reference_digest, variants, dedicated)))
    supporting_counts = Counter(proof["supporting_evidence_assessment"]["status"] for _, proof in proofs)
    by_scenario = {}
    for scenario in SCENARIOS:
        rows = [proof for _, proof in proofs if proof["scenario"] == scenario]
        by_scenario[scenario] = {
            "rows": len(rows),
            "scenario_gaps_closed": sum(item["scenario_gap_closure"]["scenario_gap_closed"] for item in rows),
            "scenario_gaps_open": sum(not item["scenario_gap_closure"]["scenario_gap_closed"] for item in rows),
            "supporting_runtime_artifacts": sum(item["supporting_evidence_assessment"]["status"] == "supporting-runtime-artifact" for item in rows),
            "supporting_artifacts": sum(item["supporting_evidence_assessment"]["status"] == "supporting-artifact" for item in rows),
            "no_supporting_artifacts": sum(item["supporting_evidence_assessment"]["status"] == "no-supporting-artifact" for item in rows),
            "supporting_runtime_identity_complete": sum(item["closure"]["supporting_runtime_identity_complete"] for item in rows),
            "authority_atomic_bindings": 0,
            "completion_eligible": 0,
            "dedicated_runtime_execution_complete": sum(item["scenario_gap_closure"]["dedicated_runtime_execution_complete"] for item in rows),
        }
    files = [{
        "id": proof["id"],
        "pattern_id": proof["pattern_id"],
        "behavior_id": proof["behavior_id"],
        "scenario": proof["scenario"],
        "path": path.relative_to(ROOT).as_posix(),
        "digest": sha256_bytes(canonical(proof)),
        "status": proof["status"],
        "supporting_evidence_status": proof["supporting_evidence_assessment"]["status"],
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
            "variant_contract": binding(VARIANT_CONTRACT),
            "dedicated_runtime_registry": binding(RUNTIME_REGISTRY),
            "sources_lock": binding(SOURCES),
            "environment_lock": binding(ENVIRONMENT_LOCK),
            "integrated_result": {"path": RESULT.relative_to(ROOT).as_posix(), "digest": reference_digest, "bytes": len(canonical(reference_result))},
        },
        "atomic_publish": {
            "reference": ATOMIC_PUBLISH_REFERENCE,
            "manifest_path": ATOMIC_PUBLISH_MANIFEST.relative_to(ROOT).as_posix(),
            "output_root": EVIDENCE_ROOT.relative_to(ROOT).as_posix(),
            "staging_root": EVIDENCE_STAGING_ROOT.relative_to(ROOT).as_posix(),
            "backup_root": EVIDENCE_BACKUP_ROOT.relative_to(ROOT).as_posix(),
            "retention_contract": {
                "publish_on": "full-run-passed",
                "failed_run": "retain-prior-success",
                "swap": "staged-directory-rename-with-rollback",
                "partial_overwrite": "rejected",
                "mixed_generation": "rejected",
            },
        },
        "summary": {
            "behaviors": len(inventory["items"]),
            "scenarios": len(SCENARIOS),
            "rows": len(proofs),
            "dedicated_artifacts": len(proofs),
            "scenario_gaps_closed": sum(proof["scenario_gap_closure"]["scenario_gap_closed"] for _, proof in proofs),
            "scenario_gaps_open": sum(not proof["scenario_gap_closure"]["scenario_gap_closed"] for _, proof in proofs),
            "variant_denominators_exhaustive": sum(proof["scenario_gap_closure"]["variant_contract"]["exhaustive"] for _, proof in proofs) // len(SCENARIOS),
            "dedicated_runtime_reports": len(dedicated_runtime_reports),
            "dedicated_runtime_execution_complete_rows": sum(proof["scenario_gap_closure"]["dedicated_runtime_execution_complete"] for _, proof in proofs),
            "supporting_runtime_artifacts": supporting_counts["supporting-runtime-artifact"],
            "supporting_artifacts": supporting_counts["supporting-artifact"],
            "no_supporting_artifacts": supporting_counts["no-supporting-artifact"],
            "supporting_runtime_identity_complete": sum(proof["closure"]["supporting_runtime_identity_complete"] for _, proof in proofs),
            "integrated_scenario_rows": len(reference_result["tests"]),
            "integrated_runtime_passed": 0,
            "authority_atomic_bindings": 0,
            "completion_eligible_rows": 0,
        },
        "by_scenario": by_scenario,
        "files": files,
        "completion_limits": [
            "現行100 SurfaceはAuthority人手Review済みAtomic behavior母集団ではない。",
            "Authority人手Review済みのexhaustiveなSurface Variant分母がない行は閉じない。",
            "Surface×Scenario×全Variantの専用実Argo CD／Kubernetes RuntimeだけをClosureへ算入する。",
            "retry 0、first-attempt pass、Oracle、Source/Harness digest、Runtime identity、4専用Artifactの全条件を要求する。",
            "既存Lab bundle、統合結果、別Artifact metadataをClosureへ流用しない。",
            "10 Scenario offline integration auditを各Behavior固有Runtime Proofへ流用しない。",
            "各rowのresource state、controller log、metric、traceはArtifact bindingまたは明示gapのまま保持する。",
            "同一Topology実行、Performance、広域Compatibility、OTLP traceのGapが残る。",
            "Authority atomic bindingなしではcompletion eligibleを0から増やさない。",
        ],
    }
    return reference_result, [(INDEX, index), *proofs]


def main() -> None:
    reference_result, outputs = build_all()
    generated = [(RESULT, reference_result), *outputs]
    expected_paths = [path.relative_to(EVIDENCE_ROOT) for path, _ in generated]
    manifest_relative = ATOMIC_PUBLISH_MANIFEST.relative_to(EVIDENCE_ROOT)

    def populate(staging_root: Path) -> None:
        staged_proof_root = staging_root / PROOF_ROOT.relative_to(EVIDENCE_ROOT)
        if staged_proof_root.exists():
            shutil.rmtree(staged_proof_root)
        for final_path, value in generated:
            staged_path = staging_root / final_path.relative_to(EVIDENCE_ROOT)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(canonical(value))
        write_publish_manifest(
            staging_root,
            manifest_relative,
            expected_paths,
            reporter_id="argocd-scenario-proof-atomic-publish-v1",
            reference_commit=ATOMIC_PUBLISH_REFERENCE["commit"],
        )

    def validate(staging_root: Path) -> None:
        validate_publish_manifest(staging_root, manifest_relative, expected_paths)
        expected_proofs = {
            path.relative_to(EVIDENCE_ROOT)
            for path, _ in outputs
            if path != INDEX
        }
        actual_proofs = {
            path.relative_to(staging_root)
            for path in (staging_root / PROOF_ROOT.relative_to(EVIDENCE_ROOT)).glob("*/*.proof.json")
        }
        if actual_proofs != expected_proofs:
            raise ValueError(f"stagingのScenario Proof集合が不完全です: actual={len(actual_proofs)} expected={len(expected_proofs)}")
        for final_path, value in generated:
            staged_path = staging_root / final_path.relative_to(EVIDENCE_ROOT)
            if staged_path.read_bytes() != canonical(value):
                raise ValueError(f"staging Artifactが生成結果と一致しません: {final_path.relative_to(ROOT)}")

    publish_evidence_tree(
        EVIDENCE_ROOT,
        EVIDENCE_STAGING_ROOT,
        EVIDENCE_BACKUP_ROOT,
        populate,
        validate,
        full_run_passed=True,
    )
    index = outputs[0][1]
    summary = index["summary"]
    print(
        "Generated Scenario Proof Matrix: "
        f"rows={summary['rows']} closed={summary['scenario_gaps_closed']} open={summary['scenario_gaps_open']} "
        f"supporting-runtime={summary['supporting_runtime_artifacts']} supporting-artifact={summary['supporting_artifacts']} "
        f"authority-atomic=0 completion=0"
    )


if __name__ == "__main__":
    main()
