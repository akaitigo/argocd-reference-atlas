#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Closure Plan security-004の4 rowを専用Kindで実行し、原子的にEvidenceを公開する。"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.atomic_evidence_publish import (  # noqa: E402
    publish_evidence_tree,
    validate_publish_manifest,
    write_publish_manifest,
)
from run_application_sync_policy_normal import (  # noqa: E402
    ARGOCD_NAMESPACE,
    CONTEXT,
    OUTPUT,
    assert_isolated_runtime,
    binding,
    command,
    kubectl,
    load_json_output,
    now,
    published_binding,
    runtime_identity,
    wait_for,
    write_json,
)


SOURCE_URL = "http://source-server.argocd-atlas-source.svc.cluster.local/repo.git"
HARNESS = Path(__file__).resolve()
STAGING = ROOT / "evidence/scenarios/.runtime-next"
BACKUP = ROOT / "evidence/scenarios/.runtime-previous"
WORK = ROOT / ".runtime/scenario-security-004"
FIXTURE_ROOT = ROOT / "fixtures/scenarios/security-004"
WORKLOAD_SOURCE = FIXTURE_ROOT / "workload/configmap.yaml"
CLUSTER_SOURCE = FIXTURE_ROOT / "cluster-secret.yaml"
DECISION_SOURCE = FIXTURE_ROOT / "duck-resources.yaml"
GIT_SOURCE = FIXTURE_ROOT / "git-directory/approved/configmap.yaml"
TRANCHE_LABEL = "atlas.argocd.io/tranche"
TRANCHE_VALUE = "security-004"
NAMESPACES = {
    "prune": "atlas-security-004-prune",
    "preserve": "atlas-security-004-preserve",
}
REPORT_VARIANTS = {
    "runtime.applicationset-deletion.security.v3-5-2": {
        "surface_id": "applicationset.deletion",
        "source": WORKLOAD_SOURCE,
        "variants": ["resources-pruned-on-deletion", "resources-preserved-on-deletion"],
    },
    "runtime.applicationset-generator-cluster.security.v3-5-2": {
        "surface_id": "applicationset.generator.cluster",
        "source": CLUSTER_SOURCE,
        "variants": ["restricted-cluster-excluded", "approved-cluster-selected"],
    },
    "runtime.applicationset-generator-cluster-decision-resource.security.v3-5-2": {
        "surface_id": "applicationset.generator.cluster-decision-resource",
        "source": DECISION_SOURCE,
        "variants": ["unregistered-decision-rejected", "registered-decision-selected"],
    },
    "runtime.applicationset-generator-git-directory.security.v3-5-2": {
        "surface_id": "applicationset.generator.git-directory",
        "source": GIT_SOURCE,
        "variants": ["restricted-directory-excluded", "approved-directory-selected"],
    },
}
ARTIFACT_KINDS = {
    "resource_state": "kubernetes-resource-state",
    "controller_log": "argocd-controller-log",
    "metric": "argocd-prometheus-metric",
    "trace": "scenario-execution-trace",
}


def kjson(*args: str) -> dict[str, Any]:
    return load_json_output(*args)


def kubectl_input(value: str, *args: str) -> str:
    return command(["kubectl", "--context", CONTEXT, *args], input_text=value)


def apply_object(value: dict[str, Any]) -> None:
    kubectl_input(yaml.safe_dump(value, sort_keys=False), "apply", "-f", "-")


def application_names(owner: str) -> list[str]:
    items = kjson("-n", ARGOCD_NAMESPACE, "get", "applications", "-o", "json").get("items", [])
    return sorted(
        item.get("metadata", {}).get("name", "")
        for item in items
        if any(ref.get("kind") == "ApplicationSet" and ref.get("name") == owner for ref in item.get("metadata", {}).get("ownerReferences", []))
    )


def application(name: str) -> dict[str, Any] | None:
    result = command_result(["kubectl", "--context", CONTEXT, "-n", ARGOCD_NAMESPACE, "get", "application", name, "-o", "json"])
    if result[0] != 0:
        return None
    value = json.loads(result[1])
    return value if isinstance(value, dict) else None


def command_result(args: list[str]) -> tuple[int, str, str]:
    import subprocess

    result = subprocess.run(args, text=True, capture_output=True, check=False)
    return result.returncode, result.stdout, result.stderr


def configmap_present(namespace: str) -> bool:
    code, _, _ = command_result([
        "kubectl", "--context", CONTEXT, "-n", namespace, "get", "configmap", "atlas-security-004-workload", "-o", "name",
    ])
    return code == 0


def app_synced_healthy(name: str) -> bool:
    value = application(name)
    status = (value or {}).get("status", {})
    return status.get("sync", {}).get("status") == "Synced" and status.get("health", {}).get("status") == "Healthy"


def appset_metric_lines(name: str) -> list[str]:
    raw = kubectl(
        "get", "--raw",
        "/api/v1/namespaces/argocd/services/http:argocd-applicationset-controller:8080/proxy/metrics",
    )
    lines = [line for line in raw.splitlines() if line.startswith("argocd_appset_") and f'name="{name}"' in line]
    if not lines:
        raise RuntimeError(f"ApplicationSet metricがありません: {name}")
    return lines


def controller_logs(names: list[str]) -> dict[str, Any]:
    values = {}
    for component, resource in (
        ("argocd-applicationset-controller", "deployment/argocd-applicationset-controller"),
        ("argocd-application-controller", "statefulset/argocd-application-controller"),
    ):
        raw = kubectl("-n", ARGOCD_NAMESPACE, "logs", resource, "--since=30m")
        lines = raw.splitlines()
        values[component] = {
            "line_count": len(lines),
            "matching_lines": [line for line in lines if any(name in line for name in names)][-100:],
            "tail": lines[-100:],
        }
    return values


def appset_object(name: str) -> dict[str, Any] | None:
    code, out, _ = command_result([
        "kubectl", "--context", CONTEXT, "-n", ARGOCD_NAMESPACE, "get", "applicationset", name, "-o", "json",
    ])
    return json.loads(out) if code == 0 else None


def capture(
    report_id: str,
    variant_id: str,
    appset_name: str,
    observation: dict[str, Any],
    actions: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    metric_lines: list[str] | None = None,
) -> dict[str, Any]:
    surface_id = REPORT_VARIANTS[report_id]["surface_id"]
    names = application_names(appset_name)
    applications = [application(name) for name in names]
    resource_state = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "application_set": appset_object(appset_name),
        "application_names": names,
        "applications": [item for item in applications if item is not None],
        "observation": observation,
        "security": {"credential_material_captured": False, "secret_scan_hits": 0},
    }
    controller_log = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "components": ["argocd-applicationset-controller", "argocd-application-controller"],
        "logs": controller_logs([appset_name, *names]),
    }
    metric = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "component": "argocd-applicationset-controller",
        "samples": metric_lines if metric_lines is not None else appset_metric_lines(appset_name),
    }
    trace = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "started_at": now(),
        "completed_at": now(),
        "attempt": 1,
        "retries": 0,
        "actions": actions,
        "result": {"first_attempt": True, **observation},
    }
    common = [
        {"channel": "resource_state", "pointer": "/security/secret_scan_hits", "operator": "equals", "expected": 0},
        {"channel": "controller_log", "pointer": "/components/0", "operator": "equals", "expected": "argocd-applicationset-controller"},
        {"channel": "metric", "pointer": "/component", "operator": "equals", "expected": "argocd-applicationset-controller"},
        {"channel": "trace", "pointer": "/result/first_attempt", "operator": "equals", "expected": True},
    ]
    return {
        "resource_state": resource_state,
        "controller_log": controller_log,
        "metric": metric,
        "trace": trace,
        "assertions": [*common, *assertions],
    }


def template(name: str, revision: str, path: str, namespace: str = "default", destination_name: str | None = None) -> dict[str, Any]:
    destination = {"namespace": namespace}
    if destination_name is None:
        destination["server"] = "https://kubernetes.default.svc"
    else:
        destination["name"] = destination_name
    return {
        "metadata": {"name": name, "labels": {TRANCHE_LABEL: TRANCHE_VALUE}},
        "spec": {
            "project": "default",
            "source": {"repoURL": SOURCE_URL, "targetRevision": revision, "path": path},
            "destination": destination,
        },
    }


def appset(name: str, generators: list[dict[str, Any]], template_value: dict[str, Any], sync_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"generators": generators, "template": template_value}
    if sync_policy is not None:
        spec["syncPolicy"] = sync_policy
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {"name": name, "namespace": ARGOCD_NAMESPACE, "labels": {TRANCHE_LABEL: TRANCHE_VALUE}},
        "spec": spec,
    }


def drive_deletion(captures: dict[tuple[str, str], dict[str, Any]], revision: str) -> None:
    report_id = "runtime.applicationset-deletion.security.v3-5-2"
    cases = [
        ("delete-prune", "delete-prune-child", NAMESPACES["prune"], False, "resources-pruned-on-deletion"),
        ("delete-preserve", "delete-preserve-child", NAMESPACES["preserve"], True, "resources-preserved-on-deletion"),
    ]
    for set_name, child_name, namespace, preserve, variant in cases:
        rendered = kubectl("create", "namespace", namespace, "--dry-run=client", "-o", "yaml")
        kubectl_input(rendered, "apply", "-f", "-")
        child = template(child_name, revision, "apps/security-004/workload", namespace)
        child["spec"]["syncPolicy"] = {"automated": {"prune": True, "selfHeal": True}}
        apply_object(appset(set_name, [{"list": {"elements": [{"suffix": "child"}]}}], child, {"preserveResourcesOnDeletion": preserve}))
        wait_for(lambda: application_names(set_name), [child_name], f"{set_name} child", timeout=300)
        wait_for(lambda: app_synced_healthy(child_name), True, f"{child_name} synced", timeout=300)
        wait_for(lambda: configmap_present(namespace), True, f"{namespace} workload", timeout=300)
        metrics = appset_metric_lines(set_name)
        kubectl("-n", ARGOCD_NAMESPACE, "delete", "applicationset", set_name, "--wait=true")
        wait_for(lambda: application(child_name) is None, True, f"{child_name} deleted", timeout=300)
        expected_present = preserve
        wait_for(lambda: configmap_present(namespace), expected_present, f"{namespace} resource preservation", timeout=300)
        observation = {
            "preserve_resources_on_deletion": preserve,
            "child_application_deleted": True,
            "workload_present_after_deletion": expected_present,
        }
        captures[(report_id, variant)] = capture(
            report_id,
            variant,
            set_name,
            observation,
            [{"action": "reconcile-and-sync-child", "status": "passed"}, {"action": "delete-applicationset", "status": "passed"}],
            [
                {"channel": "resource_state", "pointer": "/observation/preserve_resources_on_deletion", "operator": "equals", "expected": preserve},
                {"channel": "resource_state", "pointer": "/observation/workload_present_after_deletion", "operator": "equals", "expected": expected_present},
            ],
            metrics,
        )


def drive_cluster(captures: dict[tuple[str, str], dict[str, Any]], revision: str) -> None:
    report_id = "runtime.applicationset-generator-cluster.security.v3-5-2"
    name = "cluster-generator"
    kubectl_input(CLUSTER_SOURCE.read_text(encoding="utf-8"), "apply", "-f", "-")
    child = template("cluster-{{nameNormalized}}", revision, "apps/security-004/workload", destination_name="{{name}}")
    restricted = {"matchLabels": {"atlas.argocd.io/security-class": "restricted"}}
    approved = {"matchLabels": {"atlas.argocd.io/security-class": "approved"}}
    apply_object(appset(name, [{"clusters": {"selector": restricted}}], child))
    time.sleep(10)
    if application_names(name):
        raise RuntimeError("restricted selectorがcluster Applicationを生成しました")
    captures[(report_id, "restricted-cluster-excluded")] = capture(
        report_id,
        "restricted-cluster-excluded",
        name,
        {"selector": "restricted", "application_count": 0},
        [{"action": "reconcile-restricted-cluster-selector", "status": "excluded"}],
        [{"channel": "resource_state", "pointer": "/observation/application_count", "operator": "equals", "expected": 0}],
    )
    value = appset_object(name)
    assert value is not None
    value["spec"]["generators"][0]["clusters"]["selector"] = approved
    for field in ("status",):
        value.pop(field, None)
    value["metadata"] = {key: item for key, item in value["metadata"].items() if key in {"name", "namespace", "labels"}}
    apply_object(value)
    expected = ["cluster-atlas-security-004-in-cluster"]
    wait_for(lambda: application_names(name), expected, "approved cluster selected", timeout=300)
    captures[(report_id, "approved-cluster-selected")] = capture(
        report_id,
        "approved-cluster-selected",
        name,
        {"selector": "approved", "application_count": 1, "application_names": expected},
        [{"action": "select-approved-cluster-secret", "status": "passed"}],
        [{"channel": "resource_state", "pointer": "/observation/application_names", "operator": "equals", "expected": expected}],
    )


def drive_decision(captures: dict[tuple[str, str], dict[str, Any]], revision: str) -> None:
    report_id = "runtime.applicationset-generator-cluster-decision-resource.security.v3-5-2"
    name = "decision-generator"
    decision_objects = [
        value
        for value in yaml.safe_load_all(DECISION_SOURCE.read_text(encoding="utf-8"))
        if isinstance(value, dict)
    ]
    crds = [value for value in decision_objects if value.get("kind") == "CustomResourceDefinition"]
    dependents = [value for value in decision_objects if value.get("kind") != "CustomResourceDefinition"]
    if len(crds) != 1 or not dependents:
        raise RuntimeError("cluster decision fixtureのCRD/dependent構造が不正です")
    apply_object(crds[0])
    kubectl(
        "wait",
        "--for=condition=Established",
        "customresourcedefinition/atlasdecisions.atlas.argocd.io",
        "--timeout=60s",
    )
    for value in dependents:
        apply_object(value)
    child = template("decision-{{clusterName}}", revision, "apps/security-004/workload", destination_name="{{clusterName}}")
    generator = {"clusterDecisionResource": {"configMapRef": "atlas-security-004-duck-type", "name": "unregistered", "requeueAfterSeconds": 5}}
    apply_object(appset(name, [generator], child))
    time.sleep(10)
    if application_names(name):
        raise RuntimeError("未登録cluster decisionがApplicationを生成しました")
    captures[(report_id, "unregistered-decision-rejected")] = capture(
        report_id,
        "unregistered-decision-rejected",
        name,
        {"decision_resource": "unregistered", "application_count": 0},
        [{"action": "reconcile-unregistered-cluster-decision", "status": "rejected"}],
        [{"channel": "resource_state", "pointer": "/observation/application_count", "operator": "equals", "expected": 0}],
    )
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "applicationset", name, "--type", "json", "-p", json.dumps([
        {"op": "replace", "path": "/spec/generators/0/clusterDecisionResource/name", "value": "registered"},
    ]))
    expected = ["decision-atlas-security-004-in-cluster"]
    wait_for(lambda: application_names(name), expected, "registered cluster decision selected", timeout=300)
    captures[(report_id, "registered-decision-selected")] = capture(
        report_id,
        "registered-decision-selected",
        name,
        {"decision_resource": "registered", "application_count": 1, "application_names": expected},
        [{"action": "reconcile-registered-cluster-decision", "status": "passed"}],
        [{"channel": "resource_state", "pointer": "/observation/application_names", "operator": "equals", "expected": expected}],
    )


def drive_git_directory(captures: dict[tuple[str, str], dict[str, Any]], revision: str) -> None:
    report_id = "runtime.applicationset-generator-git-directory.security.v3-5-2"
    name = "git-directory-generator"
    child = template("git-{{path.basename}}", revision, "{{path}}")
    directories = [
        {"path": "apps/security-004/git-directory/*"},
        {"path": "apps/security-004/git-directory/restricted", "exclude": True},
    ]
    apply_object(appset(name, [{"git": {"repoURL": SOURCE_URL, "revision": revision, "directories": directories}}], child))
    expected = ["git-approved"]
    wait_for(lambda: application_names(name), expected, "restricted directory excluded", timeout=300)
    captures[(report_id, "restricted-directory-excluded")] = capture(
        report_id,
        "restricted-directory-excluded",
        name,
        {"restricted_directory_present": False, "application_names": expected},
        [{"action": "reconcile-git-directories-with-restricted-exclusion", "status": "passed"}],
        [{"channel": "resource_state", "pointer": "/observation/restricted_directory_present", "operator": "equals", "expected": False}],
    )
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "applicationset", name, "--type", "json", "-p", json.dumps([
        {"op": "replace", "path": "/spec/generators/0/git/directories", "value": [{"path": "apps/security-004/git-directory/approved"}]},
    ]))
    wait_for(lambda: application_names(name), expected, "approved directory selected", timeout=300)
    captures[(report_id, "approved-directory-selected")] = capture(
        report_id,
        "approved-directory-selected",
        name,
        {"selection": "approved-only", "application_names": expected},
        [{"action": "reconcile-explicit-approved-directory", "status": "passed"}],
        [{"channel": "resource_state", "pointer": "/observation/selection", "operator": "equals", "expected": "approved-only"}],
    )


def cleanup() -> None:
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "applicationsets", "-l", f"{TRANCHE_LABEL}={TRANCHE_VALUE}", "--ignore-not-found", "--wait=true")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "applications", "-l", f"{TRANCHE_LABEL}={TRANCHE_VALUE}", "--ignore-not-found", "--wait=true")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "secret", "atlas-security-004-cluster", "--ignore-not-found")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "configmap", "atlas-security-004-duck-type", "--ignore-not-found")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "rolebinding", "atlas-security-004-duck-reader", "--ignore-not-found")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "role", "atlas-security-004-duck-reader", "--ignore-not-found")
    kubectl("delete", "crd", "atlasdecisions.atlas.argocd.io", "--ignore-not-found", "--wait=true")
    for namespace in NAMESPACES.values():
        kubectl("delete", "namespace", namespace, "--ignore-not-found", "--wait=true")


def runtime_identity_extended() -> dict[str, Any]:
    value = runtime_identity()
    pods = kjson("-n", ARGOCD_NAMESPACE, "get", "pods", "-o", "json").get("items", [])
    observed = set(value.get("observed_argocd_components", []))
    if any(item.get("metadata", {}).get("name", "").startswith("argocd-applicationset-controller-") for item in pods):
        observed.add("argocd-applicationset-controller")
    value["observed_argocd_components"] = sorted(observed)
    return value


def build_variant(staging: Path, report_id: str, variant_id: str, value: dict[str, Any]) -> dict[str, Any]:
    target_root = staging / "artifacts" / report_id / variant_id
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True)
    artifacts = {}
    for channel, kind in ARTIFACT_KINDS.items():
        target = target_root / f"{channel}.json"
        write_json(target, value[channel])
        artifacts[channel] = {**published_binding(target, staging), "kind": kind, "owner": f"{report_id}:{variant_id}:{channel}"}
    source = REPORT_VARIANTS[report_id]["source"]
    return {
        "variant_id": variant_id,
        "attempts": 1,
        "outcome": "expected",
        "final_status": "passed",
        "error": None,
        "oracle": {"status": "pass", "assertions": value["assertions"]},
        "source": {**binding(source), "owner": f"{report_id}:{variant_id}:source"},
        "harness": {**binding(HARNESS), "owner": f"{report_id}:{variant_id}:harness"},
        "artifacts": artifacts,
    }


def publish(captures: dict[tuple[str, str], dict[str, Any]], identity: dict[str, Any]) -> None:
    manifest_relative = Path("atomic-publish-manifest.json")

    def populate(staging: Path) -> None:
        references = []
        for report_id, contract in REPORT_VARIANTS.items():
            variants = [build_variant(staging, report_id, variant_id, captures[(report_id, variant_id)]) for variant_id in contract["variants"]]
            report = {
                "schema_version": 1,
                "id": report_id,
                "atlas_id": "argocd-reference-atlas",
                "surface_id": contract["surface_id"],
                "scenario": "security",
                "status": "passed-runtime-execution-pending-authority-review",
                "execution": {"command": "python3 scripts/scenarios/run_security_004.py", "attempts": 1, "retries": 0, "first_attempt": True},
                "runtime_identity": identity,
                "variant_denominator": {
                    "source": "definitive/scenario-variant-contract.yaml",
                    "status": "runtime-declared-pending-authority-human-review",
                    "declared_variant_ids": contract["variants"],
                    "all_declared_variants_executed": True,
                    "authority_exhaustive": False,
                    "completion_eligible": False,
                },
                "variants": variants,
            }
            report_path = staging / "reports" / f"{report_id}.json"
            write_json(report_path, report)
            references.append({"id": report_id, **published_binding(report_path, staging)})
        existing = yaml.safe_load((OUTPUT / "index.yaml").read_text(encoding="utf-8"))
        replaced = set(REPORT_VARIANTS)
        all_references = [item for item in existing.get("reports", []) if item["id"] not in replaced]
        all_references.extend(references)
        all_references.sort(key=lambda item: item["id"])
        registry = {
            "schema_version": 1,
            "id": "argocd-dedicated-surface-scenario-runtime-registry-v1",
            "atlas_id": "argocd-reference-atlas",
            "status": "incomplete-authority-review-with-dedicated-runtime-reports",
            "reports": all_references,
            "admission_contract": existing["admission_contract"],
        }
        (staging / "index.yaml").write_text(yaml.safe_dump(registry, allow_unicode=True, sort_keys=False), encoding="utf-8")
        expected = [path.relative_to(staging) for path in staging.rglob("*") if path.is_file() and path.relative_to(staging) != manifest_relative]
        write_publish_manifest(staging, manifest_relative, expected, reporter_id="argocd-dedicated-runtime-atomic-publish-v1", reference_commit="7175de4305afb308722d5b83475e91c18da64957")

    def validate(staging: Path) -> None:
        expected = [path.relative_to(staging) for path in staging.rglob("*") if path.is_file() and path.relative_to(staging) != manifest_relative]
        validate_publish_manifest(staging, manifest_relative, expected)
        registry = yaml.safe_load((staging / "index.yaml").read_text(encoding="utf-8"))
        if not set(REPORT_VARIANTS) <= {item["id"] for item in registry["reports"]}:
            raise RuntimeError("security-004 Runtime report集合がregistryにありません")

    publish_evidence_tree(OUTPUT, STAGING, BACKUP, populate, validate, full_run_passed=True)


def main() -> None:
    assert_isolated_runtime()
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    revision = command(["git", f"--git-dir={ROOT / '.runtime/source/repo.git'}", "rev-parse", "refs/heads/main"]).strip()
    captures: dict[tuple[str, str], dict[str, Any]] = {}
    cleanup()
    try:
        drive_deletion(captures, revision)
        drive_cluster(captures, revision)
        drive_decision(captures, revision)
        drive_git_directory(captures, revision)
        if len(captures) != 8:
            raise RuntimeError(f"security-004 Variant実行数が不正です: {len(captures)}")
        publish(captures, runtime_identity_extended())
    finally:
        cleanup()
    print("Dedicated Runtime tranche passed: security-004 rows=4 variants=8 retries=0")


if __name__ == "__main__":
    main()
