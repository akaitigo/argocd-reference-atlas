#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""8 Outcome x 14 Surface Router契約と独立Forward Evalを機械記録する。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evals" / "argocd-atlas-router.definitive-skill-eval.json"
FORWARD = ROOT / "evals" / "argocd-atlas-router.definitive-forward-eval.json"
RAW_RESULT = ROOT / "evidence" / "raw" / "evidence.skill-definitive-eval.v3-5-2" / "result.json"
ROUTER = ROOT / ".agents" / "skills" / "argocd-atlas-router" / "scripts" / "argocd_router.py"
CONTRACT = ROOT / ".agents" / "skills" / "argocd-atlas-router" / "references" / "mastery-contract.json"
SELF_EVIDENCE_ID = "evidence.skill-definitive-eval.v3-5-2"


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def file_binding(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "digest": sha256_file(path), "bytes": path.stat().st_size}


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Object YAMLではありません: {path.relative_to(ROOT)}")
    return value


def load_router():
    spec = importlib.util.spec_from_file_location("argocd_skill_router", ROUTER)
    if spec is None or spec.loader is None:
        raise ValueError("Router moduleをloadできません")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def without_self_evidence(target: dict) -> dict:
    """評価Artifactとそれを証明するEvidence recordのdigest循環を避ける。"""
    return {
        **target,
        "evidence_ids": [item for item in target.get("evidence_ids", []) if item != SELF_EVIDENCE_ID],
    }


def matrix_requests(router, contract: dict) -> tuple[list[dict], list[str]]:
    context = router.load_context(ROOT)
    supported = []
    for target in context["coverage"]["targets"]:
        evidence = router.evidence_bindings(ROOT, without_self_evidence(target))
        if target["state"] != "missing" and any(item["runtime_proof"] for item in evidence):
            supported.append(target)
    remaining = {target["id"] for target in supported}
    requests: list[dict] = []
    for cell_index, (outcome, surface) in enumerate(
        (outcome, surface) for outcome in contract["outcomes"] for surface in contract["surfaces"]
    ):
        intersection = sorted(set(outcome["target_sets"]) & set(surface["target_sets"]))
        eligible = sorted((target for target in supported if target["target_set"] in intersection), key=lambda item: item["id"])
        remaining_eligible = [target for target in eligible if target["id"] in remaining]
        if remaining_eligible:
            target = remaining_eligible[0]
        elif eligible:
            target = eligible[cell_index % len(eligible)]
        else:
            target = next(item for item in supported if item["id"] == "failure.degraded-dependency")
        remaining.discard(target["id"])
        execution = contract["execution_contracts"][outcome["id"]]
        requests.append({
            "id": f"skill.{outcome['id']}.{surface['id']}",
            "outcome": outcome["id"],
            "surface": surface["id"],
            "query": context["routes"][target["id"]]["query"],
            "expected_target_id": target["id"],
            "authorized_change": execution["mutation_policy"] == "explicit-authorization-required",
        })
    return requests, sorted(remaining)


def evaluate_plan(plan: dict, request: dict, contract: dict, coverage_by_id: dict) -> dict:
    outcome = next(item for item in contract["outcomes"] if item["id"] == request["outcome"])
    surface = next(item for item in contract["surfaces"] if item["id"] == request["surface"])
    execution = contract["execution_contracts"][outcome["id"]]
    intersection = sorted(set(outcome["target_sets"]) & set(surface["target_sets"]))
    target = coverage_by_id[request["expected_target_id"]]
    should_route = target["target_set"] in intersection
    expected_disposition = "verified-bounded-coverage" if target["state"] == "covered" else "coverage-gap"
    assertions = {
        "identity": plan.get("id") == request["id"] and plan.get("outcome") == outcome["id"] and plan.get("surface") == surface["id"],
        "target": plan.get("target_id") == target["id"],
        "target_set_contract": plan.get("target_set_allowed") is should_route and plan.get("target_set_intersection") == intersection,
        "coverage_honesty": plan.get("coverage_state") == target["state"] and plan.get("coverage_disposition") == expected_disposition,
        "routing_gap": plan.get("status") == (expected_disposition if should_route else "mastery-routing-gap"),
        "deliverables": plan.get("required_deliverables") == surface["required_deliverables"],
        "output_contract": plan.get("required_output_fields") == execution["required_output_fields"],
        "mutation_authorization": plan.get("blocked_reasons") == [] and plan.get("mutation_status") == ("authorized-for-request-scope" if execution["mutation_policy"] == "explicit-authorization-required" else "read-only"),
        "claim_binding": bool(plan.get("claim_bindings")) and all(item["status"] == "accepted" and item["digest"].startswith("sha256:") for item in plan["claim_bindings"]),
        "source_binding": bool(plan.get("source_bindings")) and all(item["version"] == "v3.5.2" and item["digest"].startswith("sha256:") and item["url"].startswith("https://") for item in plan["source_bindings"]),
        "runtime_evidence": bool(plan.get("runtime_evidence_bindings")) and any(item["runtime_proof"] and item["artifact_matches_record"] and item["verdict"] == "pass" for item in plan["runtime_evidence_bindings"]),
        "controller_kubernetes_scope": any(item["runtime_scope"] == "real-kubernetes-argocd-controller-bounded" and item["environment"]["profile"] == "cluster" for item in plan.get("runtime_evidence_bindings", [])),
        "authority_human_boundary": plan.get("authority_review", {}).get("pending_human") == 63889 and plan.get("authority_review", {}).get("semantic_surface_credit") == 0 and plan.get("authority_review", {}).get("depth_axis_credit") == 0,
        "stop_conditions": all(item in plan.get("stop_conditions", []) for item in ("coverage-gap", "mastery-routing-gap", "unauthorized-mutation", "external-human-decision-required", "stale-source-relock-explicit-procedure-required", "source-binding-mismatch")),
    }
    return {
        "result": "pass" if all(assertions.values()) else "fail",
        "support_status": "routed" if should_route else "mastery-routing-gap",
        "assertions": assertions,
    }


def target_state_inventory(router, context: dict) -> list[dict]:
    result = []
    for target in context["coverage"]["targets"]:
        claims, sources = router.claim_bindings(ROOT, target, context["sources"])
        evidence = router.evidence_bindings(ROOT, without_self_evidence(target))
        result.append({
            "id": target["id"],
            "target_set": target["target_set"],
            "requirement": target["requirement"],
            "state": target["state"],
            "coverage_disposition": "verified-bounded-coverage" if target["state"] == "covered" else "coverage-gap",
            "claim_ids": [item["id"] for item in claims],
            "source_ids": [item["id"] for item in sources],
            "declared_evidence_ids": target.get("evidence_ids", []),
            "evidence_ids": [item["id"] for item in evidence],
            "real_kubernetes_runtime_evidence_ids": [item["id"] for item in evidence if item["runtime_proof"]],
        })
    return result


def boundary_cases(router, contract: dict) -> list[dict]:
    route_by_id = {item["id"]: item for item in contract["target_routes"]}
    requests = [
        {"id": "boundary.ambiguous", "outcome": "troubleshoot", "surface": "operations-observability", "query": "壊れているので何とかして"},
        {"id": "boundary.unknown", "outcome": "understand", "surface": "orientation-scope", "query": "量子テレパシー同期装置"},
        {"id": "boundary.unknown-outcome", "outcome": "invent", "surface": "orientation-scope", "query": route_by_id["application.declarative-model"]["query"]},
        {"id": "boundary.unauthorized-build", "outcome": "build", "surface": "implementation-construction", "query": route_by_id["sync.order-and-policy"]["query"]},
        {"id": "boundary.unauthorized-operate-mutation", "outcome": "operate", "surface": "operations-observability", "query": route_by_id["operations.routine-control"]["query"], "mutation_requested": True},
        {"id": "boundary.human-authority-decision", "outcome": "delegate", "surface": "agent-skill", "query": route_by_id["architecture.control-plane-components"]["query"], "authorized_change": True, "authority_semantic_decision": True},
        {"id": "boundary.stale-relock", "outcome": "evolve", "surface": "provenance-rights", "query": route_by_id["architecture.control-plane-components"]["query"], "authorized_change": True, "stale_source_relock": True},
    ]
    expected = {
        "boundary.ambiguous": ("coverage-gap", None, None),
        "boundary.unknown": ("coverage-gap", None, None),
        "boundary.unknown-outcome": ("coverage-gap", None, "coverage-gap"),
        "boundary.unauthorized-build": ("blocked", "sync.order-and-policy", "unauthorized-mutation"),
        "boundary.unauthorized-operate-mutation": ("blocked", "operations.routine-control", "unauthorized-mutation"),
        "boundary.human-authority-decision": ("blocked", "architecture.control-plane-components", "external-human-decision-required"),
        "boundary.stale-relock": ("blocked", "architecture.control-plane-components", "stale-source-relock-explicit-procedure-required"),
    }
    plans = router.plan_requests(requests, ROOT)
    results = []
    for plan in plans:
        status, target_id, reason = expected[plan["id"]]
        passed = plan.get("status") == status and plan.get("target_id") == target_id and (reason is None or reason in plan.get("blocked_reasons", []))
        results.append({**plan, "expected": {"status": status, "target_id": target_id, "blocked_reason": reason}, "result": "pass" if passed else "fail"})
    return results


def independent_forward_binding() -> dict:
    if not FORWARD.is_file():
        return {"status": "pending", "path": FORWARD.relative_to(ROOT).as_posix(), "digest": None, "summary": None}
    value = json.loads(FORWARD.read_text(encoding="utf-8"))
    return {
        "status": value.get("verdict", "invalid"),
        "path": FORWARD.relative_to(ROOT).as_posix(),
        "digest": sha256_file(FORWARD),
        "summary": {
            "evaluator_role": value.get("evaluator", {}).get("role"),
            "cases": value.get("summary", {}).get("cases"),
            "passed": value.get("summary", {}).get("passed"),
            "failed": value.get("summary", {}).get("failed"),
            "outcomes_covered": value.get("summary", {}).get("outcomes_covered"),
        },
    }


def build_artifact() -> dict:
    router = load_router()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    context = router.load_context(ROOT)
    coverage_by_id = context["targets"]
    requests, uncovered_supported = matrix_requests(router, contract)
    plans = router.plan_requests([{key: value for key, value in request.items() if key != "expected_target_id"} for request in requests], ROOT)
    matrix = []
    for plan, request in zip(plans, requests):
        matrix.append({**plan, "expected_target_id": request["expected_target_id"], **evaluate_plan(plan, request, contract, coverage_by_id)})
    boundaries = boundary_cases(router, contract)
    inventory = target_state_inventory(router, context)
    state_counts = dict(sorted(Counter(item["state"] for item in inventory).items()))
    routing_gaps = [item for item in matrix if item["support_status"] == "mastery-routing-gap"]
    failed = [item for item in matrix if item["result"] != "pass"]
    boundary_failed = [item for item in boundaries if item["result"] != "pass"]
    forward = independent_forward_binding()
    source_paths = {
        "generator": ROOT / "scripts/generate_definitive_skill_eval.py",
        "validator": ROOT / "scripts/validate_definitive_skill_eval.py",
        "forward_grader": ROOT / "scripts/grade_definitive_forward_eval.py",
        "evidence_generator": ROOT / "scripts/generate_definitive_skill_evidence.py",
        "contract_generator": ROOT / "scripts/generate_skill_mastery_contract.py",
        "router": ROUTER,
        "skill": ROOT / ".agents/skills/argocd-atlas-router/SKILL.md",
        "mastery_contract": CONTRACT,
        "router_cases": ROOT / "evals/router-cases.json",
        "forward_cases": ROOT / "evals/definitive-forward-cases.json",
        "mastery": ROOT / "mastery.yaml",
        "coverage": ROOT / "coverage.yaml",
    }
    open_targets = [item["id"] for item in inventory if item["state"] != "covered"]
    return {
        "schema_version": 1,
        "id": "argocd-atlas-router.definitive-mastery-v1",
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "status": "incomplete-target-or-routing-gaps" if open_targets or routing_gaps else "evaluated-not-completion-certificate",
        "semantic_scope": "deterministic-router-contract-plus-independent-agent-forward-eval-not-completion-certificate",
        "reference": contract["reference"],
        "source_bindings": {key: file_binding(path) for key, path in source_paths.items()},
        "summary": {
            "outcomes": len(contract["outcomes"]),
            "surfaces": len(contract["surfaces"]),
            "matrix_cells": len(matrix),
            "matrix_contract_passed": len(matrix) - len(failed),
            "matrix_contract_failed": len(failed),
            "routed": len(matrix) - len(routing_gaps),
            "mastery_routing_gaps": len(routing_gaps),
            "supported_runtime_targets_routed": len({item["target_id"] for item in matrix if item.get("runtime_evidence_bindings")}),
            "uncovered_supported_runtime_targets": uncovered_supported,
            "target_states": state_counts,
            "open_required_targets": len(open_targets),
            "boundary_cases": len(boundaries),
            "boundary_passed": len(boundaries) - len(boundary_failed),
            "boundary_failed": len(boundary_failed),
            "matrix_pass_is_completion": False,
        },
        "completion_limits": [
            "112セルのcontract passはTarget、Atlas、Definitive、Completion Certificateの完成を意味しない。",
            "build × failure-recoveryはMastery target_set交差がなくrouting gapである。",
            "partialまたはmissingのrequired TargetはCoverage Gapのまま維持する。",
            "人手Authority decisionとstale Source relockをAgent判断として扱わない。",
            "独立Agent Forward Evalのpassはmatrix、Target、実Runtime Proofの代替ではない。",
        ],
        "independent_forward_eval": forward,
        "all_target_state_inventory": inventory,
        "matrix": matrix,
        "boundary_cases": boundaries,
    }


def build_raw_result(artifact: dict) -> dict:
    forward = independent_forward_binding()
    return {
        "schema_version": 1,
        "id": "evidence.skill-definitive-eval.v3-5-2",
        "kind": "definitive-skill-eval",
        "argocd_version": "v3.5.2",
        "matrix_artifact": file_binding(OUTPUT),
        "independent_forward_eval": forward,
        "summary": artifact["summary"],
        "verdict": "pass" if artifact["summary"]["matrix_contract_failed"] == 0 and artifact["summary"]["boundary_failed"] == 0 and forward["status"] == "pass" else "incomplete",
        "completion_claim": False,
    }


def write_raw_result(artifact: dict) -> None:
    RAW_RESULT.parent.mkdir(parents=True, exist_ok=True)
    RAW_RESULT.write_text(json.dumps(build_raw_result(artifact), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    artifact = build_artifact()
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_raw_result(artifact)
    summary = artifact["summary"]
    print(
        f"Definitive Skill Eval: matrix={summary['matrix_contract_passed']}/{summary['matrix_cells']} "
        f"routed={summary['routed']} routing-gaps={summary['mastery_routing_gaps']} "
        f"targets={summary['target_states']} open={summary['open_required_targets']} "
        f"boundary={summary['boundary_passed']}/{summary['boundary_cases']} forward={artifact['independent_forward_eval']['status']}"
    )


if __name__ == "__main__":
    main()
