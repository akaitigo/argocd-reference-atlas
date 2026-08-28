#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Authority raw anchorを人手確認用Queueへ損失なく投影する共通実装。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BODY_INDEX = ROOT / "authority" / "body-inventory.snapshot.json"
BODY_DIR = ROOT / "authority" / "body-inventory-draft"
LOCATOR_INDEX = ROOT / "authority" / "extraction.snapshot.json"
LOCATOR_DIR = ROOT / "authority" / "locators"
QUEUE_INDEX = ROOT / "authority" / "review-queue.snapshot.json"
QUEUE_DIR = ROOT / "authority" / "review-queue-draft"
DECISIONS = ROOT / "authority" / "reviews" / "decisions.json"
REFERENCE_COMMIT = "de2f016b8b44ea67afdb08c0552044807505984e"
REFERENCE_FILES = [
    {"path": "scripts/lib/authority-review-queue.ts", "sha256": "6a0d44da874e7332d2212416bcbaa9ca93ab7a2cda9d5c28b846fecb847c2187"},
    {"path": "scripts/generate-authority-review-queue.ts", "sha256": "0ddb9e1ed3221c89e68449914e37a94a9104123d3ae0578b2e0a4aed3f57f291"},
    {"path": "scripts/verify-authority-review-queue.ts", "sha256": "3849bd25a409742acdcbb8e028a65cf0d51249ac29c23ba606a14d63b81524f9"},
    {"path": "scripts/test-authority-review-queue.ts", "sha256": "cd6ffd8860645b70f85feb262fffc903d3b0a0aa96c6f9a7181f6ed895e965ec"},
]
TOOL_FILES = [
    ROOT / "scripts" / "authority_review_queue.py",
    ROOT / "scripts" / "generate_authority_review_queue.py",
    ROOT / "scripts" / "validate_authority_review_queue.py",
    ROOT / "scripts" / "test_authority_review_queue.py",
]
DECISION_ACTIONS = {"include", "exclude", "merge", "split"}
RESULT_TYPES = {"controller-surface", "behavior-surface"}


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_digest(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def artifact_digest(value: object) -> str:
    return sha256_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def short_hash(value: str, length: int = 20) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def queue_tool_digest() -> str:
    payload = b"\0".join(path.relative_to(ROOT).as_posix().encode() + b"\0" + path.read_bytes() for path in TOOL_FILES)
    return sha256_bytes(payload)


def exact_keys(value: dict, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label}のfield集合が不正です: actual={sorted(value)} expected={sorted(expected)}")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON rootがObjectではありません: {path.relative_to(ROOT)}")
    return value


def body_artifacts() -> list[dict]:
    index = load_json(BODY_INDEX)
    result = [load_json(ROOT / record["path"]) for record in index["documents"]]
    return sorted(result, key=lambda item: item["document_id"])


def existing_edges() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    index = load_json(LOCATOR_INDEX)
    by_source_locator: dict[str, list[str]] = {}
    by_locator: dict[str, list[str]] = {}
    for record in index["sources"]:
        artifact = load_json(ROOT / record["path"])
        for edge in artifact["candidate_surfaces"]:
            key = f"{edge['source_id']}\0{edge['locator']}"
            by_source_locator.setdefault(key, []).append(edge["edge_id"])
            by_locator.setdefault(edge["locator"], []).append(edge["edge_id"])
    for values in [*by_source_locator.values(), *by_locator.values()]:
        values[:] = sorted(set(values))
    return by_source_locator, by_locator


def matched_edge_ids(artifact: dict, anchor: dict, by_source_locator: dict[str, list[str]], by_locator: dict[str, list[str]]) -> list[str]:
    locator = anchor["locator"]
    candidates = [locator]
    if locator.startswith("tar-entry:"):
        candidates.append(locator.removeprefix("tar-entry:"))
    values: list[str] = []
    for source_id in artifact["source_ids"]:
        for candidate in candidates:
            values.extend(by_source_locator.get(f"{source_id}\0{candidate}", []))
    if artifact["source_ids"] == ["argocd-source-tree"]:
        for candidate in candidates:
            values.extend(by_locator.get(candidate, []))
    return sorted(set(values))


def suggested_priority(anchor: dict, edge_ids: list[str]) -> tuple[int, list[str]]:
    if edge_ids:
        return 0, ["existing-domain-reference-locator-match"]
    if anchor["selector"] in {"markdown-atx-heading-line", "yaml-mapping-key-line", "plain-nonempty-line"}:
        return 1, ["semantic-label-anchor-candidate"]
    return 2, ["structural-or-document-anchor-candidate"]


def suggested_batch_id(priority: int, selector: str, anchor_id: str) -> str:
    bucket = f"{int(short_hash(anchor_id, 2), 16) % 64:02x}"
    selector_id = selector.replace("-line", "").replace("git-tar-", "git-")
    return f"review-p{priority}-{selector_id}-{bucket}"


def review_binding(item: dict) -> dict:
    return {
        "anchor_id": item["anchor_id"],
        "document_id": item["document_id"],
        "document_url": item["document_url"],
        "locked_source_digest": item["locked_source_digest"],
        "inventory_tool_digest": item["inventory_tool_digest"],
        "review_queue_tool_digest": item["review_queue_tool_digest"],
        "locator": item["locator"],
        "context_start": item["context_start"],
        "context_end": item["context_end"],
        "context_unit": item["context_unit"],
        "context_digest": item["context_digest"],
    }


def validate_decisions(decisions: list, item_by_id: dict[str, dict]) -> tuple[set[str], set[str]]:
    seen_decisions: set[str] = set()
    decided_anchors: set[str] = set()
    result_owner: dict[str, str] = {}
    result_ids: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("Review decisionはObjectである必要があります")
        exact_keys(decision, {"decision_id", "action", "anchor_ids", "source_bindings", "reason", "reviewer", "reviewed_at", "review_method", "mapping", "result_items"}, f"Decision {decision.get('decision_id')}")
        decision_id = decision["decision_id"]
        if not re.fullmatch(r"decision\.[a-z0-9.-]+", decision_id) or decision_id in seen_decisions or decision["action"] not in DECISION_ACTIONS:
            raise ValueError(f"Decision identity/actionが不正です: {decision_id}")
        seen_decisions.add(decision_id)
        reviewer = decision["reviewer"].strip()
        if decision["review_method"] != "manual-primary-source" or len(decision["reason"].strip()) < 40 or len(reviewer) < 2 or re.match(r"^(?:auto(?:mated)?|agent|bot|system|machine)(?:$|[-_. ])", reviewer, re.I):
            raise ValueError(f"人手一次資料review provenanceが不足しています: {decision_id}")
        try:
            reviewed_at = datetime.fromisoformat(decision["reviewed_at"])
        except (TypeError, ValueError):
            reviewed_at = None
        if reviewed_at is None or reviewed_at.tzinfo is None:
            raise ValueError(f"reviewed_atがISO date-timeではありません: {decision_id}")
        anchor_ids = decision["anchor_ids"]
        if not anchor_ids or len(anchor_ids) != len(set(anchor_ids)) or len(decision["source_bindings"]) != len(anchor_ids) or len(decision["mapping"]) != len(anchor_ids):
            raise ValueError(f"Decision anchor/binding/mapping cardinalityが不正です: {decision_id}")
        for anchor_id in anchor_ids:
            if anchor_id in decided_anchors or anchor_id not in item_by_id:
                raise ValueError(f"Queue外または重複review anchorです: {anchor_id}")
            decided_anchors.add(anchor_id)
        binding_by_id = {item.get("anchor_id"): item for item in decision["source_bindings"]}
        mapping_by_id = {item.get("old_anchor_id"): item for item in decision["mapping"]}
        if len(binding_by_id) != len(anchor_ids) or len(mapping_by_id) != len(anchor_ids):
            raise ValueError(f"Decision binding/mapping IDが重複しています: {decision_id}")
        for anchor_id in anchor_ids:
            binding = binding_by_id.get(anchor_id)
            if not isinstance(binding, dict):
                raise ValueError(f"Decision source bindingがありません: {anchor_id}")
            exact_keys(binding, {"anchor_id", "document_id", "document_url", "locked_source_digest", "inventory_tool_digest", "review_queue_tool_digest", "locator", "context_start", "context_end", "context_unit", "context_digest"}, f"Decision binding {anchor_id}")
            if binding != review_binding(item_by_id[anchor_id]):
                raise ValueError(f"Decision digest/locator bindingがQueueと一致しません: {anchor_id}")
            mapping = mapping_by_id.get(anchor_id)
            if not isinstance(mapping, dict):
                raise ValueError(f"Decision mappingがありません: {anchor_id}")
            exact_keys(mapping, {"old_anchor_id", "new_item_ids"}, f"Decision mapping {anchor_id}")
            new_ids = mapping["new_item_ids"]
            if len(new_ids) != len(set(new_ids)) or any(not re.fullmatch(r"[a-z][a-z0-9.-]+", item) for item in new_ids):
                raise ValueError(f"Decision mapping result IDが不正です: {anchor_id}")
        results = decision["result_items"]
        decision_result_ids: set[str] = set()
        for result in results:
            exact_keys(result, {"id", "item_type"}, f"Decision result {decision_id}")
            if not re.fullmatch(r"[a-z][a-z0-9.-]+", result["id"]) or result["item_type"] not in RESULT_TYPES:
                raise ValueError(f"Controller/Behavior resultが不正です: {decision_id}")
            if result["id"] in decision_result_ids:
                raise ValueError(f"Decision result IDが重複しています: {decision_id}")
            decision_result_ids.add(result["id"])
            owner = result_owner.get(result["id"])
            if owner and owner != decision_id:
                raise ValueError(f"Result IDが複数decisionで共有されています: {result['id']}")
            result_owner[result["id"]] = decision_id
            result_ids.add(result["id"])
        mapped_ids = sorted(set(item for mapping in decision["mapping"] for item in mapping["new_item_ids"]))
        if mapped_ids != sorted(result["id"] for result in results):
            raise ValueError(f"Decision mappingとresult集合が一致しません: {decision_id}")
        action = decision["action"]
        mappings = decision["mapping"]
        if action == "exclude" and (mapped_ids or results):
            raise ValueError(f"excludeはController/Behavior Surfaceへ昇格できません: {decision_id}")
        if action == "include" and (any(not item["new_item_ids"] for item in mappings) or len(mapped_ids) != sum(len(item["new_item_ids"]) for item in mappings)):
            raise ValueError(f"include mappingが不正です: {decision_id}")
        if action == "merge" and (len(anchor_ids) < 2 or any(not item["new_item_ids"] for item in mappings) or len({tuple(sorted(item["new_item_ids"])) for item in mappings}) != 1):
            raise ValueError(f"merge mappingが不正です: {decision_id}")
        if action == "split" and (len(anchor_ids) != 1 or len(mappings[0]["new_item_ids"]) < 2):
            raise ValueError(f"split mappingが不正です: {decision_id}")
    return decided_anchors, result_ids


def empty_ledger(queue_id: str) -> dict:
    return {
        "schema_version": 1,
        "atlas_id": "argocd-reference-atlas",
        "queue_id": queue_id,
        "status": "incomplete-human-review-required",
        "decisions": [],
    }


def stale_hold(artifact: dict, tool_digest: str) -> dict:
    """stale documentをQueueと昇格経路から隔離するhold recordへ変換する。"""
    return {
        "document_id": artifact["document_id"],
        "document_url": artifact["source_url"],
        "source_ids": artifact["source_ids"],
        "locked_source_digest": artifact["locked_body_digest"],
        "inventory_tool_digest": artifact["extraction"]["tool_digest"],
        "review_queue_tool_digest": tool_digest,
        "locator": "document-root",
        "observed_digest": artifact["fetch"]["observed_digest"],
        "status": "hold-stale-document-relock-required",
        "reason": "locked-document-body-digest-mismatch",
    }


def build_queue() -> tuple[dict, list[dict], dict]:
    body_index = load_json(BODY_INDEX)
    artifacts = body_artifacts()
    tool_digest = queue_tool_digest()
    anchor_ids = sorted(anchor["id"] for artifact in artifacts for anchor in artifact["anchors"])
    if len(anchor_ids) != len(set(anchor_ids)):
        raise ValueError("Authority raw anchor stable IDが重複しています")
    queue_id = f"authority-review-{short_hash(body_index['input_digest'] + chr(0) + chr(0).join(anchor_ids))}"
    input_digest = canonical_digest({"body_input_digest": body_index["input_digest"], "anchor_ids": anchor_ids})
    by_source_locator, by_locator = existing_edges()

    label_groups: dict[str, list[str]] = {}
    for artifact in artifacts:
        if artifact["fetch"]["status"] != "matched":
            continue
        for anchor in artifact["anchors"]:
            if anchor["label_digest"]:
                key = f"{anchor['selector']}\0{anchor['label_digest']}"
                label_groups.setdefault(key, []).append(anchor["id"])
    cluster_by_anchor: dict[str, str] = {}
    for key, ids in label_groups.items():
        if len(ids) > 1:
            cluster_id = f"candidate-cluster-{short_hash(key)}"
            for anchor_id in ids:
                cluster_by_anchor[anchor_id] = cluster_id

    grouped: dict[str, list[dict]] = {}
    stale_holds: list[dict] = []
    for artifact in artifacts:
        if artifact["fetch"]["status"] == "stale":
            stale_holds.append(stale_hold(artifact, tool_digest))
            continue
        if artifact["fetch"]["status"] != "matched":
            continue
        for anchor in artifact["anchors"]:
            edge_ids = matched_edge_ids(artifact, anchor, by_source_locator, by_locator)
            priority, reasons = suggested_priority(anchor, edge_ids)
            batch_id = suggested_batch_id(priority, anchor["selector"], anchor["id"])
            item = {
                "anchor_id": anchor["id"],
                "document_id": artifact["document_id"],
                "document_url": artifact["source_url"],
                "source_ids": artifact["source_ids"],
                "locked_source_digest": artifact["locked_body_digest"],
                "inventory_tool_digest": artifact["extraction"]["tool_digest"],
                "review_queue_tool_digest": tool_digest,
                "locator": anchor["locator"],
                "locator_kind": anchor["locator_kind"],
                "selector": anchor["selector"],
                "parent_anchor_id": anchor["parent_anchor_id"],
                "context_start": anchor["context_start"],
                "context_end": anchor["context_end"],
                "context_unit": anchor["context_unit"],
                "context_digest": anchor["context_digest"],
                "label_digest": anchor["label_digest"],
                "existing_reference_edge_ids": edge_ids,
                "suggested_priority": priority,
                "priority_reasons": reasons,
                "suggested_cluster_id": cluster_by_anchor.get(anchor["id"]),
                "suggested_batch_id": batch_id,
                "state": "pending-human",
            }
            grouped.setdefault(batch_id, []).append(item)

    batches: list[dict] = []
    records: list[dict] = []
    for batch_id in sorted(grouped):
        items = sorted(grouped[batch_id], key=lambda item: item["anchor_id"])
        batch = {
            "schema_version": 1,
            "queue_id": queue_id,
            "batch_id": batch_id,
            "status": "pending-human",
            "machine_assistance": "priority-cluster-and-batch-proposals-only",
            "semantic_decisions": "none",
            "items": items,
        }
        batches.append(batch)
        match = re.fullmatch(r"review-p([0-2])-(.+)-([0-9a-f]{2})", batch_id)
        if not match:
            raise ValueError(f"Review batch IDが不正です: {batch_id}")
        records.append({
            "id": batch_id,
            "path": f"authority/review-queue-draft/{batch_id}.json",
            "digest": artifact_digest(batch),
            "suggested_priority": int(match.group(1)),
            "selector": match.group(2),
            "bucket": match.group(3),
            "items": len(items),
        })

    ledger = empty_ledger(queue_id)
    if DECISIONS.is_file():
        ledger = load_json(DECISIONS)
    exact_keys(ledger, {"schema_version", "atlas_id", "queue_id", "status", "decisions"}, "Authority review decision ledger")
    if ledger["schema_version"] != 1 or ledger["atlas_id"] != "argocd-reference-atlas" or ledger["queue_id"] != queue_id or ledger["status"] != "incomplete-human-review-required":
        raise ValueError("Authority review decision ledger identity/statusが現Queueと一致しません")
    item_by_id = {item["anchor_id"]: item for batch in batches for item in batch["items"]}
    decided, result_ids = validate_decisions(ledger["decisions"], item_by_id)
    priority_counts = {str(priority): sum(1 for item in item_by_id.values() if item["suggested_priority"] == priority) for priority in (0, 1, 2)}
    cluster_ids = {item["suggested_cluster_id"] for item in item_by_id.values() if item["suggested_cluster_id"]}
    index = {
        "schema_version": 1,
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "status": "incomplete-human-review-required",
        "reference": {"repository": "frontend-behavior-atlas", "commit": REFERENCE_COMMIT, "files": REFERENCE_FILES},
        "queue_id": queue_id,
        "input_digest": input_digest,
        "tool_digest": tool_digest,
        "decision_ledger": DECISIONS.relative_to(ROOT).as_posix(),
        "body_storage": "digest-locator-and-offset-only",
        "machine_assistance": "dedupe-candidate-cluster-priority-and-batch-proposals-only",
        "semantic_decisions": "human-only",
        "depth_credit_rule": "Queue、priority、cluster、batch、pending件数をSemantic Surface、Coverage、Depth axis達成へ算入しない。",
        "summary": {
            "eligible_documents": len({item["document_id"] for item in item_by_id.values()}),
            "queued_anchors": len(item_by_id),
            "pending_human": len(item_by_id) - len(decided),
            "human_reviewed": len(decided),
            "suggested_priority_counts": priority_counts,
            "candidate_clusters": len(cluster_ids),
            "clustered_anchors": sum(1 for item in item_by_id.values() if item["suggested_cluster_id"]),
            "batches": len(batches),
            "stale_document_holds": len(stale_holds),
            "decisions": len(ledger["decisions"]),
            "included": sum(1 for item in ledger["decisions"] if item["action"] == "include"),
            "excluded": sum(1 for item in ledger["decisions"] if item["action"] == "exclude"),
            "merged": sum(1 for item in ledger["decisions"] if item["action"] == "merge"),
            "split": sum(1 for item in ledger["decisions"] if item["action"] == "split"),
            "promoted_controller_behavior_items": len(result_ids),
            "semantic_surface_credit": 0,
            "depth_axis_credit": 0,
            "authority_semantics_exhaustive": False,
        },
        "batches": records,
        "stale_holds": sorted(stale_holds, key=lambda item: item["document_id"]),
    }
    return index, batches, ledger
