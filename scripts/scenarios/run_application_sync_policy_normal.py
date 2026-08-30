#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Application syncPolicy normal rowを専用Kindで実行し、原子的にEvidenceを公開する。"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib.atomic_evidence_publish import (  # noqa: E402
    publish_evidence_tree,
    validate_publish_manifest,
    write_publish_manifest,
)


CONTEXT = "kind-argocd-atlas-v3-5-2"
CLUSTER = "argocd-atlas-v3-5-2"
APP = "atlas-application"
NAMESPACE = "atlas-application"
ARGOCD_NAMESPACE = "argocd"
REPORT_ID = "runtime.application-spec-sync-policy.normal.v3-5-2"
SOURCE = ROOT / "fixtures/scenarios/application-sync-policy-normal/configmap.yaml"
HARNESS = Path(__file__).resolve()
OUTPUT = ROOT / "evidence/scenarios/runtime"
STAGING = ROOT / "evidence/scenarios/.runtime-next"
BACKUP = ROOT / "evidence/scenarios/.runtime-previous"
WORK = ROOT / ".runtime/scenario-application-sync-policy-normal"
VARIANTS = ["fixed-revision-manual-sync", "fixed-revision-automated-self-heal"]
ARTIFACT_KINDS = {
    "resource_state": "kubernetes-resource-state",
    "controller_log": "argocd-controller-log",
    "metric": "argocd-prometheus-metric",
    "trace": "scenario-execution-trace",
}


def command(args: list[str], *, input_text: str | None = None) -> str:
    result = subprocess.run(args, input=input_text, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}")
    return result.stdout


def kubectl(*args: str) -> str:
    return command(["kubectl", "--context", CONTEXT, *args])


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {"path": path.relative_to(ROOT).as_posix(), "digest": digest(path), "bytes": path.stat().st_size}


def published_binding(staged_path: Path, staging_root: Path) -> dict[str, Any]:
    final_path = OUTPUT / staged_path.relative_to(staging_root)
    return {"path": final_path.relative_to(ROOT).as_posix(), "digest": digest(staged_path), "bytes": staged_path.stat().st_size}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def load_json_output(*args: str) -> dict[str, Any]:
    value = json.loads(kubectl(*args))
    if not isinstance(value, dict):
        raise RuntimeError(f"Kubernetes response is not an object: {' '.join(args)}")
    return value


def wait_for(read, expected: Any, label: str, timeout: int = 240) -> Any:
    deadline = time.monotonic() + timeout
    observed = None
    while time.monotonic() < deadline:
        observed = read()
        if observed == expected:
            return observed
        time.sleep(2)
    raise RuntimeError(f"oracle timeout: {label}: expected={expected!r} observed={observed!r}")


def assert_isolated_runtime() -> None:
    clusters = command(["kind", "get", "clusters"]).splitlines()
    if CLUSTER not in clusters:
        raise RuntimeError(f"専用Kind clusterがありません: {CLUSTER}")
    current = command(["kubectl", "config", "current-context"]).strip()
    if current != CONTEXT:
        raise RuntimeError(f"外部contextへの操作を拒否しました: current={current} required={CONTEXT}")
    kubectl("get", "namespace", "kube-system", "-o", "name")


def refresh() -> None:
    kubectl(
        "-n", ARGOCD_NAMESPACE, "annotate", "application", APP,
        "argocd.argoproj.io/refresh=hard", "--overwrite",
    )


def app_status() -> tuple[str, str]:
    app = load_json_output("-n", ARGOCD_NAMESPACE, "get", "application", APP, "-o", "json")
    status = app.get("status", {})
    return status.get("sync", {}).get("status", ""), status.get("health", {}).get("status", "")


def configmap_release() -> str:
    configmap = load_json_output("-n", NAMESPACE, "get", "configmap", APP, "-o", "json")
    return str(configmap.get("data", {}).get("release", ""))


def parse_prometheus_labels(line: str) -> dict[str, str]:
    match = re.match(r"^[^{]+\{(.*)\}\s+[-+0-9.eE]+$", line)
    if match is None:
        raise RuntimeError("argocd_app_info metricをparseできません")
    return {key: value for key, value in re.findall(r'(\w+)="([^"]*)"', match.group(1))}


def capture_variant(variant_id: str, started_at: str, actions: list[dict[str, Any]], autosync: str) -> dict[str, Any]:
    variant_root = WORK / variant_id
    if variant_root.exists():
        shutil.rmtree(variant_root)
    variant_root.mkdir(parents=True)
    application = load_json_output("-n", ARGOCD_NAMESPACE, "get", "application", APP, "-o", "json")
    configmap = load_json_output("-n", NAMESPACE, "get", "configmap", APP, "-o", "json")
    resource_state = {
        "schema_version": 1,
        "surface_id": "application.spec.sync-policy",
        "scenario": "normal",
        "variant_id": variant_id,
        "application": application,
        "configmap": configmap,
    }
    write_json(variant_root / "resource_state.json", resource_state)

    raw_logs = kubectl(
        "-n", ARGOCD_NAMESPACE, "logs", "statefulset/argocd-application-controller", "--since=10m",
    )
    entries = []
    for line in raw_logs.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("application") == APP:
            entries.append(entry)
    if not entries:
        raise RuntimeError(f"Controller logにApplication identityがありません: {variant_id}")
    controller_log = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": "application.spec.sync-policy",
        "scenario": "normal",
        "variant_id": variant_id,
        "entries": entries,
    }
    write_json(variant_root / "controller_log.json", controller_log)

    raw_metrics = kubectl(
        "get", "--raw", "/api/v1/namespaces/argocd/services/http:argocd-metrics:8082/proxy/metrics",
    )
    app_info_line = next(
        (line for line in raw_metrics.splitlines() if line.startswith("argocd_app_info{") and f'name="{APP}"' in line),
        None,
    )
    if app_info_line is None:
        raise RuntimeError(f"argocd_app_info metricがありません: {variant_id}")
    labels = parse_prometheus_labels(app_info_line)
    if labels.get("autosync_enabled") != autosync:
        raise RuntimeError(f"autosync metricが期待値と一致しません: expected={autosync} actual={labels.get('autosync_enabled')}")
    metric = {
        "schema_version": 1,
        "component": "argocd-application-controller",
        "surface_id": "application.spec.sync-policy",
        "scenario": "normal",
        "variant_id": variant_id,
        "app_info": {"sample": app_info_line, "labels": labels, "value": 1},
    }
    write_json(variant_root / "metric.json", metric)

    trace = {
        "schema_version": 1,
        "surface_id": "application.spec.sync-policy",
        "scenario": "normal",
        "variant_id": variant_id,
        "started_at": started_at,
        "completed_at": now(),
        "attempt": 1,
        "retries": 0,
        "actions": actions,
        "result": {
            "first_attempt": True,
            "sync_status": application["status"]["sync"]["status"],
            "health_status": application["status"]["health"]["status"],
            "live_release": configmap["data"]["release"],
            "autosync_enabled": labels["autosync_enabled"],
        },
    }
    write_json(variant_root / "trace.json", trace)
    return {
        "resource_state": resource_state,
        "controller_log": controller_log,
        "metric": metric,
        "trace": trace,
    }


def runtime_identity() -> dict[str, Any]:
    version = json.loads(kubectl("version", "-o", "json"))
    nodes = load_json_output("get", "nodes", "-o", "json")
    kubelets = sorted({item["status"]["nodeInfo"]["kubeletVersion"] for item in nodes["items"]})
    namespace = load_json_output("get", "namespace", "kube-system", "-o", "json")
    pods = load_json_output("-n", ARGOCD_NAMESPACE, "get", "pods", "-o", "json")
    topology = []
    observed = set()
    for pod in pods["items"]:
        name = pod["metadata"]["name"]
        for component in ("argocd-application-controller", "argocd-repo-server"):
            if name.startswith(component + "-") or name == component:
                observed.add(component)
        topology.append({
            "name": name,
            "uid": pod["metadata"]["uid"],
            "node": pod.get("spec", {}).get("nodeName"),
            "images": [container["image"] for container in pod.get("spec", {}).get("containers", [])],
        })
    topology_digest = "sha256:" + hashlib.sha256(
        json.dumps(sorted(topology, key=lambda item: item["name"]), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "profile": "cluster",
        "real_argocd_kubernetes_runtime": True,
        "cluster_name": CLUSTER,
        "kubernetes_context": CONTEXT,
        "argocd_version": (ROOT / ".runtime/downloads/argocd-VERSION").read_text(encoding="utf-8").strip(),
        "kubernetes_api_server_version": version["serverVersion"]["gitVersion"],
        "kubernetes_kubelet_version": ",".join(kubelets),
        "cluster_uid": namespace["metadata"]["uid"],
        "topology_digest": topology_digest,
        "observed_argocd_components": sorted(observed),
    }


def oracle_assertions(variant_id: str, autosync: str) -> list[dict[str, Any]]:
    assertions = [
        {"channel": "resource_state", "pointer": "/application/status/sync/status", "operator": "equals", "expected": "Synced"},
        {"channel": "resource_state", "pointer": "/application/status/health/status", "operator": "equals", "expected": "Healthy"},
        {"channel": "resource_state", "pointer": "/configmap/data/release", "operator": "equals", "expected": "v1"},
        {"channel": "controller_log", "pointer": "/entries/0/application", "operator": "equals", "expected": APP},
        {"channel": "metric", "pointer": "/app_info/labels/autosync_enabled", "operator": "equals", "expected": autosync},
        {"channel": "trace", "pointer": "/result/first_attempt", "operator": "equals", "expected": True},
    ]
    if variant_id == "fixed-revision-automated-self-heal":
        assertions.append({"channel": "resource_state", "pointer": "/application/spec/syncPolicy/automated/selfHeal", "operator": "equals", "expected": True})
    return assertions


def build_variant(staging: Path, variant_id: str, values: dict[str, Any], autosync: str) -> dict[str, Any]:
    target_root = staging / "artifacts" / REPORT_ID / variant_id
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True)
    artifacts = {}
    for channel in ARTIFACT_KINDS:
        target = target_root / f"{channel}.json"
        write_json(target, values[channel])
        artifacts[channel] = {
            **published_binding(target, staging),
            "kind": ARTIFACT_KINDS[channel],
            "owner": f"{REPORT_ID}:{variant_id}:{channel}",
        }
    return {
        "variant_id": variant_id,
        "attempts": 1,
        "outcome": "expected",
        "final_status": "passed",
        "error": None,
        "oracle": {"status": "pass", "assertions": oracle_assertions(variant_id, autosync)},
        "source": {**binding(SOURCE), "owner": f"{REPORT_ID}:{variant_id}:source"},
        "harness": {**binding(HARNESS), "owner": f"{REPORT_ID}:{variant_id}:harness"},
        "artifacts": artifacts,
    }


def publish(captures: dict[str, dict[str, Any]], identity: dict[str, Any]) -> None:
    report_relative = Path("reports") / f"{REPORT_ID}.json"
    manifest_relative = Path("atomic-publish-manifest.json")

    def populate(staging: Path) -> None:
        variants = [
            build_variant(staging, VARIANTS[0], captures[VARIANTS[0]], "false"),
            build_variant(staging, VARIANTS[1], captures[VARIANTS[1]], "true"),
        ]
        report = {
            "schema_version": 1,
            "id": REPORT_ID,
            "atlas_id": "argocd-reference-atlas",
            "surface_id": "application.spec.sync-policy",
            "scenario": "normal",
            "status": "passed-runtime-execution-pending-authority-review",
            "execution": {
                "command": "make scenario-runtime-application-sync-policy-normal",
                "attempts": 1,
                "retries": 0,
                "first_attempt": True,
            },
            "runtime_identity": identity,
            "variant_denominator": {
                "source": "definitive/scenario-variant-contract.yaml",
                "status": "runtime-declared-pending-authority-human-review",
                "declared_variant_ids": VARIANTS,
                "all_declared_variants_executed": True,
                "authority_exhaustive": False,
                "completion_eligible": False,
            },
            "variants": variants,
        }
        report_path = staging / report_relative
        write_json(report_path, report)
        report_reference = {"id": REPORT_ID, **published_binding(report_path, staging)}
        existing = yaml.safe_load((OUTPUT / "index.yaml").read_text(encoding="utf-8"))
        references = [item for item in existing.get("reports", []) if item["id"] != REPORT_ID]
        references.append(report_reference)
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
        if REPORT_ID not in {item["id"] for item in registry["reports"]}:
            raise RuntimeError("Dedicated Runtime registryのreport bindingが不正です")

    publish_evidence_tree(OUTPUT, STAGING, BACKUP, populate, validate, full_run_passed=True)


def main() -> None:
    assert_isolated_runtime()
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    captures: dict[str, dict[str, Any]] = {}
    command([str(ROOT / "scripts/run-lab.sh"), "application", "cleanup"])
    try:
        manual_started = now()
        command([str(ROOT / "scripts/run-lab.sh"), "application", "setup"])
        refresh()
        wait_for(app_status, ("Synced", "Healthy"), "manual sync status")
        wait_for(configmap_release, "v1", "manual desired resource")
        captures[VARIANTS[0]] = capture_variant(
            VARIANTS[0], manual_started,
            [
                {"action": "create-application-with-fixed-revision-and-manual-policy", "status": "passed"},
                {"action": "request-manual-sync", "status": "passed"},
                {"action": "observe-synced-healthy", "status": "passed"},
            ],
            "false",
        )

        automated_started = now()
        kubectl(
            "-n", ARGOCD_NAMESPACE, "patch", "application", APP, "--type", "merge", "-p",
            '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true},"syncOptions":["CreateNamespace=true"]}}}',
        )
        kubectl(
            "-n", NAMESPACE, "patch", "configmap", APP, "--type", "merge", "-p",
            '{"data":{"release":"live-drift"}}',
        )
        refresh()
        wait_for(configmap_release, "v1", "automated self-heal desired resource")
        wait_for(app_status, ("Synced", "Healthy"), "automated sync status")
        captures[VARIANTS[1]] = capture_variant(
            VARIANTS[1], automated_started,
            [
                {"action": "enable-automated-prune-self-heal", "status": "passed"},
                {"action": "inject-live-configmap-drift", "status": "passed"},
                {"action": "observe-controller-self-heal", "status": "passed"},
            ],
            "true",
        )
        publish(captures, runtime_identity())
    finally:
        command([str(ROOT / "scripts/run-lab.sh"), "application", "cleanup"])
    print(f"Dedicated Runtime row passed: surface=application.spec.sync-policy scenario=normal variants={len(VARIANTS)} retries=0")


if __name__ == "__main__":
    main()
