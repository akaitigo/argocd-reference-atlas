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
ARTIFACT_DIR = ROOT / "authority" / "surfaces-draft"
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
    exact_keys(index, {"schema_version", "atlas_id", "generated_at", "status", "input_digest", "tool_digest", "body_storage", "summary", "sources"}, "Authority index")
    exact_keys(index["summary"], {"locked_sources", "fetched_digest_matched", "fetched_digest_stale", "fetch_failed", "candidate_surfaces", "root_locators", "fragments_found", "fragments_not_found", "locator_evaluations_deferred", "reference_edges_classified", "unclassified_reference_edges", "authority_text_surfaces_exhaustive", "human_reviewed_surfaces", "core_v2_eligible_surfaces"}, "Authority summary")
    if index["status"] != "incomplete-human-review-required":
        raise ValueError("Authority locator監査を未完了以外にできません")
    if index["body_storage"] != "digest-and-locator-context-digest-only":
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

    coverage = yaml.safe_load((ROOT / "coverage.yaml").read_text(encoding="utf-8"))
    claim_index = yaml.safe_load((ROOT / "atlas/claims/index.yaml").read_text(encoding="utf-8"))
    target_ids = {item["id"] for item in coverage["targets"]}
    claims = {item["id"]: item for item in claim_index["claims"]}
    edge_ids: set[str] = set()
    for source_id, source in source_by_id.items():
        path = ARTIFACT_DIR / f"{source_id}.json"
        artifact = json.loads(path.read_text(encoding="utf-8"))
        reject_body_fields(artifact)
        exact_keys(artifact, {"schema_version", "source_id", "source_url", "locked_source_digest", "fetch", "extraction", "candidate_surfaces"}, f"Authority artifact {source_id}")
        exact_keys(artifact["fetch"], {"status", "fetched_digest", "locked_digest_match", "http_status", "final_url", "content_type", "fetched_bytes", "error_digest"}, f"Authority fetch {source_id}")
        exact_keys(artifact["extraction"], {"method", "tool", "tool_digest", "review_status", "body_storage"}, f"Authority extraction {source_id}")
        if artifact["source_id"] != source_id or artifact["source_url"] != source["url"] or artifact["locked_source_digest"] != source["digest"]:
            raise ValueError(f"Authority source identityが不正です: {source_id}")
        if artifact["fetch"]["status"] != "matched" or artifact["fetch"]["fetched_digest"] != source["digest"] or artifact["fetch"]["locked_digest_match"] is not True:
            raise ValueError(f"Authority source digest matchが不正です: {source_id}")
        if artifact["extraction"] != {"method": "locked-body-locator-context-digest", "tool": "argocd-reference-atlas-authority-locator-v1", "tool_digest": index["tool_digest"], "review_status": "automated-unreviewed", "body_storage": "digest-and-locator-context-digest-only"}:
            raise ValueError(f"Authority extraction/review境界が不正です: {source_id}")
        if not artifact["candidate_surfaces"]:
            raise ValueError(f"Source lockにDomain contract candidateがありません: {source_id}")
        for candidate in artifact["candidate_surfaces"]:
            exact_keys(candidate, {"edge_id", "source_id", "reference_url", "locator", "pattern_id", "pattern_kind", "candidate_behavior_id", "capability_id", "target_id", "claim_id", "variant_ids", "surface_ids", "classification_basis", "domain_reference_metadata_digest", "locator_status", "context_digest", "context_start", "context_end", "context_unit", "heading_digest", "classification"}, f"Authority candidate {candidate.get('edge_id')}")
            if candidate["edge_id"] in edge_ids or candidate["source_id"] != source_id:
                raise ValueError(f"Authority edge重複またはsource不一致です: {candidate['edge_id']}")
            edge_ids.add(candidate["edge_id"])
            claim = claims.get(candidate["claim_id"])
            if claim is None or claim["capability_id"] != candidate["capability_id"] or candidate["target_id"] not in target_ids:
                raise ValueError(f"Authority candidateのClaim／Capability／Target接続が不正です: {candidate['edge_id']}")
            if candidate["reference_url"] != source["url"] or candidate["locator_status"] != "root-document" or candidate["context_start"] != 0 or candidate["context_end"] <= 0 or candidate["context_unit"] != "utf16-code-unit" or candidate["context_digest"] != source["digest"]:
                raise ValueError(f"Authority root locatorが不正です: {candidate['edge_id']}")
            if not candidate["variant_ids"] or any(not item.endswith(".argocd-v3-5-2") for item in candidate["variant_ids"]):
                raise ValueError(f"Authority candidateのVersion variantがありません: {candidate['edge_id']}")
            if candidate["heading_digest"] is not None or candidate["classification"] != "candidate-included-unreviewed" or candidate["classification_basis"] != "domain-contract-projection-unreviewed":
                raise ValueError(f"未Review分類境界が不正です: {candidate['edge_id']}")
        record = source_index[source_id]
        exact_keys(record, {"id", "path", "digest", "locked_digest_match", "candidate_surfaces", "locator_status"}, f"Authority source index {source_id}")
        if record["path"] != path.relative_to(ROOT).as_posix() or record["digest"] != sha256(path) or record["candidate_surfaces"] != len(artifact["candidate_surfaces"]) or record["locked_digest_match"] is not True:
            raise ValueError(f"Authority source index driftがあります: {source_id}")

    summary = index["summary"]
    expected_counts = {
        "locked_sources": len(source_by_id), "fetched_digest_matched": len(source_by_id), "fetched_digest_stale": 0,
        "fetch_failed": 0, "candidate_surfaces": len(edge_ids), "root_locators": len(edge_ids),
        "fragments_found": 0, "fragments_not_found": 0, "locator_evaluations_deferred": 0,
        "reference_edges_classified": len(edge_ids), "unclassified_reference_edges": 0,
        "authority_text_surfaces_exhaustive": False, "human_reviewed_surfaces": 0, "core_v2_eligible_surfaces": 0,
    }
    if summary != expected_counts:
        raise ValueError(f"Authority summaryが実体と一致しません: {summary}")
    print(
        f"authority locators validated: sources={len(source_by_id)} matched={summary['fetched_digest_matched']} "
        f"stale={summary['fetched_digest_stale']} deferred={summary['locator_evaluations_deferred']} "
        f"candidate_edges={len(edge_ids)} human_reviewed=0 exhaustive=false"
    )


if __name__ == "__main__":
    main()
