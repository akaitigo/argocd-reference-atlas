#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Authority locator artifactのcopyright-safe境界と未完了状態を検査する。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "authority" / "extraction.snapshot.json"
ARTIFACT_DIR = ROOT / "authority" / "locators"
EXPECTED_REFERENCE_COMMIT = "841ec2fa399606a10305021a8bcd396713b8cee5"
FORBIDDEN_BODY_KEYS = {"body", "text", "content", "excerpt", "quote", "snippet", "raw_body", "source_body", "context_text", "heading_text", "markdown", "html"}


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def exact_keys(value: dict, expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(f"{label}のfieldが不一致です: actual={sorted(actual)} expected={sorted(expected)}")


def reject_body_fields(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_BODY_KEYS:
                raise ValueError(f"第三者本文fieldを拒否しました: {path}.{key}")
            reject_body_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_body_fields(child, f"{path}[{index}]")


def inventory_items() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for line in (ROOT / "definitive" / "surface-inventory.yaml").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^  - \{(.+)}$", line)
        if not match:
            continue
        item: dict[str, str] = {}
        for pair in match.group(1).split(", "):
            key, value = pair.split(": ", 1)
            item[key] = value
        result.append(item)
    return result


def main() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    reject_body_fields(index)
    exact_keys(index, {"schema_version", "atlas_id", "generated_at", "status", "reference", "input_digest", "body_storage", "scope_separation", "summary", "non_authority_inventory_item_ids", "sources"}, "Authority index")
    exact_keys(index["reference"], {"repository", "commit", "files"}, "Authority reference")
    exact_keys(index["scope_separation"], {"domain_inventory_source", "authority_reference_edge_classification", "authority_text_exhaustive_inventory", "rule"}, "Authority scope separation")
    exact_keys(index["summary"], {"locked_sources", "matched_sources", "stale_sources", "fetch_failed", "domain_inventory_items", "authority_reference_edges_classified", "non_authority_runtime_obligations", "unclassified_authority_reference_edges", "root_locators", "file_locators_found", "file_locators_not_found", "locator_evaluations_deferred", "authority_text_surfaces_exhaustive", "authority_text_surface_denominator_closed", "human_reviewed_surfaces", "core_v2_eligible_surfaces"}, "Authority summary")
    if index["reference"]["commit"] != EXPECTED_REFERENCE_COMMIT or len(index["reference"]["files"]) != 4:
        raise ValueError("FE copyright-safe Authority locator正本が固定されていません")
    for item in index["reference"]["files"]:
        exact_keys(item, {"path", "sha256"}, "Authority reference file")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Authority reference digestが不正です")
    if index["status"] != "incomplete-human-review-and-exhaustive-inventory-required":
        raise ValueError("Authority locator監査を未完了以外にできません")
    if index["body_storage"] != "metadata-digest-locator-offset-only":
        raise ValueError("Authority本文保存境界が不正です")

    lock = yaml.safe_load((ROOT / "sources.lock.yaml").read_text(encoding="utf-8"))
    source_by_id = {item["id"]: item for item in lock["sources"]}
    expected_files = {f"{source_id}.json" for source_id in source_by_id}
    actual_files = {path.name for path in ARTIFACT_DIR.glob("*.json")}
    if actual_files != expected_files:
        raise ValueError("Authority locator artifact集合がSource lockと一致しません")
    source_index = {item["id"]: item for item in index["sources"]}
    if set(source_index) != set(source_by_id) or len(source_index) != len(index["sources"]):
        raise ValueError("Authority index source集合に欠落または重複があります")

    edge_ids: set[str] = set()
    inventory_edge_ids: set[str] = set()
    for source_id, source in source_by_id.items():
        path = ARTIFACT_DIR / f"{source_id}.json"
        artifact = json.loads(path.read_text(encoding="utf-8"))
        reject_body_fields(artifact)
        exact_keys(artifact, {"schema_version", "source_id", "source_url", "locked_source_digest", "fetch", "extraction", "document_locator", "candidate_surfaces"}, f"Authority artifact {source_id}")
        exact_keys(artifact["fetch"], {"status", "observed_digest", "locked_digest_match", "observed_bytes", "content_type", "error_digest"}, f"Authority fetch {source_id}")
        exact_keys(artifact["extraction"], {"method", "tool", "review_status", "body_storage"}, f"Authority extraction {source_id}")
        exact_keys(artifact["document_locator"], {"locator", "locator_kind", "locator_status", "context_digest", "context_start", "context_end", "context_unit"}, f"Authority document locator {source_id}")
        if artifact["source_id"] != source_id or artifact["source_url"] != source["url"] or artifact["locked_source_digest"] != source["digest"]:
            raise ValueError(f"Authority source identityが不正です: {source_id}")
        if artifact["fetch"]["status"] != "matched" or artifact["fetch"]["observed_digest"] != source["digest"] or artifact["fetch"]["locked_digest_match"] is not True:
            raise ValueError(f"Authority source digest matchが不正です: {source_id}")
        if artifact["extraction"] != {"method": "locked-body-file-locator-digest", "tool": "argocd-reference-atlas-authority-locator-v1", "review_status": "automated-unreviewed", "body_storage": "metadata-digest-locator-offset-only"}:
            raise ValueError(f"Authority extraction/review境界が不正です: {source_id}")
        locator = artifact["document_locator"]
        if locator["locator"] != "document-root" or locator["locator_status"] != "root-document" or locator["context_digest"] != source["digest"] or locator["context_start"] != 0 or locator["context_end"] != artifact["fetch"]["observed_bytes"] or locator["context_unit"] != "byte":
            raise ValueError(f"Authority root locatorが不正です: {source_id}")
        for candidate in artifact["candidate_surfaces"]:
            exact_keys(candidate, {"edge_id", "source_id", "inventory_item_id", "area", "target_id", "locator", "locator_status", "context_digest", "context_start", "context_end", "context_unit", "heading_digest", "classification_basis", "domain_reference_metadata_digest", "classification"}, f"Authority candidate {candidate.get('edge_id')}")
            if candidate["edge_id"] in edge_ids or candidate["source_id"] != source_id:
                raise ValueError(f"Authority edge重複またはsource不一致です: {candidate['edge_id']}")
            edge_ids.add(candidate["edge_id"])
            inventory_edge_ids.add(candidate["inventory_item_id"])
            if candidate["locator_status"] != "file-found" or candidate["context_start"] != 0 or candidate["context_end"] <= 0 or candidate["context_unit"] != "byte" or not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate["context_digest"]):
                raise ValueError(f"Authority file locatorが不正です: {candidate['edge_id']}")
            if candidate["heading_digest"] is not None or candidate["classification"] != "candidate-included-unreviewed" or candidate["classification_basis"] != "domain-inventory-projection-unreviewed":
                raise ValueError(f"未Review分類境界が不正です: {candidate['edge_id']}")
        record = source_index[source_id]
        exact_keys(record, {"id", "path", "digest", "locked_digest_match", "candidate_surfaces", "locator_status"}, f"Authority source index {source_id}")
        if record["path"] != path.relative_to(ROOT).as_posix() or record["digest"] != sha256(path) or record["candidate_surfaces"] != len(artifact["candidate_surfaces"]) or record["locked_digest_match"] is not True:
            raise ValueError(f"Authority source index driftがあります: {source_id}")

    items = inventory_items()
    authority_ids = {item["id"] for item in items if not item["locator"].startswith(("definitive/", "labs/"))}
    non_authority_ids = sorted(item["id"] for item in items if item["id"] not in authority_ids)
    if inventory_edge_ids != authority_ids:
        raise ValueError(f"既存Authority reference edge分類に欠落があります: {sorted(authority_ids - inventory_edge_ids)}")
    if index["non_authority_inventory_item_ids"] != non_authority_ids:
        raise ValueError("Runtime obligationとAuthority edgeの分離がdriftしています")
    summary = index["summary"]
    expected_counts = {
        "locked_sources": len(source_by_id), "matched_sources": len(source_by_id), "stale_sources": 0,
        "fetch_failed": 0, "domain_inventory_items": len(items), "authority_reference_edges_classified": len(authority_ids),
        "non_authority_runtime_obligations": len(non_authority_ids), "unclassified_authority_reference_edges": 0,
        "root_locators": len(source_by_id), "file_locators_found": len(authority_ids), "file_locators_not_found": 0,
        "locator_evaluations_deferred": 0, "authority_text_surfaces_exhaustive": False,
        "authority_text_surface_denominator_closed": False, "human_reviewed_surfaces": 0, "core_v2_eligible_surfaces": 0,
    }
    if summary != expected_counts:
        raise ValueError(f"Authority summaryが実体と一致しません: {summary}")
    print(
        f"authority locators validated: sources={len(source_by_id)} matched={summary['matched_sources']} "
        f"stale={summary['stale_sources']} deferred={summary['locator_evaluations_deferred']} "
        f"candidate_edges={len(authority_ids)} human_reviewed=0 exhaustive=false"
    )


if __name__ == "__main__":
    main()
