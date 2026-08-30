#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Closure Plan security-002の4 rowを専用Kindで実行し、原子的にEvidenceを公開する。"""

from __future__ import annotations

import hashlib
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


PROJECT = "atlas-security-002"
BASE_NAMESPACE = "atlas-security-002-workloads"
DESTINATION_NAMESPACE = "atlas-security-002-destination"
TERMINATE_APP = "atlas-security-002-terminate"
WAIT_APP = "atlas-security-002-wait"
ACTION_APP = "atlas-security-002-action"
DESTINATION_APP = "atlas-security-002-destination"
ACTION_DEPLOYMENT = "atlas-security-002-action"
SOURCE_URL = "http://source-server.argocd-atlas-source.svc.cluster.local/repo.git"
HARNESS = Path(__file__).resolve()
STAGING = ROOT / "evidence/scenarios/.runtime-next"
BACKUP = ROOT / "evidence/scenarios/.runtime-previous"
WORK = ROOT / ".runtime/scenario-security-002"
ACCOUNT_READ_DENIED = "atlas-security-002-read-denied"
ACCOUNT_SYNC_DENIED = "atlas-security-002-sync-denied"
ACCOUNT_ACTION_DENIED = "atlas-security-002-action-denied"
ACCOUNT_ALLOWED = "atlas-security-002-allowed"
SOURCE_TERMINATE = ROOT / "fixtures/scenarios/security-002/terminate/hook.yaml"
SOURCE_WAIT = ROOT / "fixtures/scenarios/security-002/wait/configmap.yaml"
SOURCE_ACTION = ROOT / "fixtures/scenarios/security-002/resource-actions/deployment.yaml"
SOURCE_DESTINATION = ROOT / "fixtures/scenarios/security-002/destination/configmap.yaml"
REPORT_VARIANTS = {
    "runtime.application-operation-terminate.security.v3-5-2": {
        "surface_id": "application.operation.terminate",
        "app": TERMINATE_APP,
        "source_by_variant": {
            "rbac-denied-terminate": SOURCE_TERMINATE,
            "rbac-allowed-terminate": SOURCE_TERMINATE,
        },
        "variants": ["rbac-denied-terminate", "rbac-allowed-terminate"],
    },
    "runtime.application-operation-wait.security.v3-5-2": {
        "surface_id": "application.operation.wait",
        "app": WAIT_APP,
        "source_by_variant": {
            "rbac-denied-wait": SOURCE_WAIT,
            "rbac-allowed-wait": SOURCE_WAIT,
        },
        "variants": ["rbac-denied-wait", "rbac-allowed-wait"],
    },
    "runtime.application-resource-actions.security.v3-5-2": {
        "surface_id": "application.resource-actions",
        "app": ACTION_APP,
        "source_by_variant": {
            "rbac-denied-deployment-restart": SOURCE_ACTION,
            "rbac-allowed-deployment-restart": SOURCE_ACTION,
        },
        "variants": ["rbac-denied-deployment-restart", "rbac-allowed-deployment-restart"],
    },
    "runtime.application-spec-destination.security.v3-5-2": {
        "surface_id": "application.spec.destination",
        "app": DESTINATION_APP,
        "source_by_variant": {
            "project-denied-destination": SOURCE_DESTINATION,
            "project-allowed-destination": SOURCE_DESTINATION,
        },
        "variants": ["project-denied-destination", "project-allowed-destination"],
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


def app(app_name: str) -> dict[str, Any]:
    return kjson("-n", ARGOCD_NAMESPACE, "get", "application", app_name, "-o", "json")


def app_status(app_name: str) -> tuple[str, str]:
    status = app(app_name).get("status", {})
    return status.get("sync", {}).get("status", ""), status.get("health", {}).get("status", "")


def wait_synced_healthy(app_name: str) -> None:
    wait_for(lambda: app_status(app_name), ("Synced", "Healthy"), f"{app_name} Synced Healthy")


def app_condition(app_name: str, condition_type: str) -> dict[str, Any] | None:
    conditions = app(app_name).get("status", {}).get("conditions", [])
    return next((value for value in conditions if value.get("type") == condition_type), None)


def rbac_can(subject: str, action: str, app_name: str) -> str:
    result = command_result([
        "kubectl", "--context", CONTEXT, "-n", ARGOCD_NAMESPACE, "exec", "deployment/argocd-server", "--",
        "argocd", "admin", "settings", "rbac", "can", subject, action, "applications", f"{PROJECT}/{app_name}",
        "--namespace", ARGOCD_NAMESPACE,
    ])
    output = (result.stdout + "\n" + result.stderr).strip()
    if "Yes" in output:
        return "Yes"
    if "No" in output:
        return "No"
    raise RuntimeError(f"Argo CD RBAC decisionを取得できません: subject={subject} action={action} rc={result.returncode}")


def setup_auth() -> None:
    for name in ("argocd-cm", "argocd-rbac-cm"):
        write_json(WORK / f"{name}.backup.json", kjson("-n", ARGOCD_NAMESPACE, "get", "configmap", name, "-o", "json"))
    write_json(WORK / "argocd-secret.backup.json", kjson("-n", ARGOCD_NAMESPACE, "get", "secret", "argocd-secret", "-o", "json"))
    accounts = {
        f"accounts.{ACCOUNT_READ_DENIED}": "apiKey",
        f"accounts.{ACCOUNT_SYNC_DENIED}": "apiKey",
        f"accounts.{ACCOUNT_ACTION_DENIED}": "apiKey",
        f"accounts.{ACCOUNT_ALLOWED}": "apiKey",
    }
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", "argocd-cm", "--type", "merge", "-p", json.dumps({"data": accounts}))
    action = "action/apps/Deployment/restart"
    policy = "\n".join([
        f"p, {ACCOUNT_READ_DENIED}, applications, get, {PROJECT}/*, deny",
        f"p, {ACCOUNT_SYNC_DENIED}, applications, get, {PROJECT}/*, allow",
        f"p, {ACCOUNT_SYNC_DENIED}, applications, sync, {PROJECT}/*, deny",
        f"p, {ACCOUNT_ACTION_DENIED}, applications, get, {PROJECT}/*, allow",
        f"p, {ACCOUNT_ACTION_DENIED}, applications, {action}, {PROJECT}/*, deny",
        f"p, {ACCOUNT_ALLOWED}, applications, get, {PROJECT}/*, allow",
        f"p, {ACCOUNT_ALLOWED}, applications, sync, {PROJECT}/*, allow",
        f"p, {ACCOUNT_ALLOWED}, applications, {action}, {PROJECT}/*, allow",
    ])
    data = {"policy.csv": policy, "policy.default": "role:atlas-empty", "policy.matchMode": "glob", "scopes": "[groups]"}
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", "argocd-rbac-cm", "--type", "merge", "-p", json.dumps({"data": data}))


def restore_auth() -> None:
    for name in ("argocd-cm", "argocd-rbac-cm"):
        path = WORK / f"{name}.backup.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8")).get("data", {})
            kubectl("-n", ARGOCD_NAMESPACE, "patch", "configmap", name, "--type", "json", "-p", json.dumps([{"op": "replace", "path": "/data", "value": data}]))
    secret_path = WORK / "argocd-secret.backup.json"
    if secret_path.is_file():
        data = json.loads(secret_path.read_text(encoding="utf-8")).get("data", {})
        kubectl("-n", ARGOCD_NAMESPACE, "patch", "secret", "argocd-secret", "--type", "json", "-p", json.dumps([{"op": "replace", "path": "/data", "value": data}]))


def qualify_rbac() -> None:
    action = "action/apps/Deployment/restart"
    checks = [
        (ACCOUNT_READ_DENIED, "get", WAIT_APP, "No"),
        (ACCOUNT_SYNC_DENIED, "get", TERMINATE_APP, "Yes"),
        (ACCOUNT_SYNC_DENIED, "sync", TERMINATE_APP, "No"),
        (ACCOUNT_ACTION_DENIED, "get", ACTION_APP, "Yes"),
        (ACCOUNT_ACTION_DENIED, action, ACTION_APP, "No"),
        (ACCOUNT_ALLOWED, "get", WAIT_APP, "Yes"),
        (ACCOUNT_ALLOWED, "sync", TERMINATE_APP, "Yes"),
        (ACCOUNT_ALLOWED, action, ACTION_APP, "Yes"),
    ]
    for subject, action_name, app_name, expected in checks:
        wait_for(lambda: rbac_can(subject, action_name, app_name), expected, f"RBAC {subject} {action_name}", timeout=90)


def generate_token(account: str) -> str:
    result = command_result([
        "argocd", "account", "generate-token", "--core", "--kube-context", CONTEXT, "--account", account,
    ])
    token = result.stdout.strip()
    if result.returncode != 0 or len(token) < 100:
        raise RuntimeError(f"local account tokenを生成できません: account={account} rc={result.returncode}")
    return token


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


def create_resources(main_revision: str) -> None:
    for namespace in (BASE_NAMESPACE, DESTINATION_NAMESPACE):
        rendered = command(["kubectl", "--context", CONTEXT, "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"])
        kubectl_input(rendered, "apply", "-f", "-")
    project = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AppProject",
        "metadata": {"name": PROJECT, "namespace": ARGOCD_NAMESPACE},
        "spec": {
            "sourceRepos": [SOURCE_URL],
            "destinations": [{"namespace": BASE_NAMESPACE, "server": "https://kubernetes.default.svc"}],
            "namespaceResourceWhitelist": [{"group": "*", "kind": "*"}],
        },
    }
    definitions = [
        (TERMINATE_APP, "terminate", BASE_NAMESPACE),
        (WAIT_APP, "wait", BASE_NAMESPACE),
        (ACTION_APP, "resource-actions", BASE_NAMESPACE),
        (DESTINATION_APP, "destination", DESTINATION_NAMESPACE),
    ]
    applications = []
    for name, path, namespace in definitions:
        applications.append({
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {"name": name, "namespace": ARGOCD_NAMESPACE},
            "spec": {
                "project": PROJECT,
                "source": {"repoURL": SOURCE_URL, "targetRevision": main_revision, "path": f"apps/security-002/{path}"},
                "destination": {"server": "https://kubernetes.default.svc", "namespace": namespace},
            },
        })
    objects = "---\n".join(yaml.safe_dump(value, sort_keys=False) for value in [project, *applications])
    kubectl_input(objects, "apply", "-f", "-")


def cleanup_resources() -> None:
    for app_name in (TERMINATE_APP, WAIT_APP, ACTION_APP, DESTINATION_APP):
        kubectl("-n", ARGOCD_NAMESPACE, "delete", "application", app_name, "--ignore-not-found", "--wait=true")
    kubectl("-n", ARGOCD_NAMESPACE, "delete", "appproject", PROJECT, "--ignore-not-found")
    for namespace in (BASE_NAMESPACE, DESTINATION_NAMESPACE):
        kubectl("delete", "namespace", namespace, "--ignore-not-found", "--wait=true")


def collect_logs(app_name: str, secrets: list[str]) -> list[dict[str, Any]]:
    raw = kubectl("-n", ARGOCD_NAMESPACE, "logs", "statefulset/argocd-application-controller", "--since=20m")
    if any(secret in raw for secret in secrets):
        raise RuntimeError("Controller logへのephemeral token漏洩を検出しました")
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


def collect_metric(app_name: str, secrets: list[str]) -> dict[str, Any]:
    raw = kubectl("get", "--raw", "/api/v1/namespaces/argocd/services/http:argocd-metrics:8082/proxy/metrics")
    if any(secret in raw for secret in secrets):
        raise RuntimeError("Prometheus metricへのephemeral token漏洩を検出しました")
    line = next((value for value in raw.splitlines() if value.startswith("argocd_app_info{") and f'name="{app_name}"' in value), None)
    if line is None:
        raise RuntimeError(f"argocd_app_info metricがありません: {app_name}")
    return {"sample": line, "labels": parse_prometheus_labels(line), "value": 1}


def list_or_empty(namespace: str, resource: str) -> dict[str, Any]:
    return kjson("-n", namespace, "get", resource, "-o", "json")


def capture(
    report_id: str,
    variant_id: str,
    app_name: str,
    secrets: list[str],
    started_at: str,
    actions: list[dict[str, Any]],
    observation: dict[str, Any],
    assertions: list[dict[str, Any]],
    rbac: dict[str, Any] | None = None,
) -> dict[str, Any]:
    surface_id = REPORT_VARIANTS[report_id]["surface_id"]
    destination_configmaps = list_or_empty(DESTINATION_NAMESPACE, "configmaps")
    destination_subject_configmaps = sorted(
        item.get("metadata", {}).get("name", "")
        for item in destination_configmaps.get("items", [])
        if item.get("metadata", {}).get("name") == "atlas-security-002-destination"
    )
    resource_state = {
        "schema_version": 1,
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "application": app(app_name),
        "base_configmaps": list_or_empty(BASE_NAMESPACE, "configmaps"),
        "destination_configmaps": destination_configmaps,
        "destination_subject_configmaps": destination_subject_configmaps,
        "deployments": list_or_empty(BASE_NAMESPACE, "deployments.apps"),
        "jobs": list_or_empty(BASE_NAMESPACE, "jobs.batch"),
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
        "entries": collect_logs(app_name, secrets),
    }
    metric = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": surface_id,
        "scenario": "security",
        "variant_id": variant_id,
        "app_info": collect_metric(app_name, secrets),
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


def drive_destination(captures: dict[tuple[str, str], dict[str, Any]], allowed_token: str, secrets: list[str]) -> None:
    report_id = "runtime.application-spec-destination.security.v3-5-2"
    wait_for(lambda: app_condition(DESTINATION_APP, "InvalidSpecError") is not None, True, "project denied destination")
    condition = app_condition(DESTINATION_APP, "InvalidSpecError")
    assert condition is not None
    denied_observation = {
        "project_destination_allowed": False,
        "invalid_spec_error": True,
        "destination_configmap_present": False,
    }
    captures[(report_id, "project-denied-destination")] = capture(
        report_id, "project-denied-destination", DESTINATION_APP, secrets, now(),
        [{"action": "reconcile-project-denied-destination", "condition": condition.get("type"), "status": "passed"}],
        denied_observation,
        [
            {"channel": "resource_state", "pointer": "/observation/project_destination_allowed", "operator": "equals", "expected": False},
            {"channel": "resource_state", "pointer": "/observation/invalid_spec_error", "operator": "equals", "expected": True},
            {"channel": "resource_state", "pointer": "/destination_subject_configmaps", "operator": "equals", "expected": []},
        ],
    )
    destinations = [
        {"namespace": BASE_NAMESPACE, "server": "https://kubernetes.default.svc"},
        {"namespace": DESTINATION_NAMESPACE, "server": "https://kubernetes.default.svc"},
    ]
    kubectl("-n", ARGOCD_NAMESPACE, "patch", "appproject", PROJECT, "--type", "merge", "-p", json.dumps({"spec": {"destinations": destinations}}))
    kubectl("-n", ARGOCD_NAMESPACE, "annotate", "application", DESTINATION_APP, "argocd.argoproj.io/refresh=hard", "--overwrite")
    wait_for(lambda: app_condition(DESTINATION_APP, "InvalidSpecError") is None, True, "project allowed destination refresh")
    result = argocd_cli(allowed_token, "app", "sync", DESTINATION_APP, "--timeout", "180")
    require_allowed(result, "sync project-allowed destination")
    wait_synced_healthy(DESTINATION_APP)
    wait_for(
        lambda: any(item.get("metadata", {}).get("name") == "atlas-security-002-destination" for item in list_or_empty(DESTINATION_NAMESPACE, "configmaps").get("items", [])),
        True,
        "destination configmap created",
    )
    allowed_observation = {
        "project_destination_allowed": True,
        "invalid_spec_error": False,
        "destination_configmap_present": True,
    }
    captures[(report_id, "project-allowed-destination")] = capture(
        report_id, "project-allowed-destination", DESTINATION_APP, secrets, now(),
        [{"action": "allow-project-destination", "status": "passed"}, {"action": "sync-through-argocd-api", "status": "passed"}],
        allowed_observation,
        [
            {"channel": "resource_state", "pointer": "/observation/project_destination_allowed", "operator": "equals", "expected": True},
            {"channel": "resource_state", "pointer": "/observation/destination_configmap_present", "operator": "equals", "expected": True},
            {"channel": "resource_state", "pointer": "/destination_subject_configmaps", "operator": "equals", "expected": ["atlas-security-002-destination"]},
        ],
    )


def drive_wait(captures: dict[tuple[str, str], dict[str, Any]], denied_token: str, allowed_token: str, secrets: list[str]) -> None:
    report_id = "runtime.application-operation-wait.security.v3-5-2"
    result = argocd_cli(allowed_token, "app", "sync", WAIT_APP, "--timeout", "180")
    require_allowed(result, "prepare wait application")
    wait_synced_healthy(WAIT_APP)
    denied_decision = rbac_can(ACCOUNT_READ_DENIED, "get", WAIT_APP)
    denied = argocd_cli(denied_token, "app", "wait", WAIT_APP, "--sync", "--health", "--timeout", "15", timeout=45)
    denied_class = require_denied(denied, "application wait")
    denied_observation = {"rbac_decision": denied_decision, "wait_exit_code": denied.returncode, "wait_error": denied_class, "synced_healthy": True}
    captures[(report_id, "rbac-denied-wait")] = capture(
        report_id, "rbac-denied-wait", WAIT_APP, secrets, now(),
        [{"action": "invoke-argocd-app-wait", "subject": ACCOUNT_READ_DENIED, "status": denied_class}],
        denied_observation,
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "No"},
            {"channel": "resource_state", "pointer": "/observation/wait_error", "operator": "equals", "expected": "permission-denied"},
        ],
        {"subject": ACCOUNT_READ_DENIED, "action": "get", "decision": denied_decision},
    )
    allowed_decision = rbac_can(ACCOUNT_ALLOWED, "get", WAIT_APP)
    allowed = argocd_cli(allowed_token, "app", "wait", WAIT_APP, "--sync", "--health", "--timeout", "30", timeout=60)
    require_allowed(allowed, "application wait")
    allowed_observation = {"rbac_decision": allowed_decision, "wait_exit_code": 0, "wait_completed": True, "synced_healthy": True}
    captures[(report_id, "rbac-allowed-wait")] = capture(
        report_id, "rbac-allowed-wait", WAIT_APP, secrets, now(),
        [{"action": "invoke-argocd-app-wait", "subject": ACCOUNT_ALLOWED, "status": "passed"}],
        allowed_observation,
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "Yes"},
            {"channel": "resource_state", "pointer": "/observation/wait_completed", "operator": "equals", "expected": True},
        ],
        {"subject": ACCOUNT_ALLOWED, "action": "get", "decision": allowed_decision},
    )


def restart_annotation() -> str:
    deployment = kjson("-n", BASE_NAMESPACE, "get", "deployment", ACTION_DEPLOYMENT, "-o", "json")
    return str(deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {}).get("kubectl.kubernetes.io/restartedAt", ""))


def action_command(token: str) -> subprocess.CompletedProcess[str]:
    return argocd_cli(
        token, "app", "actions", "run", ACTION_APP, "restart", "--kind", "Deployment", "--group", "apps",
        "--resource-name", ACTION_DEPLOYMENT, "--namespace", BASE_NAMESPACE,
    )


def drive_action(captures: dict[tuple[str, str], dict[str, Any]], denied_token: str, allowed_token: str, secrets: list[str]) -> None:
    report_id = "runtime.application-resource-actions.security.v3-5-2"
    result = argocd_cli(allowed_token, "app", "sync", ACTION_APP, "--timeout", "180")
    require_allowed(result, "prepare resource action application")
    wait_synced_healthy(ACTION_APP)
    before = restart_annotation()
    action_name = "action/apps/Deployment/restart"
    denied_decision = rbac_can(ACCOUNT_ACTION_DENIED, action_name, ACTION_APP)
    denied = action_command(denied_token)
    denied_class = require_denied(denied, "deployment restart action")
    if restart_annotation() != before:
        raise RuntimeError("denied resource actionがDeploymentを変更しました")
    denied_observation = {"rbac_decision": denied_decision, "action_error": denied_class, "restart_annotation_changed": False}
    captures[(report_id, "rbac-denied-deployment-restart")] = capture(
        report_id, "rbac-denied-deployment-restart", ACTION_APP, secrets, now(),
        [{"action": "invoke-deployment-restart", "subject": ACCOUNT_ACTION_DENIED, "status": denied_class}],
        denied_observation,
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "No"},
            {"channel": "resource_state", "pointer": "/observation/restart_annotation_changed", "operator": "equals", "expected": False},
        ],
        {"subject": ACCOUNT_ACTION_DENIED, "action": action_name, "decision": denied_decision},
    )
    allowed_decision = rbac_can(ACCOUNT_ALLOWED, action_name, ACTION_APP)
    allowed = action_command(allowed_token)
    require_allowed(allowed, "deployment restart action")
    wait_for(lambda: restart_annotation() != before and bool(restart_annotation()), True, "authorized Deployment restart")
    allowed_observation = {"rbac_decision": allowed_decision, "action_exit_code": 0, "restart_annotation_changed": True}
    captures[(report_id, "rbac-allowed-deployment-restart")] = capture(
        report_id, "rbac-allowed-deployment-restart", ACTION_APP, secrets, now(),
        [{"action": "invoke-deployment-restart", "subject": ACCOUNT_ALLOWED, "status": "passed"}],
        allowed_observation,
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "Yes"},
            {"channel": "resource_state", "pointer": "/observation/restart_annotation_changed", "operator": "equals", "expected": True},
        ],
        {"subject": ACCOUNT_ALLOWED, "action": action_name, "decision": allowed_decision},
    )


def operation_phase() -> str:
    return str(app(TERMINATE_APP).get("status", {}).get("operationState", {}).get("phase", ""))


def operation_message() -> str:
    return str(app(TERMINATE_APP).get("status", {}).get("operationState", {}).get("message", ""))


def drive_terminate(captures: dict[tuple[str, str], dict[str, Any]], denied_token: str, allowed_token: str, secrets: list[str]) -> None:
    report_id = "runtime.application-operation-terminate.security.v3-5-2"
    started = argocd_cli(allowed_token, "app", "sync", TERMINATE_APP, "--async")
    require_allowed(started, "start long-running sync")
    wait_for(lambda: operation_phase(), "Running", "long-running sync operation")
    denied_decision = rbac_can(ACCOUNT_SYNC_DENIED, "sync", TERMINATE_APP)
    denied = argocd_cli(denied_token, "app", "terminate-op", TERMINATE_APP)
    denied_class = require_denied(denied, "terminate operation")
    if operation_phase() != "Running":
        raise RuntimeError("denied terminate-op後にoperationがRunningを維持していません")
    denied_observation = {"rbac_decision": denied_decision, "terminate_error": denied_class, "operation_running": True, "operation_terminated": False}
    captures[(report_id, "rbac-denied-terminate")] = capture(
        report_id, "rbac-denied-terminate", TERMINATE_APP, secrets, now(),
        [{"action": "invoke-terminate-op", "subject": ACCOUNT_SYNC_DENIED, "status": denied_class}],
        denied_observation,
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "No"},
            {"channel": "resource_state", "pointer": "/observation/operation_running", "operator": "equals", "expected": True},
        ],
        {"subject": ACCOUNT_SYNC_DENIED, "action": "sync", "decision": denied_decision},
    )
    allowed_decision = rbac_can(ACCOUNT_ALLOWED, "sync", TERMINATE_APP)
    allowed = argocd_cli(allowed_token, "app", "terminate-op", TERMINATE_APP)
    require_allowed(allowed, "terminate operation")
    wait_for(lambda: "Operation terminated" in operation_message(), True, "authorized operation termination")
    phase = operation_phase()
    allowed_observation = {
        "rbac_decision": allowed_decision,
        "terminate_exit_code": 0,
        "operation_running": False,
        "operation_terminated": True,
        "terminal_phase": phase,
    }
    captures[(report_id, "rbac-allowed-terminate")] = capture(
        report_id, "rbac-allowed-terminate", TERMINATE_APP, secrets, now(),
        [{"action": "invoke-terminate-op", "subject": ACCOUNT_ALLOWED, "status": "passed"}, {"action": "observe-controller-termination", "phase": phase, "status": "passed"}],
        allowed_observation,
        [
            {"channel": "resource_state", "pointer": "/rbac/decision", "operator": "equals", "expected": "Yes"},
            {"channel": "resource_state", "pointer": "/observation/operation_terminated", "operator": "equals", "expected": True},
        ],
        {"subject": ACCOUNT_ALLOWED, "action": "sync", "decision": allowed_decision},
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
                "execution": {"command": "make scenario-runtime-security-002", "attempts": 1, "retries": 0, "first_attempt": True},
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
            raise RuntimeError("security-002 Runtime report集合がregistryにありません")

    publish_evidence_tree(OUTPUT, STAGING, BACKUP, populate, validate, full_run_passed=True)


def main() -> None:
    assert_isolated_runtime()
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    main_revision = command(["git", f"--git-dir={ROOT / '.runtime/source/repo.git'}", "rev-parse", "refs/heads/main"]).strip()
    captures: dict[tuple[str, str], dict[str, Any]] = {}
    cleanup_resources()
    setup_auth()
    try:
        create_resources(main_revision)
        qualify_rbac()
        tokens = {
            ACCOUNT_READ_DENIED: generate_token(ACCOUNT_READ_DENIED),
            ACCOUNT_SYNC_DENIED: generate_token(ACCOUNT_SYNC_DENIED),
            ACCOUNT_ACTION_DENIED: generate_token(ACCOUNT_ACTION_DENIED),
            ACCOUNT_ALLOWED: generate_token(ACCOUNT_ALLOWED),
        }
        secrets = list(tokens.values())
        drive_destination(captures, tokens[ACCOUNT_ALLOWED], secrets)
        drive_wait(captures, tokens[ACCOUNT_READ_DENIED], tokens[ACCOUNT_ALLOWED], secrets)
        drive_action(captures, tokens[ACCOUNT_ACTION_DENIED], tokens[ACCOUNT_ALLOWED], secrets)
        drive_terminate(captures, tokens[ACCOUNT_SYNC_DENIED], tokens[ACCOUNT_ALLOWED], secrets)
        if len(captures) != 8:
            raise RuntimeError(f"security-002 Variant実行数が不正です: {len(captures)}")
        publish(captures, runtime_identity())
    finally:
        cleanup_resources()
        restore_auth()
    print("Dedicated Runtime tranche passed: security-002 rows=4 variants=8 retries=0")


if __name__ == "__main__":
    main()
