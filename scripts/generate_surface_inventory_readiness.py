#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Build the fail-closed bridge from fixed candidate artifacts to Core v2 inventory.

This report classifies candidate edges against the existing domain inventory without
promoting any pending-human Authority anchor into a final Surface Artifact.
"""

from __future__ import annotations

import argparse
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
CORE_GRAPH_PIN = "072d7ca77981f51754e824d70c6d4ecd55ea67e5"
SURFACE_SCHEMA_DIGEST = "sha256:e770a4ce03820e272469a7f621e8a4402b90b6ffba31d9ab9658926ee8c38358"
AUTHORITY_SCHEMA_DIGEST = "sha256:2ee51ca302ab3f8a7c8643c60e6aa406b9812448eac39159cc78fe7fd8ea5fc2"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path.relative_to(ROOT)}")
    return value


def verify_available_core_schemas() -> None:
    roots = [ROOT / ".atlas-core", ROOT.parent / "reference-atlas-core"]
    expected = {
        "schemas/surface-inventory.schema.json": SURFACE_SCHEMA_DIGEST,
        "schemas/authority-surfaces.schema.json": AUTHORITY_SCHEMA_DIGEST,
    }
    available = next((candidate for candidate in roots if all((candidate / path).is_file() for path in expected)), None)
    if available is None:
        return
    for relative, expected_digest in expected.items():
        if digest(available / relative) != expected_digest:
            raise ValueError(f"Core root Inventory Schema digestが固定値と一致しません: {relative}")


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
        "core_root_inventory_contract": {
            "current_main_commit": CORE_MAIN,
            "ci_evidence_dependency_pin": CORE_GRAPH_PIN,
            "schema_digests": {
                "schemas/surface-inventory.schema.json": SURFACE_SCHEMA_DIGEST,
                "schemas/authority-surfaces.schema.json": AUTHORITY_SCHEMA_DIGEST,
            },
            "constraints": {
                "authority_artifacts_min_items": 1,
                "inventory_items_min_items": 1,
                "authority_surfaces_min_items": 1,
                "inventory_classification": "included-only",
                "review_mapping_must_equal_promoted_surfaces": True,
                "incomplete_pending_root_representation_supported": False,
            },
            "honest_root_connection_state": "blocked-no-reviewed-authority-surface",
            "forbidden_workaround": "unreviewed-candidate-as-included-surface",
        },
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
    verify_available_core_schemas()
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = build()
    if args.check:
        existing = load(OUTPUT)
        if existing != document:
            raise ValueError("Surface Inventory readiness artifactが再生成結果と一致しません")
    else:
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
