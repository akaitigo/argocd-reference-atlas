#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Closure Plan security-001の4 rowを専用Kindで実行し、原子的にEvidenceを公開する。"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts"))
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
    parse_prometheus_labels,
    published_binding,
    runtime_identity,
    write_json,
)
from lib.atomic_evidence_publish import (  # noqa: E402
    publish_evidence_tree,
    validate_publish_manifest,
    write_publish_manifest,
)


PROJECT = "atlas-security"
MULTI_APP = "atlas-security-multi-source"
OPS_APP = "atlas-security-operations"
DESTINATION = "atlas-security-workloads"
SOURCE_URL = "http://source-server.argocd-atlas-source.svc.cluster.local/repo.git"
HARNESS = Path(__file__).resolve()
SOURCE_MULTI_A = ROOT / "fixtures/scenarios/security-001/source-a/shared.yaml"
SOURCE_MULTI_B = ROOT / "fixtures/scenarios/security-001/source-b/shared.yaml"
SOURCE_OPERATIONS = ROOT / "fixtures/scenarios/security-001/operations/configmap.yaml"
STAGING = ROOT / "evidence/scenarios/.runtime-next"
BACKUP = ROOT / "evidence/scenarios/.runtime-previous"
WORK = ROOT / ".runtime/scenario-security-001"
REPORT_VARIANTS = {
    "runtime.application-multi-source.security.v3-5-2": {
        "surface_id": "application.multi-source",
        "app": MULTI_APP,
        "source_by_variant": {
            "source-order-a-then-b": SOURCE_MULTI_A,
            "source-order-b-then-a": SOURCE_MULTI_B,
        },
        "variants": ["source-order-a-then-b", "source-order-b-then-a"],
    },
    "runtime.application-operation-refresh.security.v3-5-2": {
        "surface_id": "application.operation.refresh",
        "app": OPS_APP,
        "source_by_variant": {
            "rbac-denied-hard-refresh": SOURCE_OPERATIONS,
            "rbac-allowed-hard-refresh": SOURCE_OPERATIONS,
        },
        "variants": ["rbac-denied-hard-refresh", "rbac-allowed-hard-refresh"],
    },
    "runtime.application-operation-rollback.security.v3-5-2": {
        "surface_id": "application.operation.rollback",
        "app": OPS_APP,
        "source_by_variant": {
            "rbac-denied-rollback": SOURCE_OPERATIONS,
            "rbac-allowed-rollback": SOURCE_OPERATIONS,
        },
        "variants": ["rbac-denied-rollback", "rbac-allowed-rollback"],
    },
    "runtime.application-operation-sync.security.v3-5-2": {
        "surface_id": "application.operation.sync",
        "app": OPS_APP,
        "source_by_variant": {
            "rbac-denied-sync": SOURCE_OPERATIONS,
            "rbac-allowed-sync": SOURCE_OPERATIONS,
        },
        "variants": ["rbac-denied-sync", "rbac-allowed-sync"],
    },
}
ARTIFACT_KINDS = {
    "resource_state": "kubernetes-resource-state",
    "controller_log": "argocd-controller-log",
    "metric": "argocd-prometheus-metric",
    "trace": "scenario-execution-trace",
}


def command_result(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def kjson(*args: str) -> dict[str, Any]:
    return load_json_output(*args)


def kubectl_input(input_text: str, *args: str) -> str:
    return command(["kubectl", "--context", CONTEXT, *args], input_text=input_text)


def wait_for(read: Callable[[], Any], expected: Any, label: str, timeout: int = 240) -> Any:
    deadline = time.monotonic() + timeout
    observed = None
    while time.monotonic() < deadline:
        observed = read()
        if observed == expected:
            return observed
        time.sleep(2)
    raise RuntimeError(f"oracle timeout: {label}: expected={expected!r} observed={observed!r}")


def app(app_name: str) -> dict[str, Any]:
    return kjson("-n", ARGOCD_NAMESPACE, "get", "application", app_name, "-o", "json")


def app_status(app_name: str) -> tuple[str, str]:
    value = app(app_name).get("status", {})
    return value.get("sync", {}).get("status", ""), value.get("health", {}).get("status", "")


def configmap_value(name: str, key: str) -> str:
    value = kjson("-n", DESTINATION, "get", "configmap", name, "-o", "json")
    return str(value.get("data", {}).get(key, ""))


def request_sync(app_name: str, revision: str | None = None, source: dict[str, Any] | None = None) -> None:
    before = app(app_name).get("status", {}).get("operationState", {}).get("startedAt")
    sync: dict[str, Any] = {"prune": True}
    if revision:
        sync["revision"] = revision
    if source:
        sync["source"] = source
        sync["syncStrategy"] = {"apply": {}}
    payload = {"operation": {"initiatedBy": {"username": "atlas-security-allowed"}, "sync": sync}}
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "application", app_name, "--type", "merge", "-p", json.dumps(payload))

    def operation() -> tuple[str, bool]:
        state = app(app_name).get("status", {}).get("operationState", {})
        return str(state.get("phase", "")), bool(state.get("startedAt") and state.get("startedAt") != before)

    wait_for(operation, ("Succeeded", True), f"{app_name} operation succeeded")


def wait_synced_healthy(app_name: str) -> None:
    wait_for(lambda: app_status(app_name), ("Synced", "Healthy"), f"{app_name} Synced Healthy")


def rbac_can(subject: str, action: str, app_name: str) -> str:
    object_name = f"{PROJECT}/{app_name}"
    result = command_result([
        "kubectl", "--context", CONTEXT, "-n", ARGOCD_NAMESPACE, "exec", "deployment/argocd-server", "--",
        "argocd", "admin", "settings", "rbac", "can", subject, action, "applications", object_name,
        "--namespace", ARGOCD_NAMESPACE,
    ])
    output = (result.stdout + "\n" + result.stderr).strip()
    if "Yes" in output:
        return "Yes"
    if "No" in output:
        return "No"
    raise RuntimeError(f"Argo CD RBAC decisionを取得できません: subject={subject} action={action} rc={result.returncode} output={output}")


def setup_rbac() -> None:
    backup = kjson("-n", ARGOCD_NAMESPACE, "get", "configmap", "argocd-rbac-cm", "-o", "json")
    write_json(WORK / "argocd-rbac-cm.backup.json", backup)
    policy = "\n".join([
        f"p, atlas-security-allowed, applications, get, {PROJECT}/*, allow",
        f"p, atlas-security-allowed, applications, sync, {PROJECT}/*, allow",
        f"p, atlas-security-denied, applications, get, {PROJECT}/*, deny",
        f"p, atlas-security-denied, applications, sync, {PROJECT}/*, deny",
    ])
    patch = {"data": {"policy.csv": policy, "policy.default": "role:atlas-empty", "policy.matchMode": "glob", "scopes": "[groups]"}}
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", "argocd-rbac-cm", "--type", "merge", "-p", json.dumps(patch))


def qualify_rbac_policy() -> None:
    checks = [
        ("atlas-security-denied", "get", "No"),
        ("atlas-security-denied", "sync", "No"),
        ("atlas-security-allowed", "get", "Yes"),
        ("atlas-security-allowed", "sync", "Yes"),
    ]
    for subject, action, expected in checks:
        actual = rbac_can(subject, action, OPS_APP)
        if actual != expected:
            raise RuntimeError(f"RBAC qualification failed: subject={subject} action={action} expected={expected} actual={actual}")


def restore_rbac() -> None:
    backup_path = WORK / "argocd-rbac-cm.backup.json"
    if not backup_path.is_file():
        return
    data = json.loads(backup_path.read_text(encoding="utf-8")).get("data", {})
    patch = [{"op": "replace", "path": "/data", "value": data}]
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", "argocd-rbac-cm", "--type", "json", "-p", json.dumps(patch))


def create_resources(main_revision: str, canary: str) -> None:
    namespace_yaml = command(["kubectl", "--context", CONTEXT, "create", "namespace", DESTINATION, "--dry-run=client", "-o", "yaml"])
    kubectl_input(namespace_yaml, "apply", "-f", "-")
    project = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AppProject",
        "metadata": {"name": PROJECT, "namespace": ARGOCD_NAMESPACE},
        "spec": {
            "sourceRepos": [SOURCE_URL],
            "destinations": [{"namespace": DESTINATION, "server": "https://kubernetes.default.svc"}],
            "namespaceResourceWhitelist": [{"group": "*", "kind": "*"}],
        },
    }
    multi = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": MULTI_APP, "namespace": ARGOCD_NAMESPACE},
        "spec": {
            "project": PROJECT,
            "sources": [
                {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-001/source-a"},
                {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-001/source-b"},
            ],
            "destination": {"server": "https://kubernetes.default.svc", "namespace": DESTINATION},
            "syncPolicy": {"syncOptions": ["CreateNamespace=true"]},
        },
    }
    operations = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": OPS_APP, "namespace": ARGOCD_NAMESPACE},
        "spec": {
            "project": PROJECT,
            "source": {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-001/operations"},
            "destination": {"server": "https://kubernetes.default.svc", "namespace": DESTINATION},
            "syncPolicy": {"syncOptions": ["CreateNamespace=true"]},
        },
    }
    objects = "---\n".join(yaml.safe_dump(value, sort_keys=False) for value in (project, multi, operations))
    kubectl_input(objects, "apply", "-f", "-")
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "atlas-security-repo-credentials",
            "namespace": ARGOCD_NAMESPACE,
            "labels": {"argocd.argoproj.io/secret-type": "repo-creds"},
        },
        "type": "Opaque",
        "stringData": {"url": SOURCE_URL, "username": "atlas-local", "password": canary},
    }
    kubectl_input(yaml.safe_dump(secret, sort_keys=False), "apply", "-f", "-")
    request_sync(MULTI_APP)
    request_sync(OPS_APP, main_revision)
    wait_synced_healthy(MULTI_APP)
    wait_synced_healthy(OPS_APP)


def cleanup_resources() -> None:
    for app_name in (MULTI_APP, OPS_APP):
        kubectl("-n", ARGOCD_NAMESPACE, "delete", "application", app_name, "--ignore-not-found", "--wait=true")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "appproject", PROJECT, "--ignore-not-found")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "secret", "atlas-security-repo-credentials", "--ignore-not-found")
    kubectl("delete", "namespace", DESTINATION, "--ignore-not-found", "--wait=true")


def collect_logs(app_name: str, canary: str) -> list[dict[str, Any]]:
    raw = kubectl("-n", ARGOCD_NAMESPACE, "logs", "statefulset/argocd-application-controller", "--since=15m")
    if canary in raw:
        raise RuntimeError("Controller logへのsynthetic credential漏洩を検出しました")
    entries = []
    for line in raw.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("application") == app_name:
            entries.append(entry)
    if not entries:
        raise RuntimeError(f"Controller logにApplication identityがありません: {app_name}")
    return entries


def collect_metric(app_name: str, canary: str) -> dict[str, Any]:
    raw = kubectl("get", "--raw", "/api/v1/namespaces/argocd/services/http:argocd-metrics:8082/proxy/metrics")
    if canary in raw:
        raise RuntimeError("Prometheus metricへのsynthetic credential漏洩を検出しました")
    line = next((item for item in raw.splitlines() if item.startswith("argocd_app_info{") and f'name="{app_name}"' in item), None)
    if line is None:
        raise RuntimeError(f"argocd_app_info metricがありません: {app_name}")
    return {"sample": line, "labels": parse_prometheus_labels(line), "value": 1}


def capture(
    report_id: str,
    variant_id: str,
    app_name: str,
    canary: str,
    started_at: str,
    actions: list[dict[str, Any]],
    result: dict[str, Any],
    resource_assertions: list[dict[str, Any]],
    rbac: dict[str, Any] | None = None,
) -> dict[str, Any]:
    surface_id = REPORT_VARIANTS[report_id]["surface_id"]
    application = app(app_name)
    configmaps_list = kjson("-n", DESTINATION, "get", "configmaps", "-o", "json")
    configmaps = {item["metadata"]["name"]: item for item in configmaps_list.get("items", [])}
    resource_state = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "application": application,
        "configmaps": configmaps,
        "rbac": rbac,
        "security": {"synthetic_credential_present_in_captured_state": False, "secret_scan_hits": 0},
    }
    entries = collect_logs(app_name, canary)
    controller_log = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "entries": entries,
    }
    metric = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "app_info": collect_metric(app_name, canary),
    }
    trace = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "started_at": started_at,
        "completed_at": now(),
        "attempt": 1,
        "retries": 0,
        "actions": actions,
        "result": {"first_attempt": True, "synthetic_credential_leak": False, **result},
    }
    for value in (resource_state, controller_log, metric, trace):
        if canary in json.dumps(value, ensure_ascii=False):
            raise RuntimeError(f"Artifactへのsynthetic credential漏洩を検出しました: {report_id}:{variant_id}")
    assertions = [
        {"channel": "resource_state", "pointer": "/security/secret_scan_hits", "operator": "equals", "expected": 0},
        {"channel": "controller_log", "pointer": "/entries/0/application", "operator": "equals", "expected": app_name},
        {"channel": "metric", "pointer": "/app_info/labels/name", "operator": "equals", "expected": app_name},
        {"channel": "trace", "pointer": "/result/first_attempt", "operator": "equals", "expected": True},
        *resource_assertions,
    ]
    return {
        "resource_state": resource_state,
        "controller_log": controller_log,
        "metric": metric,
        "trace": trace,
        "assertions": assertions,
    }


def drive_multi_source(captures: dict[tuple[str, str], dict[str, Any]], main_revision: str, canary: str) -> None:
    report_id = "runtime.application-multi-source.security.v3-5-2"
    wait_for(lambda: configmap_value("atlas-security-shared", "selected_source"), "source-b", "multi-source A then B precedence")
    captures[(report_id, "source-order-a-then-b")] = capture(
        report_id, "source-order-a-then-b", MULTI_APP, canary, now(),
        [{"action": "sync-source-order-a-then-b", "status": "passed"}, {"action": "verify-no-credential-leak", "status": "passed"}],
        {"selected_source": "source-b", "both_unique_resources_present": True},
        [
            {"channel": "resource_state", "pointer": "/configmaps/atlas-security-shared/data/selected_source", "operator": "equals", "expected": "source-b"},
            {"channel": "resource_state", "pointer": "/configmaps/atlas-security-source-a/data/present", "operator": "equals", "expected": "true"},
            {"channel": "resource_state", "pointer": "/configmaps/atlas-security-source-b/data/present", "operator": "equals", "expected": "true"},
        ],
    )
    sources = [
        {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-001/source-b"},
        {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-001/source-a"},
    ]
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "application", MULTI_APP, "--type", "merge", "-p", json.dumps({"spec": {"sources": sources}}))
    request_sync(MULTI_APP)
    wait_for(lambda: configmap_value("atlas-security-shared", "selected_source"), "source-a", "multi-source B then A precedence")
    wait_synced_healthy(MULTI_APP)
    captures[(report_id, "source-order-b-then-a")] = capture(
        report_id, "source-order-b-then-a", MULTI_APP, canary, now(),
        [{"action": "reverse-multi-source-order", "status": "passed"}, {"action": "sync-source-order-b-then-a", "status": "passed"}, {"action": "verify-no-credential-leak", "status": "passed"}],
        {"selected_source": "source-a", "both_unique_resources_present": True},
        [
            {"channel": "resource_state", "pointer": "/configmaps/atlas-security-shared/data/selected_source", "operator": "equals", "expected": "source-a"},
            {"channel": "resource_state", "pointer": "/configmaps/atlas-security-source-a/data/present", "operator": "equals", "expected": "true"},
            {"channel": "resource_state", "pointer": "/configmaps/atlas-security-source-b/data/present", "operator": "equals", "expected": "true"},
        ],
    )


def drive_operations(captures: dict[tuple[str, str], dict[str, Any]], main_revision: str, v2_revision: str, canary: str) -> None:
    refresh_report = "runtime.application-operation-refresh.security.v3-5-2"
    denied = rbac_can("atlas-security-denied", "get", OPS_APP)
    if denied != "No":
        raise RuntimeError("refresh deny policyがNoではありません")
    captures[(refresh_report, "rbac-denied-hard-refresh")] = capture(
        refresh_report, "rbac-denied-hard-refresh", OPS_APP, canary, now(),
        [{"action": "evaluate-argocd-rbac-get-for-hard-refresh", "subject": "atlas-security-denied", "decision": denied}, {"action": "do-not-mutate-after-denial", "status": "passed"}],
        {"rbac_decision": denied, "refresh_requested": False},
        [{"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "No"}],
        {"subject": "atlas-security-denied", "action": "get", "decision": denied},
    )
    allowed = rbac_can("atlas-security-allowed", "get", OPS_APP)
    if allowed != "Yes":
        raise RuntimeError("refresh allow policyがYesではありません")
    before = app(OPS_APP).get("status", {}).get("reconciledAt")
    kubectl("-n", ARGOCD_NAMESPACE, "annotate", "application", OPS_APP, "argocd.argoproj.io/refresh=hard", "--overwrite")
    wait_for(lambda: app(OPS_APP).get("status", {}).get("reconciledAt") != before, True, "authorized hard refresh")
    captures[(refresh_report, "rbac-allowed-hard-refresh")] = capture(
        refresh_report, "rbac-allowed-hard-refresh", OPS_APP, canary, now(),
        [{"action": "evaluate-argocd-rbac-get-for-hard-refresh", "subject": "atlas-security-allowed", "decision": allowed}, {"action": "request-hard-refresh", "status": "passed"}],
        {"rbac_decision": allowed, "refresh_requested": True, "reconciled_at_changed": True},
        [{"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "Yes"}],
        {"subject": "atlas-security-allowed", "action": "get", "decision": allowed},
    )

    kubectl("-n", ARGOCD_NAMESPACE, "patch", "application", OPS_APP, "--type", "merge", "-p", json.dumps({"spec": {"source": {"targetRevision": v2_revision}}}))
    request_sync(OPS_APP, v2_revision)
    wait_for(lambda: configmap_value(OPS_APP, "release"), "v2", "operations revision v2")
    wait_synced_healthy(OPS_APP)
    wait_for(lambda: len(app(OPS_APP).get("status", {}).get("history", [])) >= 2, True, "rollback history")
    history = app(OPS_APP)["status"]["history"]
    v1_history = next(item for item in history if item.get("revision") == main_revision)

    rollback_report = "runtime.application-operation-rollback.security.v3-5-2"
    denied = rbac_can("atlas-security-denied", "sync", OPS_APP)
    if denied != "No":
        raise RuntimeError("rollback deny policyがNoではありません")
    captures[(rollback_report, "rbac-denied-rollback")] = capture(
        rollback_report, "rbac-denied-rollback", OPS_APP, canary, now(),
        [{"action": "evaluate-argocd-rbac-sync-for-rollback", "subject": "atlas-security-denied", "decision": denied}, {"action": "retain-live-v2-after-denial", "status": "passed"}],
        {"rbac_decision": denied, "rollback_requested": False, "live_release": "v2"},
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "No"},
            {"channel": "resource_state", "pointer": f"/configmaps/{OPS_APP}/data/release", "operator": "equals", "expected": "v2"},
        ],
        {"subject": "atlas-security-denied", "action": "sync", "decision": denied},
    )
    allowed = rbac_can("atlas-security-allowed", "sync", OPS_APP)
    if allowed != "Yes":
        raise RuntimeError("rollback allow policyがYesではありません")
    request_sync(OPS_APP, main_revision, v1_history["source"])
    wait_for(lambda: configmap_value(OPS_APP, "release"), "v1", "authorized rollback to v1")
    captures[(rollback_report, "rbac-allowed-rollback")] = capture(
        rollback_report, "rbac-allowed-rollback", OPS_APP, canary, now(),
        [{"action": "evaluate-argocd-rbac-sync-for-rollback", "subject": "atlas-security-allowed", "decision": allowed}, {"action": "request-controller-rollback-to-history", "history_id": v1_history["id"], "status": "passed"}],
        {"rbac_decision": allowed, "rollback_requested": True, "live_release": "v1"},
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "Yes"},
            {"channel": "resource_state", "pointer": f"/configmaps/{OPS_APP}/data/release", "operator": "equals", "expected": "v1"},
        ],
        {"subject": "atlas-security-allowed", "action": "sync", "decision": allowed},
    )

    sync_report = "runtime.application-operation-sync.security.v3-5-2"
    denied = rbac_can("atlas-security-denied", "sync", OPS_APP)
    captures[(sync_report, "rbac-denied-sync")] = capture(
        sync_report, "rbac-denied-sync", OPS_APP, canary, now(),
        [{"action": "evaluate-argocd-rbac-sync", "subject": "atlas-security-denied", "decision": denied}, {"action": "retain-live-v1-after-denial", "status": "passed"}],
        {"rbac_decision": denied, "sync_requested": False, "live_release": "v1"},
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "No"},
            {"channel": "resource_state", "pointer": f"/configmaps/{OPS_APP}/data/release", "operator": "equals", "expected": "v1"},
        ],
        {"subject": "atlas-security-denied", "action": "sync", "decision": denied},
    )
    allowed = rbac_can("atlas-security-allowed", "sync", OPS_APP)
    request_sync(OPS_APP, v2_revision)
    wait_for(lambda: configmap_value(OPS_APP, "release"), "v2", "authorized sync to v2")
    wait_synced_healthy(OPS_APP)
    captures[(sync_report, "rbac-allowed-sync")] = capture(
        sync_report, "rbac-allowed-sync", OPS_APP, canary, now(),
        [{"action": "evaluate-argocd-rbac-sync", "subject": "atlas-security-allowed", "decision": allowed}, {"action": "request-controller-sync-to-v2", "status": "passed"}],
        {"rbac_decision": allowed, "sync_requested": True, "live_release": "v2"},
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "Yes"},
            {"channel": "resource_state", "pointer": f"/configmaps/{OPS_APP}/data/release", "operator": "equals", "expected": "v2"},
        ],
        {"subject": "atlas-security-allowed", "action": "sync", "decision": allowed},
    )


def build_variant(staging: Path, report_id: str, variant_id: str, capture_value: dict[str, Any]) -> dict[str, Any]:
    target_root = staging / "artifacts" / report_id / variant_id
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True)
    artifacts = {}
    for channel in ARTIFACT_KINDS:
        target = target_root / f"{channel}.json"
        write_json(target, capture_value[channel])
        artifacts[channel] = {
            **published_binding(target, staging),
            "kind": ARTIFACT_KINDS[channel],
            "owner": f"{report_id}:{variant_id}:{channel}",
        }
    source = REPORT_VARIANTS[report_id]["source_by_variant"][variant_id]
    return {
        "variant_id": variant_id,
        "attempts": 1,
        "outcome": "expected",
        "final_status": "passed",
        "error": None,
        "oracle": {"status": "pass", "assertions": capture_value["assertions"]},
        "source": {**binding(source), "owner": f"{report_id}:{variant_id}:source"},
        "harness": {**binding(HARNESS), "owner": f"{report_id}:{variant_id}:harness"},
        "artifacts": artifacts,
    }


def publish(captures: dict[tuple[str, str], dict[str, Any]], identity: dict[str, Any]) -> None:
    manifest_relative = Path("atomic-publish-manifest.json")

    def populate(staging: Path) -> None:
        new_references = []
        for report_id, contract in REPORT_VARIANTS.items():
            variants = [build_variant(staging, report_id, variant_id, captures[(report_id, variant_id)]) for variant_id in contract["variants"]]
            report = {
                "schema_version": 1,
                "id": report_id,
                "atlas_id": "argocd-reference-atlas",
                "surface_id": contract["surface_id"],
                "scenario": "security",
                "status": "passed-runtime-execution-pending-authority-review",
                "execution": {"command": "make scenario-runtime-security-001", "attempts": 1, "retries": 0, "first_attempt": True},
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
            new_references.append({"id": report_id, **published_binding(report_path, staging)})

        existing = yaml.safe_load((OUTPUT / "index.yaml").read_text(encoding="utf-8"))
        replaced = set(REPORT_VARIANTS)
        references = [item for item in existing.get("reports", []) if item["id"] not in replaced]
        references.extend(new_references)
        references.sort(key=lambda item: item["id"])
        registry = {
            "schema_version": 1,
            "id": "argocd-dedicated-surface-scenario-runtime-registry-v1",
            "atlas_id": "argocd-reference-atlas",
            "status": "incomplete-authority-review-with-dedicated-runtime-reports",
            "reports": references,
            "admission_contract": existing["admission_contract"],
        }
        (staging / "index.yaml").write_text(yaml.safe_dump(registry, allow_unicode=True, sort_keys=False), encoding="utf-8")
        expected = [path.relative_to(staging) for path in staging.rglob("*") if path.is_file() and path.relative_to(staging) != manifest_relative]
        write_publish_manifest(
            staging,
            manifest_relative,
            expected,
            reporter_id="argocd-dedicated-runtime-atomic-publish-v1",
            reference_commit="7175de4305afb308722d5b83475e91c18da64957",
        )

    def validate(staging: Path) -> None:
        expected = [path.relative_to(staging) for path in staging.rglob("*") if path.is_file() and path.relative_to(staging) != manifest_relative]
        validate_publish_manifest(staging, manifest_relative, expected)
        registry = yaml.safe_load((staging / "index.yaml").read_text(encoding="utf-8"))
        ids = {item["id"] for item in registry["reports"]}
        if not set(REPORT_VARIANTS) <= ids:
            raise RuntimeError("security-001 Runtime report集合がregistryにありません")

    publish_evidence_tree(OUTPUT, STAGING, BACKUP, populate, validate, full_run_passed=True)


def main() -> None:
    assert_isolated_runtime()
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    main_revision = command(["git", f"--git-dir={ROOT / '.runtime/source/repo.git'}", "rev-parse", "refs/heads/main"]).strip()
    v2_revision = command(["git", f"--git-dir={ROOT / '.runtime/source/repo.git'}", "rev-parse", "refs/heads/security-001-v2"]).strip()
    canary = hashlib.sha256(f"{now()}:{main_revision}:security-001".encode("utf-8")).hexdigest()
    captures: dict[tuple[str, str], dict[str, Any]] = {}
    cleanup_resources()
    setup_rbac()
    try:
        qualify_rbac_policy()
        create_resources(main_revision, canary)
        drive_multi_source(captures, main_revision, canary)
        drive_operations(captures, main_revision, v2_revision, canary)
        if len(captures) != 8:
            raise RuntimeError(f"security-001 Variant実行数が不正です: {len(captures)}")
        publish(captures, runtime_identity())
    finally:
        cleanup_resources()
        restore_rbac()
    print("Dedicated Runtime tranche passed: security-001 rows=4 variants=8 retries=0")


if __name__ == "__main__":
    main()
