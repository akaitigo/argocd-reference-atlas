#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Build the fail-closed bridge from fixed candidate artifacts to Core v2 inventory.

This report classifies candidate edges against the existing domain inventory without
promoting any pending-human Authority anchor into a final Surface Artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXTRACTION = ROOT / "authority/extraction.snapshot.json"
BODY = ROOT / "authority/body-inventory.snapshot.json"
REVIEW = ROOT / "authority/review-queue.snapshot.json"
DOMAIN_INVENTORY = ROOT / "definitive/surface-inventory.yaml"
ROOT_INVENTORY = ROOT / "surface.inventory.yaml"
OUTPUT = ROOT / "artifacts/core-v2/surface-inventory-readiness.json"
CORE_MAIN = "46db1eb0e68d00c09f34994dd66ad6d44d3f6ef1"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path.relative_to(ROOT)}")
    return value


def build() -> dict[str, Any]:
    extraction = load(EXTRACTION)
    body = load(BODY)
    review = load(REVIEW)
    domain = load(DOMAIN_INVENTORY)
    domain_items = {item["id"]: item for item in domain["items"]}
    if len(domain_items) != len(domain["items"]):
        raise ValueError("旧domain inventoryのItem IDが重複しています")

    artifact_bindings: list[dict[str, Any]] = []
    candidate_mappings: list[dict[str, Any]] = []
    seen_edges: set[str] = set()
    claim_binding_gaps = 0
    unmapped: list[str] = []
    for source in sorted(extraction["sources"], key=lambda item: item["id"]):
        path = ROOT / source["path"]
        if digest(path) != source["digest"]:
            raise ValueError(f"candidate Artifact digestが固定値と一致しません: {source['path']}")
        draft = load(path)
        artifact_bindings.append({
            "source_id": source["id"],
            "path": source["path"],
            "digest": source["digest"],
            "candidate_edges": len(draft["candidate_surfaces"]),
            "review_status": draft["extraction"]["review_status"],
            "promotion_eligible": False,
        })
        for candidate in draft["candidate_surfaces"]:
            edge_id = candidate["edge_id"]
            if edge_id in seen_edges:
                raise ValueError(f"candidate edge IDが重複しています: {edge_id}")
            seen_edges.add(edge_id)
            item_id = next(
                (identifier for identifier in sorted(domain_items, key=len, reverse=True) if edge_id.startswith(f"edge.{identifier}.")),
                None,
            )
            item = domain_items.get(item_id) if item_id else None
            source_provenance = candidate["pattern_id"].startswith("authority/") and edge_id.startswith("edge.source.")
            mapped = (item is not None and item["target_id"] == candidate["target_id"]) or source_provenance
            if not mapped:
                unmapped.append(edge_id)
            claim_bound = not candidate["claim_id"].startswith("unclassified.claim.")
            if not claim_bound:
                claim_binding_gaps += 1
            candidate_mappings.append({
                "edge_id": edge_id,
                "source_id": source["id"],
                "candidate_artifact_path": source["path"],
                "candidate_artifact_digest": source["digest"],
                "locator": candidate["locator"],
                "domain_inventory_item_id": item_id,
                "candidate_behavior_id": candidate["candidate_behavior_id"],
                "candidate_variant_ids": candidate["variant_ids"],
                "candidate_surface_ids": candidate["surface_ids"],
                "candidate_capability_id": candidate["capability_id"],
                "candidate_claim_id": candidate["claim_id"],
                "candidate_inventory_mapping": (
                    "mapped-domain-item" if item is not None and mapped
                    else "mapped-source-provenance" if source_provenance
                    else "unmapped"
                ),
                "claim_binding_status": "bound" if claim_bound else "gap",
                "authority_semantic_status": "pending-human-review",
                "final_surface_promoted": False,
                "completion_credit": False,
            })

    extraction_summary = extraction["summary"]
    body_summary = body["summary"]
    review_summary = review["summary"]
    blockers = []
    if body_summary["pending_human_anchors"]:
        blockers.append("authority-body-pending-human")
    if review_summary["human_reviewed"] == 0:
        blockers.append("authority-review-decisions-zero")
    if extraction_summary["core_v2_eligible_surfaces"] == 0:
        blockers.append("core-v2-eligible-surfaces-zero")
    if claim_binding_gaps:
        blockers.append("candidate-claim-binding-gaps")
    if unmapped:
        blockers.append("candidate-inventory-unmapped")
    if not extraction_summary["authority_text_surfaces_exhaustive"]:
        blockers.append("authority-text-not-exhaustive")
    if not body_summary["authority_semantics_exhaustive"]:
        blockers.append("authority-semantics-not-exhaustive")

    emission_allowed = not blockers
    return {
        "schema_version": 1,
        "id": "argocd-surface-inventory-readiness-v1",
        "status": "incomplete-human-authority-review-required",
        "core_main_commit": CORE_MAIN,
        "inputs": {
            "authority/extraction.snapshot.json": digest(EXTRACTION),
            "authority/body-inventory.snapshot.json": digest(BODY),
            "authority/review-queue.snapshot.json": digest(REVIEW),
            "definitive/surface-inventory.yaml": digest(DOMAIN_INVENTORY),
        },
        "policy": {
            "candidate_mapping_is_authority_promotion": False,
            "pending_human_anchor_has_semantic_credit": False,
            "machine_proposal_is_human_decision": False,
            "root_inventory_publish_is_fail_closed": True,
            "target_generation_used_for_closure": False,
            "scope_reduction_used_for_closure": False,
        },
        "summary": {
            "locked_candidate_artifacts": len(artifact_bindings),
            "candidate_edges": len(candidate_mappings),
            "candidate_inventory_mapped": len(candidate_mappings) - len(unmapped),
            "candidate_inventory_unmapped": len(unmapped),
            "candidate_claim_binding_gaps": claim_binding_gaps,
            "domain_inventory_items": len(domain_items),
            "authority_raw_anchors": body_summary["raw_anchor_candidates"],
            "authority_pending_human": body_summary["pending_human_anchors"],
            "authority_human_reviewed": review_summary["human_reviewed"],
            "authority_core_v2_eligible_surfaces": extraction_summary["core_v2_eligible_surfaces"],
            "final_authority_artifacts": 0,
            "final_surface_items": 0,
            "completion_credit": 0,
        },
        "root_inventory_gate": {
            "required_path": "surface.inventory.yaml",
            "present": ROOT_INVENTORY.is_file(),
            "emission_allowed": emission_allowed,
            "blockers": blockers,
            "expected_next_gate": "authority-human-review",
        },
        "candidate_artifacts": artifact_bindings,
        "candidate_mappings": candidate_mappings,
        "unmapped_candidate_edge_ids": sorted(unmapped),
    }


def validate(document: dict[str, Any]) -> None:
    expected = build()
    if document != expected:
        raise ValueError("Surface Inventory readiness artifactが現在入力からの導出値と一致しません")
    summary = document["summary"]
    gate = document["root_inventory_gate"]
    if summary["candidate_inventory_unmapped"] != 0:
        raise ValueError("固定candidate Artifactからdomain inventoryへの未分類edgeがあります")
    if summary["authority_human_reviewed"] == 0:
        if summary["final_authority_artifacts"] or summary["final_surface_items"] or summary["completion_credit"]:
            raise ValueError("Human ReviewなしでAuthority Surfaceを昇格しています")
        if gate["emission_allowed"] or gate["present"]:
            raise ValueError("Human Reviewなしでroot Surface Inventoryを発行しています")
    if any(item["final_surface_promoted"] or item["completion_credit"] for item in document["candidate_mappings"]):
        raise ValueError("candidate mappingをfinal Authority Surfaceとして扱っています")


def main() -> None:
    document = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validate(document)
    summary = document["summary"]
    print(
        "Surface Inventory readiness generated: "
        f"candidate_artifacts={summary['locked_candidate_artifacts']} "
        f"mapped={summary['candidate_inventory_mapped']} "
        f"unmapped={summary['candidate_inventory_unmapped']} "
        f"claim_gaps={summary['candidate_claim_binding_gaps']} "
        f"human_reviewed={summary['authority_human_reviewed']} promoted={summary['final_surface_items']}"
    )


if __name__ == "__main__":
    main()
