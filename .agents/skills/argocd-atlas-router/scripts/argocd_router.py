#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Outcome／Surface／Queryを固定Target、Authority、Runtime Evidenceへfail-closedでRouteする。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import yaml


DEFAULT_ROOT = Path(__file__).resolve().parents[4]


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Object YAMLではありません: {path}")
    return value


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Object JSONではありません: {path}")
    return value


def tokenize(value: str) -> set[str]:
    return {term for term in re.split(r"[^a-z0-9]+", value.lower()) if len(term) > 1}


def load_context(root: Path = DEFAULT_ROOT) -> dict:
    contract_path = root / ".agents/skills/argocd-atlas-router/references/mastery-contract.json"
    contract = load_json(contract_path)
    coverage = load_yaml(root / "coverage.yaml")
    sources = load_yaml(root / "sources.lock.yaml")
    body = load_json(root / "authority/body-inventory.snapshot.json")
    queue = load_json(root / "authority/review-queue.snapshot.json")
    decisions = load_json(root / "authority/reviews/decisions.json")
    return {
        "root": root,
        "contract": contract,
        "coverage": coverage,
        "targets": {target["id"]: target for target in coverage["targets"]},
        "routes": {route["id"]: route for route in contract["target_routes"]},
        "sources": {source["id"]: source for source in sources["sources"]},
        "authority_review": {
            "body_status": body["status"],
            "raw_anchors": body["summary"]["raw_anchors"],
            "pending_human": queue["summary"]["pending_human"],
            "human_reviewed": queue["summary"]["human_reviewed"],
            "stale_document_holds": queue["summary"]["stale_document_holds"],
            "decisions": len(decisions["decisions"]),
            "promoted_controller_behavior_items": queue["summary"]["promoted_controller_behavior_items"],
            "semantic_surface_credit": queue["summary"]["semantic_surface_credit"],
            "depth_axis_credit": queue["summary"]["depth_axis_credit"],
        },
        "contract_binding": {"path": contract_path.relative_to(root).as_posix(), "digest": sha256_file(contract_path), "bytes": contract_path.stat().st_size},
    }


def match_target(context: dict, query: str) -> tuple[dict | None, str]:
    normalized = " ".join(query.strip().lower().split())
    exact = [route for route in context["routes"].values() if normalized == " ".join(route["query"].lower().split())]
    if len(exact) == 1:
        return context["targets"][exact[0]["id"]], "exact-exemplar"
    identity = [target for target in context["targets"].values() if target["id"].lower() in normalized or target["title"].lower() in normalized]
    if len(identity) == 1:
        return identity[0], "exact-target-identity"
    query_terms = tokenize(normalized)
    scored: list[tuple[int, dict]] = []
    for target in context["targets"].values():
        terms = tokenize(f"{target['id']} {target['title']} {target['rationale']}")
        score = len(query_terms & terms)
        if score >= 2:
            scored.append((score, target))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1], "unique-token-match"
    return None, "ambiguous-or-unknown"


def claim_bindings(root: Path, target: dict, sources: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    claims: list[dict] = []
    source_bindings: dict[str, dict] = {}
    for claim_id in target.get("claim_ids", []):
        path = root / "claims" / f"{claim_id}.claim.yaml"
        claim = load_yaml(path)
        claims.append({
            "id": claim_id,
            "path": path.relative_to(root).as_posix(),
            "digest": sha256_file(path),
            "status": claim["status"],
            "source_ids": claim["source_ids"],
        })
        for source_id in claim["source_ids"]:
            source = sources[source_id]
            source_bindings[source_id] = {
                "id": source_id,
                "url": source["url"],
                "version": source["version"],
                "digest": source["digest"],
                "kind": source["kind"],
            }
    return claims, [source_bindings[key] for key in sorted(source_bindings)]


def evidence_bindings(root: Path, target: dict) -> list[dict]:
    result: list[dict] = []
    for evidence_id in target.get("evidence_ids", []):
        record_path = root / "evidence" / "records" / f"{evidence_id}.evidence.yaml"
        record = load_yaml(record_path)
        artifact_path = root / record["artifact"]["uri"]
        artifact_matches = (
            artifact_path.is_file()
            and sha256_file(artifact_path) == record["artifact"]["digest"]
            and artifact_path.stat().st_size == record["artifact"]["size_bytes"]
        )
        environment = record["environment"]
        runtime_proof = (
            environment.get("profile") == "cluster"
            and str(environment.get("argocd_version", "")).startswith("v3.")
            and str(record.get("producer", "")).startswith("argocd-atlas-kind")
            and artifact_matches
        )
        result.append({
            "id": evidence_id,
            "record_path": record_path.relative_to(root).as_posix(),
            "record_digest": sha256_file(record_path),
            "verdict": record["verdict"],
            "producer": record["producer"],
            "command": record["command"],
            "environment": environment,
            "source_digest": record["source_digest"],
            "harness_path": record["harness_path"],
            "harness_digest": record["harness_digest"],
            "artifact": record["artifact"],
            "artifact_matches_record": artifact_matches,
            "runtime_proof": runtime_proof,
            "runtime_scope": "real-kubernetes-argocd-controller-bounded" if runtime_proof else "non-cluster-or-aggregate-evidence",
        })
    return result


def boundary_blocks(request: dict, execution: dict) -> list[str]:
    blocks: list[str] = []
    mutation_required = execution["mutation_policy"] == "explicit-authorization-required" or request.get("mutation_requested") is True
    if mutation_required and request.get("authorized_change") is not True:
        blocks.append("unauthorized-mutation")
    if request.get("authority_semantic_decision") is True:
        blocks.append("external-human-decision-required")
    if request.get("stale_source_relock") is True:
        blocks.append("stale-source-relock-explicit-procedure-required")
    return blocks


def plan_request(context: dict, request: dict) -> dict:
    contract = context["contract"]
    outcome = next((item for item in contract["outcomes"] if item["id"] == request.get("outcome")), None)
    surface = next((item for item in contract["surfaces"] if item["id"] == request.get("surface")), None)
    if outcome is None or surface is None:
        return {
            "id": request.get("id"),
            "status": "coverage-gap",
            "query_disposition": "unknown-outcome-or-surface",
            "outcome": request.get("outcome"),
            "surface": request.get("surface"),
            "target_id": None,
            "blocked_reasons": ["coverage-gap"],
            "stop_conditions": contract["stop_conditions"],
        }
    execution = contract["execution_contracts"][outcome["id"]]
    target, query_disposition = match_target(context, str(request.get("query", "")))
    blocks = boundary_blocks(request, execution)
    intersection = sorted(set(outcome["target_sets"]) & set(surface["target_sets"]))
    if target is None:
        return {
            "id": request["id"],
            "status": "coverage-gap",
            "query_disposition": query_disposition,
            "outcome": outcome["id"],
            "surface": surface["id"],
            "mode": execution["mode"],
            "query": request["query"],
            "target_id": None,
            "target_set_intersection": intersection,
            "coverage_state": "missing",
            "coverage_disposition": "coverage-gap",
            "required_deliverables": surface["required_deliverables"],
            "required_output_fields": execution["required_output_fields"],
            "mutation_policy": execution["mutation_policy"],
            "mutation_status": "blocked" if "unauthorized-mutation" in blocks else "read-only",
            "blocked_reasons": blocks,
            "stop_conditions": contract["stop_conditions"],
            "claim_bindings": [],
            "source_bindings": [],
            "runtime_evidence_bindings": [],
            "authority_review": context["authority_review"],
            "contract_binding": context["contract_binding"],
        }
    target_allowed = target["target_set"] in intersection
    claims, sources = claim_bindings(context["root"], target, context["sources"])
    evidence = evidence_bindings(context["root"], target)
    coverage_disposition = "verified-bounded-coverage" if target["state"] == "covered" else "coverage-gap"
    route_status = coverage_disposition if target_allowed else "mastery-routing-gap"
    if blocks:
        route_status = "blocked"
    mutation_required = execution["mutation_policy"] == "explicit-authorization-required" or request.get("mutation_requested") is True
    mutation_status = "read-only"
    if mutation_required:
        mutation_status = "authorized-for-request-scope" if request.get("authorized_change") is True and "unauthorized-mutation" not in blocks else "blocked"
    return {
        "id": request["id"],
        "status": route_status,
        "query_disposition": query_disposition,
        "outcome": outcome["id"],
        "surface": surface["id"],
        "mode": execution["mode"],
        "query": request["query"],
        "target_id": target["id"],
        "target_set": target["target_set"],
        "target_set_intersection": intersection,
        "target_set_allowed": target_allowed,
        "coverage_state": target["state"],
        "coverage_disposition": coverage_disposition,
        "required_deliverables": surface["required_deliverables"],
        "required_output_fields": execution["required_output_fields"],
        "mutation_policy": execution["mutation_policy"],
        "mutation_status": mutation_status,
        "blocked_reasons": blocks,
        "stop_conditions": contract["stop_conditions"],
        "claim_bindings": claims,
        "source_bindings": sources,
        "runtime_evidence_bindings": evidence,
        "authority_review": context["authority_review"],
        "contract_binding": context["contract_binding"],
    }


def plan_requests(requests: list[dict], root: Path = DEFAULT_ROOT) -> list[dict]:
    context = load_context(root)
    return [plan_request(context, request) for request in requests]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--authorized-change", action="store_true")
    parser.add_argument("--mutation-requested", action="store_true")
    parser.add_argument("--authority-semantic-decision", action="store_true")
    parser.add_argument("--stale-source-relock", action="store_true")
    parser.add_argument("--repository-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    request = {
        "id": "cli-request",
        "outcome": args.outcome,
        "surface": args.surface,
        "query": args.query,
        "authorized_change": args.authorized_change,
        "mutation_requested": args.mutation_requested,
        "authority_semantic_decision": args.authority_semantic_decision,
        "stale_source_relock": args.stale_source_relock,
    }
    print(json.dumps(plan_requests([request], args.repository_root.resolve())[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
