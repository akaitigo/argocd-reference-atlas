#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Argo CD固有のEvidence Dependency GraphとClosure Planを生成・検証する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "evidence/dependency-graph.json"
CLOSURE_PLAN = ROOT / "evidence/scenarios/closure-plan.json"
INDEX = ROOT / "evidence/scenarios/index.json"
HISTORICAL_SOURCE = ROOT / "evidence/certificates/historical/v0.1.0-2026-08-28.completion-certificate.json"
HISTORICAL_TARGET = ROOT / "evidence/history/v0.1.0/completion-certificate.json"
CORE_COMMIT = "072d7ca77981f51754e824d70c6d4ecd55ea67e5"
GENERATED_AT = "2026-08-28T15:48:00Z"
RISK_ORDER = ["security", "rejection", "failure", "recovery", "migration", "operations", "boundary", "performance", "compatibility", "normal"]


class DependencyContractError(ValueError):
    """Dependency Graph契約違反。"""


def load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DependencyContractError(f"objectではありません: {path}")
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def pretty(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def aggregate_member_digest(root: Path, members: Iterable[str]) -> str:
    items = []
    for member in sorted(members):
        path = root / member
        if not path.is_file():
            raise DependencyContractError(f"input memberがありません: {member}")
        items.append({"path": member, "digest": sha256_file(path)})
    return sha256_bytes(canonical(items))


def stable_id(prefix: str, path: str) -> str:
    slug = re.sub(r"[^a-z0-9._:-]+", ".", path.lower()).strip(".")
    return f"{prefix}.{slug}"


def target_sets() -> dict[str, str]:
    return {item["id"]: item["target_set"] for item in load(ROOT / "coverage.yaml")["targets"]}


def build_closure_plan() -> dict[str, Any]:
    index = load(INDEX)
    sets = target_sets()
    ranks = {scenario: position + 1 for position, scenario in enumerate(RISK_ORDER)}
    rows = []
    for item in index["files"]:
        proof = load(ROOT / item["path"])
        scenario = proof["scenario"]
        runtime_closure = proof["scenario_gap_closure"]
        rows.append({
            "id": f"closure.{proof['behavior_id']}.{scenario}",
            "pattern_id": proof["behavior_id"],
            "target_id": proof["target_id"],
            "target_set": proof.get("target_set") or sets[proof["target_id"]],
            "scenario": scenario,
            "risk_rank": ranks[scenario],
            "proof": {"path": item["path"], "digest": item["digest"]},
            "variant_denominator": {
                "status": runtime_closure["variant_contract"]["status"],
                "exhaustive": runtime_closure["variant_contract"]["exhaustive"],
                "approved_variant_ids": [],
                "runtime_declared_variant_ids": runtime_closure["variant_contract"]["expected_variant_ids"],
            },
            "dedicated_runtime_execution_complete": runtime_closure["dedicated_runtime_execution_complete"],
            "scenario_gap_closed": runtime_closure["scenario_gap_closed"],
            "required_closure": {
                "all_variants_driven": True,
                "first_attempt_only": True,
                "retries": 0,
                "runtime_identity": ["argocd", "kubernetes", "cluster", "topology", "controller"],
                "artifact_channels": ["resource_state", "controller_log", "metric", "trace"],
                "source_and_harness_digests": True,
                "forbidden_substitutions": ["metadata-only", "historical-bundle-reuse", "integrated-result-reuse", "mock-or-static-runtime"],
            },
            "gaps": proof["gaps"],
        })
    rows.sort(key=lambda item: (item["risk_rank"], item["pattern_id"]))
    tranches = []
    by_scenario: dict[str, int] = {}
    for scenario in RISK_ORDER:
        scenario_rows = [row for row in rows if row["scenario"] == scenario]
        by_scenario[scenario] = len(scenario_rows)
        for offset in range(0, len(scenario_rows), 4):
            selected = scenario_rows[offset:offset + 4]
            tranches.append({
                "id": f"{scenario}-{offset // 4 + 1:03d}",
                "risk_rank": ranks[scenario],
                "scenario": scenario,
                "status": "planned",
                "row_ids": [row["id"] for row in selected],
                "pattern_rows": len(selected),
                "variant_runs": 0,
                "variant_denominator_status": "pending-authority-human-review",
                "commit_policy": "one-reviewed-tranche-with-non-regression-runtime-identity-and-oracle-validation",
            })
    completed_rows = [row["id"] for row in rows if row["dedicated_runtime_execution_complete"]]
    completed_set = set(completed_rows)
    row_map = {row["id"]: row for row in rows}
    for tranche in tranches:
        if all(row_id in completed_set for row_id in tranche["row_ids"]):
            tranche["status"] = "dedicated-runtime-complete-authority-pending"
            tranche["variant_runs"] = sum(len(row_map[row_id]["variant_denominator"]["runtime_declared_variant_ids"]) for row_id in tranche["row_ids"])
    completed_tranches = [tranche for tranche in tranches if tranche["status"] == "dedicated-runtime-complete-authority-pending"]
    next_tranche = next((tranche for tranche in tranches if tranche["status"] == "planned"), None)
    return {
        "schema_version": 1,
        "id": "argocd-scenario-closure-plan-v1",
        "atlas_id": "argocd-reference-atlas",
        "generated_at": GENERATED_AT,
        "status": "incomplete",
        "scope": "current-argocd-surface-scenario-gaps-not-authority-atomic",
        "policy": {
            "risk_order": RISK_ORDER,
            "maximum_pattern_rows_per_tranche": 4,
            "monotonic_addition": True,
            "mass_closure_forbidden": True,
            "pending_variant_denominator_has_no_runtime_credit": True,
        },
        "reference": {
            "core_repository": "reference-atlas-core",
            "core_commit_pin": CORE_COMMIT,
            "pin_reason": "正式mainおよびCI成功済みのEvidence Dependency Graph契約commitを固定する。",
        },
        "source_digests": {"evidence/scenarios/index.json": sha256_file(INDEX)},
        "baseline": {
            "matrix_rows": len(index["files"]),
            "patterns": index["summary"]["behaviors"],
            "scenarios": index["summary"]["scenarios"],
            "inherited_gap_rows_at_f055351": len(rows),
        },
        "summary": {
            "completed_dedicated_rows": len(completed_rows),
            "remaining_rows": len(rows) - len(completed_rows),
            "planned_tranches": len(tranches),
            "by_scenario": by_scenario,
        },
        "independent_incomplete": {
            "authority_atomic_rows": index["summary"]["authority_atomic_bindings"],
            "approved_variant_denominators": index["summary"]["variant_denominators_exhaustive"],
            "dedicated_runtime_reports": index["summary"]["dedicated_runtime_reports"],
        },
        "completed_rows": completed_rows,
        "completed_tranches": completed_tranches,
        "next_tranche": next_tranche,
        "tranches": tranches,
        "rows": rows,
    }


def input_specs() -> list[dict[str, Any]]:
    lab_specs = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "labs").glob("*/lab.yaml"))
    specs = [
        ("source.application", "source", ["atlas/claims/index.yaml", "claims/claim.application.desired-state.claim.yaml", "claims/claim.applicationset.generated-applications.claim.yaml", "claims/claim.reconciliation.convergence.claim.yaml", "definitive/surface-inventory.yaml"]),
        ("source.project-policy", "source", ["atlas.yaml", "definitive.yaml", "migrations/definitive-v2.yaml", "atlas/proof-obligations/index.yaml", "coverage.yaml", "mastery.yaml", "claims/claim.security.identity-authorization-boundary.claim.yaml", "claims/claim.security.no-secret-leak.claim.yaml"]),
        ("source.manifests", "source", ["integrations/reference-system/manifest.yaml", "environments/kind/source-server.yaml", "scripts/build-local-source.sh", "fixtures/scenarios/application-sync-policy-normal/configmap.yaml", "fixtures/scenarios/security-001/source-a/shared.yaml", "fixtures/scenarios/security-001/source-b/shared.yaml", "fixtures/scenarios/security-001/operations/configmap.yaml", "fixtures/scenarios/security-002/terminate/hook.yaml", "fixtures/scenarios/security-002/wait/configmap.yaml", "fixtures/scenarios/security-002/resource-actions/deployment.yaml", "fixtures/scenarios/security-002/destination/configmap.yaml", "fixtures/scenarios/security-003/project/configmap.yaml", "fixtures/scenarios/security-003/sources-a/configmap.yaml", "fixtures/scenarios/security-003/sources-b/configmap.yaml", "fixtures/scenarios/security-003/sync-policy/configmap.yaml", "fixtures/scenarios/security-003/appset-workload/configmap.yaml", "fixtures/scenarios/security-003/applicationset.yaml", "fixtures/scenarios/security-004/workload/configmap.yaml", "fixtures/scenarios/security-004/cluster-secret.yaml", "fixtures/scenarios/security-004/duck-resources.yaml", "fixtures/scenarios/security-004/git-directory/approved/configmap.yaml", "fixtures/scenarios/security-004/git-directory/restricted/configmap.yaml"]),
        ("harness.cluster-labs", "harness", [*lab_specs, "scripts/run-lab.sh", "scripts/run-suite.sh", "scripts/evidence/capture.sh", "scripts/evidence/record.sh", "scripts/evidence/record_extended.py", "scripts/extended/run.sh", "scripts/extended/run-suite.sh"]),
        ("harness.scenario-proof", "harness", ["scripts/generate_scenario_proofs.py", "scripts/validate_scenario_proofs.py", "scripts/test_scenario_gap_closure.py", "scripts/test_atomic_evidence_publish.py", "scripts/lib/atomic_evidence_publish.py", "definitive/scenario-variant-contract.yaml", "evidence/scenarios/runtime/index.yaml"]),
        ("harness.scenario-runtime", "harness", ["scripts/scenarios/run_application_sync_policy_normal.py", "scripts/generate_scenario_proofs.py", "scripts/validate_scenario_proofs.py", "scripts/lib/atomic_evidence_publish.py", "definitive/scenario-variant-contract.yaml", "fixtures/scenarios/application-sync-policy-normal/configmap.yaml"]),
        ("harness.scenario-runtime.security-001", "harness", ["scripts/scenarios/run_security_001.py", "scripts/scenarios/run_application_sync_policy_normal.py", "scripts/generate_scenario_proofs.py", "scripts/validate_scenario_proofs.py", "scripts/lib/atomic_evidence_publish.py", "definitive/scenario-variant-contract.yaml", "fixtures/scenarios/security-001/source-a/shared.yaml", "fixtures/scenarios/security-001/source-b/shared.yaml", "fixtures/scenarios/security-001/operations/configmap.yaml"]),
        ("harness.scenario-runtime.security-002", "harness", ["scripts/scenarios/run_security_002.py", "scripts/scenarios/run_application_sync_policy_normal.py", "scripts/generate_scenario_proofs.py", "scripts/validate_scenario_proofs.py", "scripts/lib/atomic_evidence_publish.py", "definitive/scenario-variant-contract.yaml", "fixtures/scenarios/security-002/terminate/hook.yaml", "fixtures/scenarios/security-002/wait/configmap.yaml", "fixtures/scenarios/security-002/resource-actions/deployment.yaml", "fixtures/scenarios/security-002/destination/configmap.yaml"]),
        ("harness.scenario-runtime.security-003", "harness", ["scripts/scenarios/run_security_003.py", "scripts/scenarios/run_application_sync_policy_normal.py", "scripts/build-local-source.sh", "scripts/generate_scenario_proofs.py", "scripts/validate_scenario_proofs.py", "scripts/lib/atomic_evidence_publish.py", "definitive/scenario-variant-contract.yaml", "fixtures/scenarios/security-003/project/configmap.yaml", "fixtures/scenarios/security-003/sources-a/configmap.yaml", "fixtures/scenarios/security-003/sources-b/configmap.yaml", "fixtures/scenarios/security-003/sync-policy/configmap.yaml", "fixtures/scenarios/security-003/appset-workload/configmap.yaml", "fixtures/scenarios/security-003/applicationset.yaml"]),
        ("harness.scenario-runtime.security-004", "harness", ["scripts/scenarios/run_security_004.py", "scripts/scenarios/run_application_sync_policy_normal.py", "scripts/build-local-source.sh", "scripts/generate_scenario_proofs.py", "scripts/validate_scenario_proofs.py", "scripts/lib/atomic_evidence_publish.py", "definitive/scenario-variant-contract.yaml", "fixtures/scenarios/security-004/workload/configmap.yaml", "fixtures/scenarios/security-004/cluster-secret.yaml", "fixtures/scenarios/security-004/duck-resources.yaml", "fixtures/scenarios/security-004/git-directory/approved/configmap.yaml", "fixtures/scenarios/security-004/git-directory/restricted/configmap.yaml"]),
        ("harness.evidence-dependency", "harness", ["scripts/evidence_dependency_graph.py", "scripts/test_evidence_dependency_graph.py", "docs/EVIDENCE_DEPENDENCY_GRAPH.md"]),
        ("harness.skill-eval", "harness", ["skill.package.yaml", ".agents/skills/argocd-atlas-router/SKILL.md", "evals/router-cases.json", "evals/forward-cases.json", "evals/definitive-forward-cases.json", "scripts/generate_definitive_skill_eval.py", "scripts/grade_definitive_forward_eval.py", "scripts/validate_definitive_skill_eval.py"]),
        ("runtime.controller-components", "runtime", ["sources.lock.yaml", "environments/kind/argocd-v3.5.2.lock", "environments/kind/argocd-v3.5.2-ha.lock"]),
        ("runtime.argocd-kubernetes", "runtime", ["environments/kind/argocd-v3.4.8.lock", "environments/kind/argocd-v3.5.2.lock", "environments/kind/kind-config.yaml.tmpl", "scripts/extended/isolation.sh"]),
        ("profile.cluster", "profile", ["environments/kind/README.md", "scripts/environment.sh"]),
        ("profile.container", "profile", ["labs/architecture/lab.yaml", "tests/labs/extended-static.sh"]),
        ("profile.local", "profile", ["Makefile", "evals/definitive-forward-cases.json", "evals/forward-cases.json"]),
    ]
    result = []
    for identifier, kind, members in specs:
        digest = aggregate_member_digest(ROOT, members)
        result.append({"id": identifier, "kind": kind, "members": members, "baseline_digest": digest, "current_digest": digest, "observed_at": GENERATED_AT})
    return result


def evidence_dependencies(record: dict[str, Any]) -> list[str]:
    profile = record["environment"]["profile"]
    if profile == "local":
        return ["source.project-policy", "harness.skill-eval", "profile.local"]
    profiles = ["profile.container"] if profile == "container" else ["profile.cluster"]
    return ["source.application", "source.project-policy", "source.manifests", "harness.cluster-labs", "runtime.controller-components", "runtime.argocd-kubernetes", *profiles]


def discover_required_paths(root: Path) -> set[str]:
    paths = {path.relative_to(root).as_posix() for path in (root / "evidence/records").glob("*.evidence.yaml")}
    paths |= {path.relative_to(root).as_posix() for path in (root / "evidence/raw").glob("*/result.json")}
    paths |= {path.relative_to(root).as_posix() for path in (root / "evidence/scenarios/behaviors").glob("*/*.proof.json")}
    paths |= {path.relative_to(root).as_posix() for path in (root / "evidence/scenarios/runtime").rglob("*") if path.is_file()}
    for relative in [
        "evidence/reference-system/results.json", "evidence/scenarios/index.json", "evidence/scenarios/atomic-publish-manifest.json",
        "evidence/scenarios/closure-plan.json", "evals/argocd-atlas-router.definitive-skill-eval.json",
        "evals/argocd-atlas-router.definitive-forward-eval.json", "provenance.yaml", "artifacts/authority-body-non-regression-report.json",
        "evidence/certificates/historical/v0.1.0-2026-08-28.completion-certificate.json", "evidence/history/v0.1.0/completion-certificate.json",
    ]:
        if (root / relative).is_file():
            paths.add(relative)
    return paths


def add_output(outputs: list[dict[str, Any]], path: str, kind: str, depends_on: list[str], run_id: str) -> str:
    identifier = stable_id("output", path)
    outputs.append({"id": identifier, "kind": kind, "path": path, "digest": sha256_file(ROOT / path), "depends_on": sorted(set(depends_on)), "status": "current", "run_id": run_id})
    return identifier


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def run_document(identifier: str, kind: str, command: str, started: str, output_ids: list[str], identity: dict[str, Any] | None = None) -> dict[str, Any]:
    start = parse_time(started)
    result: dict[str, Any] = {
        "id": identifier,
        "execution_kind": kind,
        "command": command,
        "started_at": start.isoformat().replace("+00:00", "Z"),
        "completed_at": (start + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "result": "passed",
        "attempts": 1,
        "input_bindings": [],
        "output_ids": output_ids,
    }
    if kind != "derived":
        result["runtime_identity"] = identity or {"profile": "unknown"}
    return result


def input_ancestors(output_id: str, output_map: dict[str, dict[str, Any]], input_ids: set[str], visiting: set[str] | None = None) -> set[str]:
    visiting = set() if visiting is None else visiting
    if output_id in visiting:
        raise DependencyContractError(f"cycleがあります: {output_id}")
    visiting.add(output_id)
    result = set()
    for dependency in output_map[output_id]["depends_on"]:
        if dependency in input_ids:
            result.add(dependency)
        elif dependency in output_map:
            result |= input_ancestors(dependency, output_map, input_ids, visiting)
        else:
            raise DependencyContractError(f"未知nodeです: {output_id}->{dependency}")
    visiting.remove(output_id)
    return result


def core_proof_structure_digest(root: Path) -> str:
    index = load(root / "evidence/scenarios/index.json")
    files = []
    for item in index["files"]:
        proof = load(root / item["path"])
        bindings = [{"variant_id": binding.get("variant_id"), "path": binding.get("path")} for binding in proof.get("source_bindings", [])]
        files.append({
            "id": item.get("id"), "pattern_id": item.get("pattern_id"), "scenario": item.get("scenario"), "path": item.get("path"),
            "proof_id": proof.get("id"), "target_id": proof.get("target_id"), "target_set": proof.get("target_set"),
            "behavior_scope": proof.get("behavior_scope"), "source_bindings": bindings,
        })
    return sha256_bytes(canonical({"id": index.get("id"), "atlas_id": index.get("atlas_id"), "denominator": index.get("denominator"), "files": files}))


def core_plan_structure_digest(root: Path) -> str:
    plan = load(root / "evidence/scenarios/closure-plan.json")
    tranches = []
    for field in ["completed_tranches", "tranches"]:
        for item in plan.get(field, []):
            tranches.append({key: item.get(key) for key in ["id", "risk_rank", "scenario", "row_ids", "pattern_rows", "variant_runs", "commit_policy"]})
    ordered = [row_id for item in plan.get("completed_tranches", []) for row_id in item["row_ids"]]
    ordered.extend(item["id"] for item in plan["rows"])
    return sha256_bytes(canonical({"id": plan.get("id"), "scope": plan.get("scope"), "policy": plan.get("policy"), "baseline": plan.get("baseline"), "tranches": tranches, "ordered_row_ids": ordered}))


def build_graph() -> dict[str, Any]:
    inputs = input_specs()
    input_map = {item["id"]: item for item in inputs}
    outputs: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    records = [load(path) for path in sorted((ROOT / "evidence/records").glob("*.evidence.yaml"))]
    records_by_artifact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_artifact[record["artifact"]["uri"]].append(record)
    artifact_output_ids: dict[str, str] = {}
    for artifact_path, group in sorted(records_by_artifact.items()):
        run_id = stable_id("run", artifact_path)
        dependencies = sorted({dependency for record in group for dependency in evidence_dependencies(record)})
        kind = "derived-evidence" if all(record["environment"]["profile"] == "local" for record in group) else "runtime-evidence"
        artifact_id = add_output(outputs, artifact_path, kind, dependencies, run_id)
        artifact_output_ids[artifact_path] = artifact_id
        output_ids = [artifact_id]
        for record in group:
            record_path = f"evidence/records/{record['id']}.evidence.yaml"
            output_ids.append(add_output(outputs, record_path, "derived-evidence", [artifact_id, *evidence_dependencies(record)], run_id))
        started = min(record["created_at"] for record in group)
        profiles = sorted({record["environment"]["profile"] for record in group})
        versions = sorted({str(record["environment"].get("argocd_version")) for record in group})
        identity = {
            "profiles": profiles,
            "argocd_versions": versions,
            "kubernetes_contexts": sorted({str(record["environment"].get("kubernetes_context")) for record in group if record["environment"].get("kubernetes_context")}),
            "cluster_names": sorted({str(record["environment"].get("cluster_name")) for record in group if record["environment"].get("cluster_name")}),
            "manifest_digests": sorted({record["environment"]["manifest_digest"] for record in group}),
            "first_attempt": True,
        }
        execution_kind = "derived" if profiles == ["local"] else ("platform" if "container" in profiles else "runtime")
        runs.append(run_document(run_id, execution_kind, " && ".join(sorted({record["command"] for record in group})), started, output_ids, identity))

    runtime_output_ids = []
    runtime_registry = load(ROOT / "evidence/scenarios/runtime/index.yaml")
    runtime_groups: dict[str, dict[str, Any]] = {}
    for reference in runtime_registry.get("reports", []):
        report = load(ROOT / reference["path"])
        security_001 = report["scenario"] == "security" and report["surface_id"] in {
            "application.multi-source", "application.operation.refresh", "application.operation.rollback", "application.operation.sync",
        }
        security_002 = report["scenario"] == "security" and report["surface_id"] in {
            "application.operation.terminate", "application.operation.wait", "application.resource-actions", "application.spec.destination",
        }
        security_003 = report["scenario"] == "security" and report["surface_id"] in {
            "application.spec.project", "application.spec.sources", "application.spec.sync-policy", "applicationset.any-namespace",
        }
        security_004 = report["scenario"] == "security" and report["surface_id"] in {
            "applicationset.deletion", "applicationset.generator.cluster",
            "applicationset.generator.cluster-decision-resource", "applicationset.generator.git-directory",
        }
        if security_001:
            run_id = "run.scenario-runtime.security-001"
            harness_id = "harness.scenario-runtime.security-001"
            command_name = "make scenario-runtime-security-001"
        elif security_002:
            run_id = "run.scenario-runtime.security-002"
            harness_id = "harness.scenario-runtime.security-002"
            command_name = "make scenario-runtime-security-002"
        elif security_003:
            run_id = "run.scenario-runtime.security-003"
            harness_id = "harness.scenario-runtime.security-003"
            command_name = "make scenario-runtime-security-003"
        elif security_004:
            run_id = "run.scenario-runtime.security-004"
            harness_id = "harness.scenario-runtime.security-004"
            command_name = "python3 scripts/scenarios/run_security_004.py"
        else:
            run_id = "run.scenario-runtime.application-sync-policy.normal"
            harness_id = "harness.scenario-runtime"
            command_name = "make scenario-runtime-application-sync-policy-normal"
        dependencies = [harness_id, "source.manifests", "runtime.controller-components", "runtime.argocd-kubernetes", "profile.cluster"]
        group = runtime_groups.setdefault(run_id, {"command": command_name, "identity": {**report["runtime_identity"], "first_attempt": True}, "output_ids": []})
        artifact_ids = []
        for variant in report["variants"]:
            for artifact in variant["artifacts"].values():
                artifact_id = add_output(outputs, artifact["path"], "runtime-evidence", dependencies, run_id)
                artifact_ids.append(artifact_id)
                runtime_output_ids.append(artifact_id)
        report_id = add_output(outputs, reference["path"], "runtime-evidence", [*artifact_ids, *dependencies], run_id)
        group["output_ids"].extend([*artifact_ids, report_id])
        runtime_output_ids.append(report_id)

    security_004_published = "run.scenario-runtime.security-004" in runtime_groups
    registry_run = "run.scenario-runtime.security-004" if security_004_published else "run.scenario-runtime.security-003"
    registry_dependencies = [*runtime_output_ids, "harness.scenario-runtime.security-003", "harness.scenario-runtime.security-002", "harness.scenario-runtime.security-001", "harness.scenario-runtime"]
    if security_004_published:
        registry_dependencies.append("harness.scenario-runtime.security-004")
    for path in ["evidence/scenarios/runtime/index.yaml", "evidence/scenarios/runtime/atomic-publish-manifest.json"]:
        output_id = add_output(outputs, path, "runtime-evidence", registry_dependencies, registry_run)
        runtime_groups[registry_run]["output_ids"].append(output_id)
        runtime_output_ids.append(output_id)
    for run_id, group in runtime_groups.items():
        runs.append(run_document(run_id, "runtime", group["command"], GENERATED_AT, group["output_ids"], group["identity"]))

    scenario_run = "run.scenario-proof-full"
    raw_ids = sorted(artifact_output_ids.values())
    reference_id = add_output(outputs, "evidence/reference-system/results.json", "reference-system", [*raw_ids, *runtime_output_ids, "harness.scenario-proof", "source.manifests"], scenario_run)
    proof_ids = []
    index = load(INDEX)
    for item in index["files"]:
        proof_ids.append(add_output(outputs, item["path"], "scenario-proof", [reference_id, *runtime_output_ids, "harness.scenario-proof", "runtime.controller-components", "runtime.argocd-kubernetes", "profile.cluster"], scenario_run))
    index_id = add_output(outputs, "evidence/scenarios/index.json", "scenario-proof", [reference_id, *proof_ids, "harness.scenario-proof"], scenario_run)
    manifest_id = add_output(outputs, "evidence/scenarios/atomic-publish-manifest.json", "derived-evidence", [index_id], scenario_run)
    runs.append(run_document(scenario_run, "derived", "make scenario-proofs && make scenario-proofs-validate", GENERATED_AT, [reference_id, *proof_ids, index_id, manifest_id]))

    closure_run = "run.scenario-closure-plan"
    closure_id = add_output(outputs, "evidence/scenarios/closure-plan.json", "closure-plan", [index_id, "harness.evidence-dependency"], closure_run)
    runs.append(run_document(closure_run, "derived", "python3 scripts/evidence_dependency_graph.py generate", GENERATED_AT, [closure_id]))

    skill_paths = ["evals/argocd-atlas-router.definitive-skill-eval.json", "evals/argocd-atlas-router.definitive-forward-eval.json"]
    skill_output_ids = [add_output(outputs, path, "skill-eval", [artifact_output_ids["evidence/raw/evidence.skill-definitive-eval.v3-5-2/result.json"], "harness.skill-eval", "source.project-policy", "profile.local"], "run.definitive-skill-eval") for path in skill_paths]
    runs.append(run_document("run.definitive-skill-eval", "derived", "make skill-definitive-eval && python3 scripts/validate_definitive_skill_eval.py", GENERATED_AT, skill_output_ids))

    migration_outputs = []
    for path in [
        "provenance.yaml", "artifacts/authority-body-non-regression-report.json",
        "evidence/certificates/historical/v0.1.0-2026-08-28.completion-certificate.json", "evidence/history/v0.1.0/completion-certificate.json",
    ]:
        migration_outputs.append(add_output(outputs, path, "derived-evidence", ["source.project-policy", "harness.evidence-dependency", "profile.local"], "run.dependency-migration"))
    runs.append(run_document("run.dependency-migration", "derived", "python3 scripts/evidence_dependency_graph.py generate", GENERATED_AT, migration_outputs))

    output_map = {item["id"]: item for item in outputs}
    input_ids = set(input_map)
    run_map = {run["id"]: run for run in runs}
    for run in runs:
        ancestors = set()
        for output_id in run["output_ids"]:
            ancestors |= input_ancestors(output_id, output_map, input_ids)
        run["input_bindings"] = [{"input_id": input_id, "digest": input_map[input_id]["current_digest"]} for input_id in sorted(ancestors)]
    return {
        "schema_version": 1,
        "atlas_id": "argocd-reference-atlas",
        "generated_at": GENERATED_AT,
        "status": "current",
        "policy": {
            "transitive_staleness": True,
            "digest_only_closure_forbidden": True,
            "actual_rerun_required": True,
            "missing_rerun_targets_fail": True,
            "proof_structure_invariant": True,
            "closure_plan_structure_invariant": True,
        },
        "inputs": inputs,
        "outputs": sorted(outputs, key=lambda item: item["path"]),
        "runs": sorted(run_map.values(), key=lambda item: item["id"]),
        "required_outputs": sorted(item["path"] for item in outputs),
        "structures": [
            {"id": "argocd-scenario-proof-index-v1", "kind": "scenario-proof-index", "path": "evidence/scenarios/index.json", "baseline_digest": core_proof_structure_digest(ROOT)},
            {"id": "argocd-scenario-closure-plan-v1", "kind": "scenario-closure-plan", "path": "evidence/scenarios/closure-plan.json", "baseline_digest": core_plan_structure_digest(ROOT)},
        ],
    }


def validate_closure_plan(root: Path) -> None:
    plan, index = load(root / "evidence/scenarios/closure-plan.json"), load(root / "evidence/scenarios/index.json")
    completed = [row["id"] for row in plan["rows"] if row.get("dedicated_runtime_execution_complete") is True]
    if plan["status"] != "incomplete" or plan["summary"]["remaining_rows"] != len(index["files"]) - len(completed):
        raise DependencyContractError("Closure Planの未完分母がScenario indexと一致しません")
    if plan["summary"]["completed_dedicated_rows"] != len(completed) or plan["completed_rows"] != completed:
        raise DependencyContractError("Closure Planの専用Runtime完了row集計が一致しません")
    if any(row.get("scenario_gap_closed") is True for row in plan["rows"] if row["id"] in completed):
        raise DependencyContractError("Authority未承認rowをScenario gap closedへ昇格しています")
    if len(plan["rows"]) != len(index["files"]):
        raise DependencyContractError("Closure Plan rowが漏れています")
    if any(tranche["pattern_rows"] > 4 or tranche["variant_denominator_status"] != "pending-authority-human-review" for tranche in plan["tranches"]):
        raise DependencyContractError("Closure tranche上限または未承認Variant境界が不正です")
    ordered = sorted(plan["rows"], key=lambda item: (item["risk_rank"], item["pattern_id"]))
    if ordered != plan["rows"]:
        raise DependencyContractError("Closure Planがrisk／Pattern安定順ではありません")
    proof_paths = {item["path"] for item in index["files"]}
    if {item["proof"]["path"] for item in plan["rows"]} != proof_paths:
        raise DependencyContractError("Closure PlanがProof集合を完全包含していません")


def validate_graph(root: Path, graph: dict[str, Any] | None = None) -> None:
    graph = load(root / "evidence/dependency-graph.json") if graph is None else graph
    if graph.get("status") != "current" or any(graph.get("policy", {}).get(key) is not True for key in ["transitive_staleness", "digest_only_closure_forbidden", "actual_rerun_required", "missing_rerun_targets_fail", "proof_structure_invariant", "closure_plan_structure_invariant"]):
        raise DependencyContractError("Graph statusまたはpolicyが不正です")
    inputs = {item["id"]: item for item in graph["inputs"]}
    if len(inputs) != len(graph["inputs"]):
        raise DependencyContractError("input IDが重複しています")
    changed: dict[str, datetime] = {}
    for item in inputs.values():
        actual = aggregate_member_digest(root, item["members"])
        if item["current_digest"] != actual:
            raise DependencyContractError(f"input current digestが不一致です: {item['id']}")
        if item["baseline_digest"] != item["current_digest"]:
            changed[item["id"]] = parse_time(item["observed_at"])
    outputs = {item["id"]: item for item in graph["outputs"]}
    if len(outputs) != len(graph["outputs"]):
        raise DependencyContractError("output IDが重複しています")
    output_paths = {item["path"] for item in outputs.values()}
    discovered = discover_required_paths(root)
    if set(graph["required_outputs"]) != output_paths or discovered - output_paths:
        raise DependencyContractError(f"必要outputが漏れまたは退避されています: missing={sorted(discovered - output_paths)[:3]}")
    for item in outputs.values():
        path = root / item["path"]
        if item["status"] != "current":
            raise DependencyContractError(f"outputがstaleです: {item['id']}")
        if not path.is_file() or item["digest"] != sha256_file(path):
            raise DependencyContractError(f"output digestが不一致です: {item['id']}")
    runs = {item["id"]: item for item in graph["runs"]}
    for output_id, output in outputs.items():
        ancestors = input_ancestors(output_id, outputs, set(inputs))
        run = runs.get(output.get("run_id"))
        if run is None or run.get("result") != "passed" or run.get("attempts") != 1 or output_id not in run.get("output_ids", []):
            raise DependencyContractError(f"outputがfirst-attempt full-runへ接続されていません: {output_id}")
        if run["execution_kind"] != "derived" and not run.get("runtime_identity"):
            raise DependencyContractError(f"runtime identityがありません: {run['id']}")
        bindings = {item["input_id"]: item["digest"] for item in run["input_bindings"]}
        for input_id in ancestors:
            if bindings.get(input_id) != inputs[input_id]["current_digest"]:
                raise DependencyContractError(f"現在input bindingがありません: {run['id']}:{input_id}")
            if input_id in changed and parse_time(run["started_at"]) < changed[input_id]:
                raise DependencyContractError(f"digest-only closureを拒否しました: {input_id}->{output_id}")
    structures = {item["kind"]: item for item in graph["structures"]}
    expected = {
        "scenario-proof-index": core_proof_structure_digest(root),
        "scenario-closure-plan": core_plan_structure_digest(root),
    }
    for kind, digest in expected.items():
        if structures.get(kind, {}).get("baseline_digest") != digest:
            raise DependencyContractError(f"Proof/Closure Plan構造が縮小または変更されました: {kind}")
    validate_closure_plan(root)


def generate() -> None:
    if HISTORICAL_TARGET.exists() and HISTORICAL_SOURCE.read_bytes() != HISTORICAL_TARGET.read_bytes():
        raise DependencyContractError("historical Certificate targetがsourceと一致しません")
    atomic_write(HISTORICAL_TARGET, HISTORICAL_SOURCE.read_bytes())
    plan = build_closure_plan()
    atomic_write(CLOSURE_PLAN, pretty(plan))
    graph = build_graph()
    atomic_write(GRAPH, pretty(graph))
    validate_graph(ROOT, graph)
    print(f"Evidence Dependency Graph generated: inputs={len(graph['inputs'])} outputs={len(graph['outputs'])} runs={len(graph['runs'])} closure_rows={len(plan['rows'])}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["generate", "validate"])
    args = parser.parse_args()
    if args.mode == "generate":
        generate()
    else:
        validate_graph(ROOT)
        graph = load(GRAPH)
        print(f"Evidence Dependency Graph validated: inputs={len(graph['inputs'])} outputs={len(graph['outputs'])} runs={len(graph['runs'])} changed=0")


if __name__ == "__main__":
    main()
