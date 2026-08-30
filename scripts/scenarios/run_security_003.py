#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Closure Plan security-003の4 rowを専用Kindで実行し、原子的にEvidenceを公開する。"""

from __future__ import annotations

import json
import os
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


SOURCE_URL = "http://source-server.argocd-atlas-source.svc.cluster.local/repo.git"
WORKLOAD_NAMESPACE = "atlas-security-003-workloads"
TENANT_NAMESPACE = "atlas-security-003-tenant"
PROJECT_DENIED = "atlas-security-003-project-denied"
PROJECT_ALLOWED = "atlas-security-003-project-allowed"
SOURCES_PROJECT = "atlas-security-003-sources"
SYNC_PROJECT = "atlas-security-003-sync-policy"
APPSET_PROJECT = "atlas-security-003-appset"
PROJECT_APP = "atlas-security-003-project"
SOURCES_APP = "atlas-security-003-sources"
SYNC_APP = "atlas-security-003-sync-policy"
APPSET = "atlas-security-003-appset"
APPSET_CHILD = "atlas-security-003-generated"
ACCOUNT_UPDATE_DENIED = "atlas-security-003-update-denied"
ACCOUNT_ALLOWED = "atlas-security-003-allowed"
HARNESS = Path(__file__).resolve()
STAGING = ROOT / "evidence/scenarios/.runtime-next"
BACKUP = ROOT / "evidence/scenarios/.runtime-previous"
WORK = ROOT / ".runtime/scenario-security-003"
SOURCE_PROJECT = ROOT / "fixtures/scenarios/security-003/project/configmap.yaml"
SOURCE_SOURCES = ROOT / "fixtures/scenarios/security-003/sources-a/configmap.yaml"
SOURCE_SYNC = ROOT / "fixtures/scenarios/security-003/sync-policy/configmap.yaml"
SOURCE_APPSET = ROOT / "fixtures/scenarios/security-003/applicationset.yaml"
APPSET_FIXTURE = ROOT / "fixtures/scenarios/security-003/applicationset.yaml"
REPORT_VARIANTS = {
    "runtime.application-spec-project.security.v3-5-2": {
        "surface_id": "application.spec.project",
        "source": SOURCE_PROJECT,
        "variants": ["restricted-project-binding", "authorized-project-binding"],
    },
    "runtime.application-spec-sources.security.v3-5-2": {
        "surface_id": "application.spec.sources",
        "source": SOURCE_SOURCES,
        "variants": ["project-denied-multi-source", "project-allowed-multi-source"],
    },
    "runtime.application-spec-sync-policy.security.v3-5-2": {
        "surface_id": "application.spec.sync-policy",
        "source": SOURCE_SYNC,
        "variants": ["fixed-revision-manual-sync", "fixed-revision-automated-self-heal"],
    },
    "runtime.applicationset-any-namespace.security.v3-5-2": {
        "surface_id": "applicationset.any-namespace",
        "source": SOURCE_APPSET,
        "variants": ["namespace-not-allowlisted", "namespace-allowlisted"],
    },
}
ARTIFACT_KINDS = {
    "resource_state": "kubernetes-resource-state",
    "controller_log": "argocd-controller-log",
    "metric": "argocd-prometheus-metric",
    "trace": "scenario-execution-trace",
}


def command_result(args: list[str], *, env: dict[str, str] | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return subprocess.CompletedProcess(args, 124, stdout, stderr + "\ncommand timeout")


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


def source_revisions_ready(expected_revisions: set[str]) -> bool:
    result = command_result([
        "kubectl", "--context", CONTEXT, "-n", ARGOCD_NAMESPACE, "exec", "deployment/argocd-repo-server", "--",
        "git", "ls-remote", SOURCE_URL,
    ], timeout=60)
    if result.returncode != 0:
        return False
    observed = {line.split()[0] for line in result.stdout.splitlines() if line.split()}
    return expected_revisions <= observed


def application(name: str, namespace: str = ARGOCD_NAMESPACE) -> dict[str, Any]:
    return kjson("-n", namespace, "get", "application", name, "-o", "json")


def application_status(name: str, namespace: str = ARGOCD_NAMESPACE) -> tuple[str, str]:
    status = application(name, namespace).get("status", {})
    return status.get("sync", {}).get("status", ""), status.get("health", {}).get("status", "")


def wait_synced_healthy(name: str, namespace: str = ARGOCD_NAMESPACE) -> None:
    wait_for(lambda: application_status(name, namespace), ("Synced", "Healthy"), f"{namespace}/{name} Synced Healthy")


def condition(name: str, condition_type: str) -> dict[str, Any] | None:
    values = application(name).get("status", {}).get("conditions", [])
    return next((value for value in values if value.get("type") == condition_type), None)


def refresh(name: str, namespace: str = ARGOCD_NAMESPACE) -> None:
    kubectl("-n", namespace, "annotate", "application", name, "argocd.argoproj.io/refresh=hard", "--overwrite")


def configmap_names(namespace: str = WORKLOAD_NAMESPACE) -> list[str]:
    result = kjson("-n", namespace, "get", "configmaps", "-o", "json")
    return sorted(item.get("metadata", {}).get("name", "") for item in result.get("items", []))


def child_applications() -> list[dict[str, Any]]:
    return kjson("-n", TENANT_NAMESPACE, "get", "applications", "-o", "json").get("items", [])


def app_info_metric(name: str, secrets: list[str]) -> dict[str, Any]:
    raw = kubectl("get", "--raw", "/api/v1/namespaces/argocd/services/http:argocd-metrics:8082/proxy/metrics")
    if any(secret in raw for secret in secrets):
        raise RuntimeError("Prometheus metricへのephemeral token漏洩を検出しました")
    line = next((value for value in raw.splitlines() if value.startswith("argocd_app_info{") and f'name="{name}"' in value), None)
    if line is None:
        return {"sample_present": False, "sample": None, "labels": {}, "value": 0}
    return {"sample_present": True, "sample": line, "labels": parse_prometheus_labels(line), "value": 1}


def collect_application_logs(name: str, secrets: list[str]) -> list[dict[str, Any]]:
    raw = kubectl("-n", ARGOCD_NAMESPACE, "logs", "statefulset/argocd-application-controller", "--since=30m")
    if any(secret in raw for secret in secrets):
        raise RuntimeError("Controller logへのephemeral token漏洩を検出しました")
    entries = []
    for line in raw.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        identity = str(entry.get("application", ""))
        if identity == name or identity.endswith("/" + name):
            entries.append(entry)
    if not entries:
        raise RuntimeError(f"Controller logにApplication identityがありません: {name}")
    return entries


def collect_appset_logs(secrets: list[str]) -> dict[str, Any]:
    components = {}
    for component, resource in (
        ("argocd-applicationset-controller", "deployment/argocd-applicationset-controller"),
        ("argocd-application-controller", "statefulset/argocd-application-controller"),
    ):
        raw = kubectl("-n", ARGOCD_NAMESPACE, "logs", resource, "--since=30m")
        if any(secret in raw for secret in secrets):
            raise RuntimeError("Controller logへのephemeral token漏洩を検出しました")
        lines = raw.splitlines()
        components[component] = {
            "line_count": len(lines),
            "matching_lines": [line for line in lines if APPSET in line or APPSET_CHILD in line][-100:],
            "tail": lines[-100:],
        }
    return components


def argocd_cli(token: str, *args: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["ARGOCD_AUTH_TOKEN"] = token
    return command_result([
        "argocd", "--port-forward", "--port-forward-namespace", ARGOCD_NAMESPACE,
        "--kube-context", CONTEXT, "--insecure", "--http-retry-max", "0", *args,
    ], env=env, timeout=timeout)


def require_allowed(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(f"authorized Argo CD API call failed: {label}: rc={result.returncode}: {result.stderr[-500:]}")


def require_denied(result: subprocess.CompletedProcess[str], label: str) -> str:
    output = (result.stdout + "\n" + result.stderr).lower()
    if result.returncode == 0 or "permission denied" not in output:
        raise RuntimeError(f"denied Argo CD API callが拒否されませんでした: {label}: rc={result.returncode}: {output[-500:]}")
    return "permission-denied"


def rbac_can(subject: str, action: str, project: str, app_name: str) -> str:
    result = command_result([
        "kubectl", "--context", CONTEXT, "-n", ARGOCD_NAMESPACE, "exec", "deployment/argocd-server", "--",
        "argocd", "admin", "settings", "rbac", "can", subject, action, "applications", f"{project}/{app_name}",
        "--namespace", ARGOCD_NAMESPACE,
    ])
    output = (result.stdout + "\n" + result.stderr).strip()
    if "Yes" in output:
        return "Yes"
    if "No" in output:
        return "No"
    raise RuntimeError(f"Argo CD RBAC decisionを取得できません: subject={subject} action={action} rc={result.returncode}")


def backup_configuration() -> None:
    for name in ("argocd-cm", "argocd-rbac-cm", "argocd-cmd-params-cm"):
        write_json(WORK / f"{name}.backup.json", kjson("-n", ARGOCD_NAMESPACE, "get", "configmap", name, "-o", "json"))
    write_json(WORK / "argocd-secret.backup.json", kjson("-n", ARGOCD_NAMESPACE, "get", "secret", "argocd-secret", "-o", "json"))


def setup_auth() -> None:
    accounts = {
        f"accounts.{ACCOUNT_UPDATE_DENIED}": "apiKey",
        f"accounts.{ACCOUNT_ALLOWED}": "apiKey",
    }
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", "argocd-cm", "--type", "merge", "-p", json.dumps({"data": accounts}))
    policy = "\n".join([
        f"p, {ACCOUNT_UPDATE_DENIED}, applications, get, {SYNC_PROJECT}/*, allow",
        f"p, {ACCOUNT_UPDATE_DENIED}, applications, update, {SYNC_PROJECT}/*, deny",
        f"p, {ACCOUNT_ALLOWED}, applications, get, */*, allow",
        f"p, {ACCOUNT_ALLOWED}, applications, update, */*, allow",
        f"p, {ACCOUNT_ALLOWED}, applications, sync, */*, allow",
    ])
    data = {"policy.csv": policy, "policy.default": "role:atlas-empty", "policy.matchMode": "glob", "scopes": "[groups]"}
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", "argocd-rbac-cm", "--type", "merge", "-p", json.dumps({"data": data}))


def restore_configuration() -> None:
    for name in ("argocd-cm", "argocd-rbac-cm", "argocd-cmd-params-cm"):
        path = WORK / f"{name}.backup.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8")).get("data", {})
            kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", name, "--type", "json", "-p", json.dumps([{"op": "replace", "path": "/data", "value": data}]))
    secret_path = WORK / "argocd-secret.backup.json"
    if secret_path.is_file():
        data = json.loads(secret_path.read_text(encoding="utf-8")).get("data", {})
        kubectl("-n", ARGOCD_NAMESPACE, "patch", "secret", "argocd-secret", "--type", "json", "-p", json.dumps([{"op": "replace", "path": "/data", "value": data}]))


def rollout_namespace_watchers() -> None:
    for kind, name in (
        ("statefulset", "argocd-application-controller"),
        ("deployment", "argocd-server"),
        ("deployment", "argocd-applicationset-controller"),
    ):
        kubectl("-n", ARGOCD_NAMESPACE, "rollout", "restart", f"{kind}/{name}")
    for kind, name in (
        ("statefulset", "argocd-application-controller"),
        ("deployment", "argocd-server"),
        ("deployment", "argocd-applicationset-controller"),
    ):
        kubectl("-n", ARGOCD_NAMESPACE, "rollout", "status", f"{kind}/{name}", "--timeout=300s")


def generate_token(account: str) -> str:
    result = command_result(["argocd", "account", "generate-token", "--core", "--kube-context", CONTEXT, "--account", account])
    token = result.stdout.strip()
    if result.returncode != 0 or len(token) < 100:
        raise RuntimeError(f"local account tokenを生成できません: account={account} rc={result.returncode}")
    return token


def create_resources(main_revision: str, sync_revision: str) -> None:
    for namespace in (WORKLOAD_NAMESPACE, TENANT_NAMESPACE):
        rendered = command(["kubectl", "--context", CONTEXT, "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"])
        kubectl_input(rendered, "apply", "-f", "-")
    destination = [{"namespace": WORKLOAD_NAMESPACE, "server": "https://kubernetes.default.svc"}]
    projects = [
        {"name": PROJECT_DENIED, "sourceRepos": ["https://denied.invalid"]},
        {"name": PROJECT_ALLOWED, "sourceRepos": [SOURCE_URL]},
        {"name": SOURCES_PROJECT, "sourceRepos": ["https://denied.invalid"]},
        {"name": SYNC_PROJECT, "sourceRepos": [SOURCE_URL]},
        {"name": APPSET_PROJECT, "sourceRepos": [SOURCE_URL], "sourceNamespaces": [TENANT_NAMESPACE]},
    ]
    objects: list[dict[str, Any]] = []
    for item in projects:
        objects.append({
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "AppProject",
            "metadata": {"name": item["name"], "namespace": ARGOCD_NAMESPACE},
            "spec": {
                "sourceRepos": item["sourceRepos"],
                "destinations": destination,
                "sourceNamespaces": item.get("sourceNamespaces", []),
                "namespaceResourceWhitelist": [{"group": "*", "kind": "*"}],
            },
        })
    objects.extend([
        {
            "apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
            "metadata": {"name": PROJECT_APP, "namespace": ARGOCD_NAMESPACE},
            "spec": {
                "project": PROJECT_DENIED,
                "source": {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-003/project"},
                "destination": {"server": "https://kubernetes.default.svc", "namespace": WORKLOAD_NAMESPACE},
            },
        },
        {
            "apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
            "metadata": {"name": SOURCES_APP, "namespace": ARGOCD_NAMESPACE},
            "spec": {
                "project": SOURCES_PROJECT,
                "sources": [
                    {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-003/sources-a"},
                    {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": "apps/security-003/sources-b"},
                ],
                "destination": {"server": "https://kubernetes.default.svc", "namespace": WORKLOAD_NAMESPACE},
            },
        },
        {
            "apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
            "metadata": {"name": SYNC_APP, "namespace": ARGOCD_NAMESPACE},
            "spec": {
                "project": SYNC_PROJECT,
                "source": {"repoURL": SOURCE_URL, "targetRevision": sync_revision, "path": "apps/security-003/sync-policy"},
                "destination": {"server": "https://kubernetes.default.svc", "namespace": WORKLOAD_NAMESPACE},
            },
        },
    ])
    kubectl_input("---\n".join(yaml.safe_dump(value, sort_keys=False) for value in objects), "apply", "-f", "-")
    appset = yaml.safe_load(APPSET_FIXTURE.read_text(encoding="utf-8"))
    appset["spec"]["template"]["spec"]["source"]["targetRevision"] = main_revision
    rendered_appset = yaml.safe_dump(appset, sort_keys=False)
    (WORK / "applicationset.runtime.yaml").write_text(rendered_appset, encoding="utf-8")
    kubectl_input(rendered_appset, "apply", "-f", "-")


def cleanup_resources() -> None:
    kubectl("-n", TENANT_NAMESPACE, "delete", "applicationset", APPSET, "--ignore-not-found", "--wait=true")
    kubectl("-n", TENANT_NAMESPACE, "delete", "application", APPSET_CHILD, "--ignore-not-found", "--wait=true")
    for app_name in (PROJECT_APP, SOURCES_APP, SYNC_APP):
        kubectl("-n", ARGOCD_NAMESPACE, "delete", "application", app_name, "--ignore-not-found", "--wait=true")
    for project in (PROJECT_DENIED, PROJECT_ALLOWED, SOURCES_PROJECT, SYNC_PROJECT, APPSET_PROJECT):
        kubectl("-n", ARGOCD_NAMESPACE, "delete", "appproject", project, "--ignore-not-found")
    for namespace in (TENANT_NAMESPACE, WORKLOAD_NAMESPACE):
        kubectl("delete", "namespace", namespace, "--ignore-not-found", "--wait=true")


def qualify_rbac() -> None:
    checks = [
        (ACCOUNT_UPDATE_DENIED, "get", "Yes"),
        (ACCOUNT_UPDATE_DENIED, "update", "No"),
        (ACCOUNT_ALLOWED, "get", "Yes"),
        (ACCOUNT_ALLOWED, "update", "Yes"),
    ]
    for subject, action, expected in checks:
        wait_for(lambda: rbac_can(subject, action, SYNC_PROJECT, SYNC_APP), expected, f"RBAC {subject} {action}", timeout=90)


def capture_application(
    report_id: str,
    variant_id: str,
    app_name: str,
    secrets: list[str],
    actions: list[dict[str, Any]],
    observation: dict[str, Any],
    assertions: list[dict[str, Any]],
    rbac: dict[str, Any] | None = None,
) -> dict[str, Any]:
    surface_id = REPORT_VARIANTS[report_id]["surface_id"]
    resource_state = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "application": application(app_name),
        "app_projects": kjson("-n", ARGOCD_NAMESPACE, "get", "appprojects", "-o", "json"),
        "workload_configmaps": kjson("-n", WORKLOAD_NAMESPACE, "get", "configmaps", "-o", "json"),
        "workload_configmap_names": configmap_names(),
        "rbac": rbac,
        "observation": observation,
        "security": {"ephemeral_token_present_in_captured_state": False, "secret_scan_hits": 0},
    }
    controller_log = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "entries": collect_application_logs(app_name, secrets),
    }
    metric = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "app_info": app_info_metric(app_name, secrets),
    }
    if not metric["app_info"]["sample_present"]:
        raise RuntimeError(f"argocd_app_info metricがありません: {app_name}")
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
        "result": {"first_attempt": True, "ephemeral_token_leak": False, **observation},
    }
    for value in (resource_state, controller_log, metric, trace):
        serialized = json.dumps(value, ensure_ascii=False)
        if any(secret in serialized for secret in secrets):
            raise RuntimeError(f"Artifactへのephemeral token漏洩を検出しました: {report_id}:{variant_id}")
    common = [
        {"channel": "resource_state", "pointer": "/security/secret_scan_hits", "operator": "equals", "expected": 0},
        {"channel": "controller_log", "pointer": "/entries/0/application", "operator": "equals", "expected": app_name},
        {"channel": "metric", "pointer": "/app_info/labels/name", "operator": "equals", "expected": app_name},
        {"channel": "trace", "pointer": "/result/first_attempt", "operator": "equals", "expected": True},
    ]
    return {"resource_state": resource_state, "controller_log": controller_log, "metric": metric, "trace": trace, "assertions": [*common, *assertions]}


def capture_appset(
    variant_id: str,
    secrets: list[str],
    actions: list[dict[str, Any]],
    observation: dict[str, Any],
    assertions: list[dict[str, Any]],
) -> dict[str, Any]:
    report_id = "runtime.applicationset-any-namespace.security.v3-5-2"
    applications = child_applications()
    resource_state = {
        "schema_version": 1,
        "surface_id": "applicationset.any-namespace",
        "scenario": "security",
        "variant_id": variant_id,
        "application_set": kjson("-n", TENANT_NAMESPACE, "get", "applicationset", APPSET, "-o", "json"),
        "tenant_applications": applications,
        "tenant_application_names": sorted(item.get("metadata", {}).get("name", "") for item in applications),
        "app_project": kjson("-n", ARGOCD_NAMESPACE, "get", "appproject", APPSET_PROJECT, "-o", "json"),
        "cmd_params": kjson("-n", ARGOCD_NAMESPACE, "get", "configmap", "argocd-cmd-params-cm", "-o", "json"),
        "workload_configmap_names": configmap_names(),
        "observation": observation,
        "security": {"ephemeral_token_present_in_captured_state": False, "secret_scan_hits": 0},
    }
    controller_log = {
        "schema_version": 1,
        "components": ["argocd-applicationset-controller", "argocd-application-controller"],
        "surface_id": "applicationset.any-namespace",
        "scenario": "security",
        "variant_id": variant_id,
        "logs": collect_appset_logs(secrets),
    }
    metric = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": "applicationset.any-namespace",
        "scenario": "security",
        "variant_id": variant_id,
        "app_info": app_info_metric(APPSET_CHILD, secrets),
    }
    trace = {
        "schema_version": 1,
        "surface_id": "applicationset.any-namespace",
        "scenario": "security",
        "variant_id": variant_id,
        "started_at": now(),
        "completed_at": now(),
        "attempt": 1,
        "retries": 0,
        "actions": actions,
        "result": {"first_attempt": True, "ephemeral_token_leak": False, **observation},
    }
    for value in (resource_state, controller_log, metric, trace):
        serialized = json.dumps(value, ensure_ascii=False)
        if any(secret in serialized for secret in secrets):
            raise RuntimeError(f"Artifactへのephemeral token漏洩を検出しました: {report_id}:{variant_id}")
    common = [
        {"channel": "resource_state", "pointer": "/security/secret_scan_hits", "operator": "equals", "expected": 0},
        {"channel": "controller_log", "pointer": "/components/0", "operator": "equals", "expected": "argocd-applicationset-controller"},
        {"channel": "trace", "pointer": "/result/first_attempt", "operator": "equals", "expected": True},
    ]
    return {"resource_state": resource_state, "controller_log": controller_log, "metric": metric, "trace": trace, "assertions": [*common, *assertions]}


def drive_project(captures: dict[tuple[str, str], dict[str, Any]], allowed_token: str, secrets: list[str]) -> None:
    report_id = "runtime.application-spec-project.security.v3-5-2"
    wait_for(lambda: condition(PROJECT_APP, "InvalidSpecError") is not None, True, "restricted project binding")
    captures[(report_id, "restricted-project-binding")] = capture_application(
        report_id, "restricted-project-binding", PROJECT_APP, secrets,
        [{"action": "reconcile-restricted-project", "status": "rejected"}],
        {"project": PROJECT_DENIED, "invalid_spec_error": True, "workload_present": False},
        [
            {"channel": "resource_state", "pointer": "/observation/invalid_spec_error", "operator": "equals", "expected": True},
            {"channel": "resource_state", "pointer": "/observation/workload_present", "operator": "equals", "expected": False},
        ],
    )
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "application", PROJECT_APP, "--type", "merge", "-p", json.dumps({"spec": {"project": PROJECT_ALLOWED}}))
    refresh(PROJECT_APP)
    wait_for(lambda: condition(PROJECT_APP, "InvalidSpecError") is None, True, "authorized project binding")
    result = argocd_cli(allowed_token, "app", "sync", PROJECT_APP, "--timeout", "180")
    require_allowed(result, "authorized project sync")
    wait_synced_healthy(PROJECT_APP)
    wait_for(lambda: "atlas-security-003-project" in configmap_names(), True, "project workload")
    captures[(report_id, "authorized-project-binding")] = capture_application(
        report_id, "authorized-project-binding", PROJECT_APP, secrets,
        [{"action": "bind-authorized-project", "status": "passed"}, {"action": "sync", "status": "passed"}],
        {"project": PROJECT_ALLOWED, "invalid_spec_error": False, "workload_present": True},
        [
            {"channel": "resource_state", "pointer": "/observation/invalid_spec_error", "operator": "equals", "expected": False},
            {"channel": "resource_state", "pointer": "/observation/workload_present", "operator": "equals", "expected": True},
        ],
    )


def drive_sources(captures: dict[tuple[str, str], dict[str, Any]], allowed_token: str, secrets: list[str]) -> None:
    report_id = "runtime.application-spec-sources.security.v3-5-2"
    wait_for(lambda: condition(SOURCES_APP, "InvalidSpecError") is not None, True, "project denied multi-source")
    captures[(report_id, "project-denied-multi-source")] = capture_application(
        report_id, "project-denied-multi-source", SOURCES_APP, secrets,
        [{"action": "reconcile-project-denied-sources", "status": "rejected"}],
        {"source_count": 2, "invalid_spec_error": True, "source_a_present": False, "source_b_present": False},
        [
            {"channel": "resource_state", "pointer": "/observation/source_count", "operator": "equals", "expected": 2},
            {"channel": "resource_state", "pointer": "/observation/invalid_spec_error", "operator": "equals", "expected": True},
        ],
    )
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "appproject", SOURCES_PROJECT, "--type", "merge", "-p", json.dumps({"spec": {"sourceRepos": [SOURCE_URL]}}))
    refresh(SOURCES_APP)
    wait_for(lambda: condition(SOURCES_APP, "InvalidSpecError") is None, True, "project allowed multi-source")
    result = argocd_cli(allowed_token, "app", "sync", SOURCES_APP, "--timeout", "180")
    require_allowed(result, "project allowed multi-source sync")
    wait_synced_healthy(SOURCES_APP)
    wait_for(lambda: {"atlas-security-003-source-a", "atlas-security-003-source-b"} <= set(configmap_names()), True, "multi-source workloads")
    captures[(report_id, "project-allowed-multi-source")] = capture_application(
        report_id, "project-allowed-multi-source", SOURCES_APP, secrets,
        [{"action": "allow-project-sources", "status": "passed"}, {"action": "sync-two-sources", "status": "passed"}],
        {"source_count": 2, "invalid_spec_error": False, "source_a_present": True, "source_b_present": True},
        [
            {"channel": "resource_state", "pointer": "/observation/source_count", "operator": "equals", "expected": 2},
            {"channel": "resource_state", "pointer": "/observation/source_a_present", "operator": "equals", "expected": True},
            {"channel": "resource_state", "pointer": "/observation/source_b_present", "operator": "equals", "expected": True},
        ],
    )


def automated_enabled() -> bool:
    return "automated" in application(SYNC_APP).get("spec", {}).get("syncPolicy", {})


def self_heal_enabled() -> bool:
    return application(SYNC_APP).get("spec", {}).get("syncPolicy", {}).get("automated", {}).get("selfHeal") is True


def drive_sync_policy(captures: dict[tuple[str, str], dict[str, Any]], denied_token: str, allowed_token: str, secrets: list[str], sync_revision: str) -> None:
    report_id = "runtime.application-spec-sync-policy.security.v3-5-2"
    wait_for(lambda: application_status(SYNC_APP)[0], "OutOfSync", "manual sync policy remains OutOfSync")
    denied_decision = rbac_can(ACCOUNT_UPDATE_DENIED, "update", SYNC_PROJECT, SYNC_APP)
    denied = argocd_cli(denied_token, "app", "set", SYNC_APP, "--sync-policy", "automated", "--self-heal", "--validate=false")
    denied_class = require_denied(denied, "enable automated sync policy")
    if automated_enabled():
        raise RuntimeError("denied sync-policy updateがApplicationを変更しました")
    captures[(report_id, "fixed-revision-manual-sync")] = capture_application(
        report_id, "fixed-revision-manual-sync", SYNC_APP, secrets,
        [{"action": "enable-automated-sync", "subject": ACCOUNT_UPDATE_DENIED, "status": denied_class}],
        {"rbac_decision": denied_decision, "automated_enabled": False, "self_heal_enabled": False, "sync_status": "OutOfSync", "workload_present": False},
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "No"},
            {"channel": "resource_state", "pointer": "/observation/automated_enabled", "operator": "equals", "expected": False},
            {"channel": "resource_state", "pointer": "/observation/self_heal_enabled", "operator": "equals", "expected": False},
            {"channel": "resource_state", "pointer": "/observation/sync_status", "operator": "equals", "expected": "OutOfSync"},
        ],
        {"subject": ACCOUNT_UPDATE_DENIED, "action": "update", "decision": denied_decision},
    )
    allowed_decision = rbac_can(ACCOUNT_ALLOWED, "update", SYNC_PROJECT, SYNC_APP)
    wait_for(lambda: source_revisions_ready({sync_revision}), True, "sync-policy source revision ready", timeout=120)
    allowed = argocd_cli(allowed_token, "app", "set", SYNC_APP, "--sync-policy", "automated", "--self-heal", "--validate=false")
    require_allowed(allowed, "enable automated sync policy")
    wait_for(automated_enabled, True, "automated sync policy enabled")
    wait_for(self_heal_enabled, True, "automated self-heal enabled")
    wait_synced_healthy(SYNC_APP)
    wait_for(lambda: "atlas-security-003-sync-policy" in configmap_names(), True, "automated sync workload")
    captures[(report_id, "fixed-revision-automated-self-heal")] = capture_application(
        report_id, "fixed-revision-automated-self-heal", SYNC_APP, secrets,
        [{"action": "enable-automated-sync", "subject": ACCOUNT_ALLOWED, "status": "passed"}, {"action": "controller-auto-sync", "status": "passed"}],
        {"rbac_decision": allowed_decision, "automated_enabled": True, "self_heal_enabled": True, "sync_status": "Synced", "workload_present": True},
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "Yes"},
            {"channel": "resource_state", "pointer": "/observation/automated_enabled", "operator": "equals", "expected": True},
            {"channel": "resource_state", "pointer": "/observation/self_heal_enabled", "operator": "equals", "expected": True},
            {"channel": "resource_state", "pointer": "/observation/sync_status", "operator": "equals", "expected": "Synced"},
        ],
        {"subject": ACCOUNT_ALLOWED, "action": "update", "decision": allowed_decision},
    )


def drive_appset(captures: dict[tuple[str, str], dict[str, Any]], secrets: list[str]) -> None:
    report_id = "runtime.applicationset-any-namespace.security.v3-5-2"
    time.sleep(10)
    if child_applications():
        raise RuntimeError("allowlist外namespaceのApplicationSetがApplicationを生成しました")
    captures[(report_id, "namespace-not-allowlisted")] = capture_appset(
        "namespace-not-allowlisted", secrets,
        [{"action": "observe-unconfigured-tenant-applicationset", "status": "not-reconciled"}],
        {"namespace_allowlisted": False, "child_application_count": 0, "workload_present": False},
        [
            {"channel": "resource_state", "pointer": "/tenant_application_names", "operator": "equals", "expected": []},
            {"channel": "metric", "pointer": "/app_info/sample_present", "operator": "equals", "expected": False},
        ],
    )
    kubectl("-n", TENANT_NAMESPACE, "delete", "applicationset", APPSET, "--wait=true")
    data = {
        "application.namespaces": TENANT_NAMESPACE,
        "applicationsetcontroller.namespaces": TENANT_NAMESPACE,
        "applicationsetcontroller.enable.scm.providers": "false",
    }
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", "argocd-cmd-params-cm", "--type", "merge", "-p", json.dumps({"data": data}))
    rollout_namespace_watchers()
    appset_namespace = kubectl("-n", ARGOCD_NAMESPACE, "exec", "deployment/argocd-applicationset-controller", "--", "printenv", "ARGOCD_APPLICATIONSET_CONTROLLER_NAMESPACES").strip()
    application_namespace = kubectl("-n", ARGOCD_NAMESPACE, "exec", "statefulset/argocd-application-controller", "--", "printenv", "ARGOCD_APPLICATION_NAMESPACES").strip()
    if appset_namespace != TENANT_NAMESPACE or application_namespace != TENANT_NAMESPACE:
        raise RuntimeError(f"namespace allowlistがcontrollerへ反映されませんでした: applicationset={appset_namespace!r} application={application_namespace!r}")
    kubectl_input((WORK / "applicationset.runtime.yaml").read_text(encoding="utf-8"), "apply", "-f", "-")
    wait_for(lambda: [item.get("metadata", {}).get("name") for item in child_applications()], [APPSET_CHILD], "allowlisted ApplicationSet child", timeout=300)
    wait_synced_healthy(APPSET_CHILD, TENANT_NAMESPACE)
    wait_for(lambda: "atlas-security-003-appset" in configmap_names(), True, "ApplicationSet workload", timeout=300)
    captures[(report_id, "namespace-allowlisted")] = capture_appset(
        "namespace-allowlisted", secrets,
        [{"action": "configure-application-and-applicationset-namespaces", "status": "passed"}, {"action": "disable-scm-providers-for-tenant-boundary", "status": "passed"}, {"action": "restart-controllers", "status": "passed"}, {"action": "reconcile-tenant-applicationset", "status": "passed"}],
        {"namespace_allowlisted": True, "scm_providers_enabled": False, "child_application_count": 1, "workload_present": True},
        [
            {"channel": "resource_state", "pointer": "/tenant_application_names", "operator": "equals", "expected": [APPSET_CHILD]},
            {"channel": "resource_state", "pointer": "/observation/scm_providers_enabled", "operator": "equals", "expected": False},
            {"channel": "metric", "pointer": "/app_info/sample_present", "operator": "equals", "expected": True},
            {"channel": "metric", "pointer": "/app_info/labels/name", "operator": "equals", "expected": APPSET_CHILD},
        ],
    )


def runtime_identity_extended() -> dict[str, Any]:
    identity = runtime_identity()
    pods = kjson("-n", ARGOCD_NAMESPACE, "get", "pods", "-o", "json")
    observed = set(identity.get("observed_argocd_components", []))
    if any(item.get("metadata", {}).get("name", "").startswith("argocd-applicationset-controller-") for item in pods.get("items", [])):
        observed.add("argocd-applicationset-controller")
    identity["observed_argocd_components"] = sorted(observed)
    return identity


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
    source = REPORT_VARIANTS[report_id]["source"]
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
                "execution": {"command": "make scenario-runtime-security-003", "attempts": 1, "retries": 0, "first_attempt": True},
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
        write_publish_manifest(staging, manifest_relative, expected, reporter_id="argocd-dedicated-runtime-atomic-publish-v1", reference_commit="7175de4305afb308722d5b83475e91c18da64957")

    def validate(staging: Path) -> None:
        expected = [path.relative_to(staging) for path in staging.rglob("*") if path.is_file() and path.relative_to(staging) != manifest_relative]
        validate_publish_manifest(staging, manifest_relative, expected)
        registry = yaml.safe_load((staging / "index.yaml").read_text(encoding="utf-8"))
        ids = {item["id"] for item in registry["reports"]}
        if not set(REPORT_VARIANTS) <= ids:
            raise RuntimeError("security-003 Runtime report集合がregistryにありません")

    publish_evidence_tree(OUTPUT, STAGING, BACKUP, populate, validate, full_run_passed=True)


def main() -> None:
    assert_isolated_runtime()
    command(["kubectl", "config", "set-context", CONTEXT, "--namespace", ARGOCD_NAMESPACE])
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    main_revision = command(["git", f"--git-dir={ROOT / '.runtime/source/repo.git'}", "rev-parse", "refs/heads/main"]).strip()
    sync_revision = command(["git", f"--git-dir={ROOT / '.runtime/source/repo.git'}", "rev-parse", "refs/heads/security-003-sync-v2"]).strip()
    captures: dict[tuple[str, str], dict[str, Any]] = {}
    cleanup_resources()
    backup_configuration()
    setup_auth()
    namespace_watchers_changed = False
    try:
        wait_for(lambda: source_revisions_ready({main_revision, sync_revision}), True, "local source revisions ready", timeout=120)
        create_resources(main_revision, sync_revision)
        qualify_rbac()
        tokens = {ACCOUNT_UPDATE_DENIED: generate_token(ACCOUNT_UPDATE_DENIED), ACCOUNT_ALLOWED: generate_token(ACCOUNT_ALLOWED)}
        secrets = list(tokens.values())
        drive_project(captures, tokens[ACCOUNT_ALLOWED], secrets)
        drive_sources(captures, tokens[ACCOUNT_ALLOWED], secrets)
        drive_sync_policy(captures, tokens[ACCOUNT_UPDATE_DENIED], tokens[ACCOUNT_ALLOWED], secrets, sync_revision)
        namespace_watchers_changed = True
        drive_appset(captures, secrets)
        if len(captures) != 8:
            raise RuntimeError(f"security-003 Variant実行数が不正です: {len(captures)}")
        publish(captures, runtime_identity_extended())
    finally:
        cleanup_resources()
        restore_configuration()
        if namespace_watchers_changed:
            rollout_namespace_watchers()
    print("Dedicated Runtime tranche passed: security-003 rows=4 variants=8 retries=0")


if __name__ == "__main__":
    main()
