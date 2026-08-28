#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""raw Authority anchor母集団、未Review境界、専用非後退baselineを検査する。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "authority" / "body-inventory.snapshot.json"
ARTIFACT_DIR = ROOT / "authority" / "body-inventory-draft"
BASELINE = ROOT / "baselines" / "authority-body-inventory-v1.json"
MIGRATION = ROOT / "migrations" / "authority-body-inventory-v1.json"
REPORT = ROOT / "artifacts" / "authority-body-non-regression-report.json"
GENERATOR = ROOT / "scripts" / "generate_authority_body_inventory.py"
EXPECTED_REFERENCE_COMMIT = "841ec2fa399606a10305021a8bcd396713b8cee5"
SELECTOR_CONTRACT = [
    "document-root",
    "git-tar-regular-file",
    "markdown-atx-heading-line",
    "yaml-mapping-key-line",
    "plain-nonempty-line",
]
FORBIDDEN_BODY_KEYS = {
    "body", "text", "content", "excerpt", "quote", "snippet", "raw_body", "source_body",
    "context_text", "heading_text", "markdown", "html", "label", "heading",
}


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def exact_keys(value: dict, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label}のfieldが不一致です: actual={sorted(value)} expected={sorted(expected)}")


def reject_body_fields(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_BODY_KEYS:
                raise ValueError(f"第三者本文fieldを拒否しました: {path}.{key}")
            reject_body_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for position, child in enumerate(value):
            reject_body_fields(child, f"{path}[{position}]")


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("\0".join(str(part) for part in parts).encode()).hexdigest()[:20]
    return f"{prefix}-{digest}"


def main() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    reject_body_fields(index)
    exact_keys(index, {"schema_version", "atlas_id", "generated_at", "status", "reference", "input_digest", "tool_digest", "body_storage", "selector_contract", "promotion_contract", "stale_boundary", "summary", "documents"}, "Authority body index")
    exact_keys(index["reference"], {"repository", "commit", "files"}, "Authority body reference")
    exact_keys(index["promotion_contract"], {"initial_status", "raw_anchor_semantic_surface_credit", "raw_anchor_depth_axis_credit", "promotion_requires", "rule"}, "Authority body promotion contract")
    exact_keys(index["stale_boundary"], {"rule", "matched_required_for_selector_exhaustive"}, "Authority body stale boundary")
    exact_keys(index["summary"], {"source_entries", "unique_documents", "matched_documents", "stale_documents", "failed_documents", "selector_exhaustive_documents", "raw_anchors", "anchors_by_selector", "classified_anchors", "unclassified_anchors", "human_reviewed_anchors", "promoted_controller_behavior_surfaces", "core_v2_eligible_artifacts", "semantic_surface_credit", "depth_axis_credit", "authority_semantics_exhaustive"}, "Authority body summary")
    if index["schema_version"] != 1 or index["atlas_id"] != "argocd-reference-atlas" or index["status"] != "incomplete-human-review-required":
        raise ValueError("Authority body inventoryを未完了以外にできません")
    if index["reference"]["commit"] != EXPECTED_REFERENCE_COMMIT or index["reference"]["repository"] != "frontend-behavior-atlas":
        raise ValueError("FE Authority denominator正本が固定されていません")
    if len(index["reference"]["files"]) != 5:
        raise ValueError("FE Authority denominator参照fileが不足しています")
    for item in index["reference"]["files"]:
        exact_keys(item, {"path", "sha256"}, "Authority body reference file")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("FE Authority denominator参照digestが不正です")
    if index["tool_digest"] != sha256_path(GENERATOR) or index["body_storage"] != "digest-locator-and-offset-only" or index["selector_contract"] != SELECTOR_CONTRACT:
        raise ValueError("Authority body tool／storage／selector contractがdriftしています")
    expected_promotion = {
        "initial_status": "pending-human",
        "raw_anchor_semantic_surface_credit": 0,
        "raw_anchor_depth_axis_credit": 0,
        "promotion_requires": ["human-decision", "stable-controller-or-behavior-surface-id", "source-edge", "proof-obligation"],
        "rule": "人手decision前のraw anchor件数をSemantic Surface、Coverage、Depth axisの達成へ算入しない。",
    }
    if index["promotion_contract"] != expected_promotion or index["stale_boundary"]["matched_required_for_selector_exhaustive"] is not True:
        raise ValueError("raw anchorの未Review／stale／昇格境界が不正です")

    lock = yaml.safe_load((ROOT / "sources.lock.yaml").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in lock["sources"]}
    documents = {item["id"]: item for item in index["documents"]}
    expected_document_ids = {f"document-{source_id}" for source_id in sources}
    if set(documents) != expected_document_ids or len(documents) != len(index["documents"]):
        raise ValueError("Authority unique document集合がSource lockと一致しません")
    actual_files = {path.name for path in ARTIFACT_DIR.glob("*.json")}
    if actual_files != {f"{document_id}.json" for document_id in expected_document_ids}:
        raise ValueError("Authority body artifact集合がunique document集合と一致しません")

    all_anchor_ids: set[str] = set()
    selector_counts: dict[str, int] = {}
    current_by_document: dict[str, dict] = {}
    total_anchors = 0
    for document_id in sorted(expected_document_ids):
        record = documents[document_id]
        exact_keys(record, {"id", "path", "digest", "fetch_status", "source_entries", "anchors", "anchors_by_selector"}, f"Authority body record {document_id}")
        path = ROOT / record["path"]
        artifact = json.loads(path.read_text(encoding="utf-8"))
        reject_body_fields(artifact)
        exact_keys(artifact, {"schema_version", "document_id", "source_ids", "source_url", "authority_family", "locked_body_digest", "fetch", "extraction", "anchors"}, f"Authority body artifact {document_id}")
        exact_keys(artifact["fetch"], {"status", "observed_digest", "locked_digest_match", "observed_bytes", "error_digest"}, f"Authority body fetch {document_id}")
        exact_keys(artifact["extraction"], {"method", "tool", "tool_digest", "selector_contract", "selector_exhaustive_for_locked_body", "authority_semantics_exhaustive", "review_status", "body_storage"}, f"Authority body extraction {document_id}")
        if artifact["document_id"] != document_id or len(artifact["source_ids"]) != 1:
            raise ValueError(f"Authority body document identityが不正です: {document_id}")
        source_id = artifact["source_ids"][0]
        source = sources.get(source_id)
        if source is None or artifact["source_url"] != source["url"] or artifact["locked_body_digest"] != source["digest"]:
            raise ValueError(f"Authority body Source lock接続が不正です: {document_id}")
        if artifact["fetch"] != {"status": "matched", "observed_digest": source["digest"], "locked_digest_match": True, "observed_bytes": artifact["fetch"]["observed_bytes"], "error_digest": None}:
            raise ValueError(f"Authority body matched境界が不正です: {document_id}")
        extraction = artifact["extraction"]
        if extraction != {"method": "fixed-selector-raw-anchor-v1", "tool": "argocd-reference-atlas-authority-body-inventory-v1", "tool_digest": index["tool_digest"], "selector_contract": SELECTOR_CONTRACT, "selector_exhaustive_for_locked_body": True, "authority_semantics_exhaustive": False, "review_status": "automated-unreviewed", "body_storage": "digest-locator-and-offset-only"}:
            raise ValueError(f"Authority body extraction境界が不正です: {document_id}")
        if not artifact["anchors"]:
            raise ValueError(f"matched documentにraw anchorがありません: {document_id}")
        per_document: dict[str, int] = {}
        document_anchor_ids: set[str] = set()
        for position, item in enumerate(artifact["anchors"]):
            exact_keys(item, {"id", "locator", "locator_kind", "selector", "parent_anchor_id", "context_start", "context_end", "context_unit", "context_digest", "label_digest", "classification_status", "surface_ids"}, f"Authority raw anchor {document_id}:{position}")
            if item["id"] in all_anchor_ids or item["id"] in document_anchor_ids:
                raise ValueError(f"Authority raw anchor IDが重複しています: {item['id']}")
            document_anchor_ids.add(item["id"])
            all_anchor_ids.add(item["id"])
            zero_length_git_entry = item["selector"] == "git-tar-regular-file" and item["context_end"] == item["context_start"]
            if item["selector"] not in SELECTOR_CONTRACT or item["context_unit"] != "byte" or item["context_start"] < 0 or item["context_end"] < item["context_start"] or (item["context_end"] == item["context_start"] and not zero_length_git_entry):
                raise ValueError(f"Authority raw anchor locatorが不正です: {item['id']}")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", item["context_digest"]) or (item["label_digest"] is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", item["label_digest"])):
                raise ValueError(f"Authority raw anchor digestが不正です: {item['id']}")
            expected_id = stable_id("anchor", document_id, item["selector"], item["locator"], item["context_start"], item["context_end"], item["context_digest"])
            if item["id"] != expected_id or item["classification_status"] != "pending-human" or item["surface_ids"] != []:
                raise ValueError(f"Authority raw anchor stable ID／未Review境界が不正です: {item['id']}")
            if position == 0:
                if item["selector"] != "document-root" or item["locator"] != "document-root" or item["parent_anchor_id"] is not None:
                    raise ValueError(f"Authority document rootが不正です: {document_id}")
            elif item["parent_anchor_id"] != artifact["anchors"][0]["id"]:
                raise ValueError(f"Authority raw anchor parentがdocument rootではありません: {item['id']}")
            per_document[item["selector"]] = per_document.get(item["selector"], 0) + 1
            selector_counts[item["selector"]] = selector_counts.get(item["selector"], 0) + 1
        total_anchors += len(artifact["anchors"])
        if record != {"id": document_id, "path": path.relative_to(ROOT).as_posix(), "digest": sha256_path(path), "fetch_status": "matched", "source_entries": 1, "anchors": len(artifact["anchors"]), "anchors_by_selector": dict(sorted(per_document.items()))}:
            raise ValueError(f"Authority body index recordがArtifactと一致しません: {document_id}")
        current_by_document[document_id] = artifact

    expected_summary = {
        "source_entries": len(sources),
        "unique_documents": len(sources),
        "matched_documents": len(sources),
        "stale_documents": 0,
        "failed_documents": 0,
        "selector_exhaustive_documents": len(sources),
        "raw_anchors": total_anchors,
        "anchors_by_selector": dict(sorted(selector_counts.items())),
        "classified_anchors": 0,
        "unclassified_anchors": total_anchors,
        "human_reviewed_anchors": 0,
        "promoted_controller_behavior_surfaces": 0,
        "core_v2_eligible_artifacts": 0,
        "semantic_surface_credit": 0,
        "depth_axis_credit": 0,
        "authority_semantics_exhaustive": False,
    }
    if index["summary"] != expected_summary:
        raise ValueError("Authority body summaryがArtifact実体と一致しません")

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    migration = json.loads(MIGRATION.read_text(encoding="utf-8"))
    reject_body_fields(baseline)
    reject_body_fields(migration)
    exact_keys(baseline, {"schema_version", "id", "captured_at", "source_entries", "unique_documents", "tool_digest", "selector_contract", "documents"}, "Authority body baseline")
    exact_keys(migration, {"schema_version", "baseline_id", "replacements"}, "Authority body migration")
    if baseline["id"] != "authority-body-inventory-v1-2026-08-28" or migration["baseline_id"] != baseline["id"] or baseline["tool_digest"] != index["tool_digest"] or baseline["selector_contract"] != SELECTOR_CONTRACT:
        raise ValueError("Authority body baseline identityが不正です")
    if index["summary"]["source_entries"] < baseline["source_entries"] or index["summary"]["unique_documents"] < baseline["unique_documents"]:
        raise ValueError("Authority body Source／document floorが縮小しています")
    baseline_anchor_ids: set[str] = set()
    baseline_by_document: dict[str, dict] = {}
    for item in baseline["documents"]:
        exact_keys(item, {"id", "path", "locked_body_digest", "source_ids", "anchor_ids"}, f"Authority baseline document {item.get('id')}")
        if item["id"] in baseline_by_document or len(item["anchor_ids"]) != len(set(item["anchor_ids"])):
            raise ValueError("Authority baseline document／anchor IDが重複しています")
        baseline_by_document[item["id"]] = item
        for anchor_id in item["anchor_ids"]:
            if anchor_id in baseline_anchor_ids:
                raise ValueError("Authority baseline anchor IDがdocument間で重複しています")
            baseline_anchor_ids.add(anchor_id)

    replacements: dict[str, dict] = {}
    replacement_new_ids: set[str] = set()
    for item in migration["replacements"]:
        exact_keys(item, {"old_anchor_id", "new_anchor_ids", "execution_proof", "migration_evidence", "reason"}, f"Authority anchor migration {item.get('old_anchor_id')}")
        if item["old_anchor_id"] not in baseline_anchor_ids or item["old_anchor_id"] in replacements or not item["new_anchor_ids"] or len(item["reason"]) < 20:
            raise ValueError("Authority anchor migration mappingが不正です")
        for new_id in item["new_anchor_ids"]:
            if new_id not in all_anchor_ids or new_id in replacement_new_ids:
                raise ValueError("Authority anchor replacementが現行IDでないか共有されています")
            replacement_new_ids.add(new_id)
        if item["execution_proof"] == item["migration_evidence"]:
            raise ValueError("Authority anchor replacementのProofとMigration Evidenceを分離してください")
        for evidence_path in (item["execution_proof"], item["migration_evidence"]):
            if not (ROOT / evidence_path).is_file():
                raise ValueError(f"Authority anchor migration Evidenceがありません: {evidence_path}")
        replacements[item["old_anchor_id"]] = item

    retained = 0
    replaced = 0
    for document_id, expected in baseline_by_document.items():
        current = current_by_document.get(document_id)
        if current is None or current["locked_body_digest"] != expected["locked_body_digest"] or current["source_ids"] != expected["source_ids"]:
            raise ValueError(f"Authority baseline documentが削除または置換されています: {document_id}")
        for anchor_id in expected["anchor_ids"]:
            if anchor_id in all_anchor_ids:
                retained += 1
            elif anchor_id in replacements:
                replaced += 1
            else:
                raise ValueError(f"Authority raw anchorがMappingなしで削除されています: {anchor_id}")
    for old_id in replacements:
        if old_id in all_anchor_ids:
            raise ValueError(f"現存Authority anchorを置換扱いにできません: {old_id}")
    report = {
        "schema_version": 1,
        "baseline_id": baseline["id"],
        "baseline_anchors": len(baseline_anchor_ids),
        "current_anchors": len(all_anchor_ids),
        "retained": retained,
        "replaced": replaced,
        "added": len(all_anchor_ids) - retained - len(replacement_new_ids),
        "document_floor": f"{len(baseline_by_document)}/{len(current_by_document)}",
        "status": "pass",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Authority body inventory validated: documents={len(sources)} matched={len(sources)} stale=0 anchors={total_anchors} pending-human={total_anchors} semantic-credit=0; baseline retained={retained}/{len(baseline_anchor_ids)}")


if __name__ == "__main__":
    main()
