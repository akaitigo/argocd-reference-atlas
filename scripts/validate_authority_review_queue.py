#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Authority Review Queueと人手Decision昇格境界をoffline検査する。"""

from __future__ import annotations

import json
import re

from authority_review_queue import DECISIONS, QUEUE_DIR, QUEUE_INDEX, REFERENCE_COMMIT, ROOT, artifact_digest, build_queue, exact_keys


FORBIDDEN_BODY_KEYS = {
    "body", "text", "content", "excerpt", "quote", "snippet", "raw_body", "source_body",
    "context_text", "heading_text", "markdown", "html", "label", "heading",
}


def reject_body_fields(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_BODY_KEYS:
                raise ValueError(f"第三者本文fieldを拒否しました: {path}.{key}")
            reject_body_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for position, child in enumerate(value):
            reject_body_fields(child, f"{path}[{position}]")


def main() -> None:
    expected_index, expected_batches, expected_ledger = build_queue()
    index = json.loads(QUEUE_INDEX.read_text(encoding="utf-8"))
    reject_body_fields(index)
    exact_keys(index, {"schema_version", "atlas_id", "generated_at", "status", "reference", "queue_id", "input_digest", "tool_digest", "decision_ledger", "body_storage", "machine_assistance", "semantic_decisions", "depth_credit_rule", "summary", "batches", "stale_holds"}, "Authority review queue index")
    exact_keys(index["reference"], {"repository", "commit", "files"}, "Authority review queue reference")
    for item in index["reference"]["files"]:
        exact_keys(item, {"path", "sha256"}, f"Authority review queue reference file {item.get('path')}")
    exact_keys(summary := index["summary"], {"eligible_documents", "queued_anchors", "pending_human", "human_reviewed", "suggested_priority_counts", "candidate_clusters", "clustered_anchors", "batches", "stale_document_holds", "decisions", "included", "excluded", "merged", "split", "promoted_controller_behavior_items", "semantic_surface_credit", "depth_axis_credit", "authority_semantics_exhaustive"}, "Authority review queue summary")
    if index != expected_index:
        raise ValueError("Authority review queue indexが入力／tool／decision ledgerの期待値と一致しません")
    if index["reference"]["commit"] != REFERENCE_COMMIT or index["semantic_decisions"] != "human-only":
        raise ValueError("FE Queue正本または人手Decision境界が固定されていません")
    if index["machine_assistance"] != "dedupe-candidate-cluster-priority-and-batch-proposals-only":
        raise ValueError("priority/cluster/batchを機械Decisionへ使用できません")
    if summary["semantic_surface_credit"] != 0 or summary["depth_axis_credit"] != 0 or summary["authority_semantics_exhaustive"] is not False:
        raise ValueError("Queue件数をSemantic Surface／Depth達成へ算入できません")
    expected_files = {f"{batch['batch_id']}.json" for batch in expected_batches}
    actual_files = {path.name for path in QUEUE_DIR.glob("*.json")}
    if actual_files != expected_files:
        raise ValueError("Authority review queue batch集合が不正です")
    seen: set[str] = set()
    for expected in expected_batches:
        path = QUEUE_DIR / f"{expected['batch_id']}.json"
        actual = json.loads(path.read_text(encoding="utf-8"))
        reject_body_fields(actual)
        exact_keys(actual, {"schema_version", "queue_id", "batch_id", "status", "machine_assistance", "semantic_decisions", "items"}, f"Review batch {expected['batch_id']}")
        if actual != expected or artifact_digest(actual) != next(record["digest"] for record in index["batches"] if record["id"] == actual["batch_id"]):
            raise ValueError(f"Review batchが決定論生成値と一致しません: {actual['batch_id']}")
        if actual["status"] != "pending-human" or actual["machine_assistance"] != "priority-cluster-and-batch-proposals-only" or actual["semantic_decisions"] != "none":
            raise ValueError(f"Review batchの未判断境界が不正です: {actual['batch_id']}")
        for item in actual["items"]:
            exact_keys(item, {"anchor_id", "document_id", "document_url", "source_ids", "locked_source_digest", "inventory_tool_digest", "review_queue_tool_digest", "locator", "locator_kind", "selector", "parent_anchor_id", "context_start", "context_end", "context_unit", "context_digest", "label_digest", "existing_reference_edge_ids", "suggested_priority", "priority_reasons", "suggested_cluster_id", "suggested_batch_id", "state"}, f"Review item {item.get('anchor_id')}")
            if item["anchor_id"] in seen or not re.fullmatch(r"anchor-[0-9a-f]{20}", item["anchor_id"]):
                raise ValueError(f"Queue anchor stable IDが重複または不正です: {item['anchor_id']}")
            seen.add(item["anchor_id"])
            if item["state"] != "pending-human" or item["suggested_batch_id"] != actual["batch_id"] or item["suggested_priority"] not in (0, 1, 2):
                raise ValueError(f"Queue itemのpending/proposal境界が不正です: {item['anchor_id']}")
            for digest in (item["locked_source_digest"], item["inventory_tool_digest"], item["review_queue_tool_digest"], item["context_digest"]):
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                    raise ValueError(f"Queue item digestが不正です: {item['anchor_id']}")
    for record in index["batches"]:
        exact_keys(record, {"id", "path", "digest", "suggested_priority", "selector", "bucket", "items"}, f"Review batch record {record.get('id')}")
    for hold in index["stale_holds"]:
        exact_keys(hold, {"document_id", "document_url", "source_ids", "locked_source_digest", "inventory_tool_digest", "review_queue_tool_digest", "locator", "observed_digest", "status", "reason"}, f"Stale hold {hold.get('document_id')}")
        if hold["status"] != "hold-stale-document-relock-required" or hold["reason"] != "locked-document-body-digest-mismatch":
            raise ValueError(f"stale documentがholdされていません: {hold.get('document_id')}")
    ledger = json.loads(DECISIONS.read_text(encoding="utf-8"))
    reject_body_fields(ledger)
    if ledger != expected_ledger:
        raise ValueError("Decision ledgerがQueue検証時の入力と一致しません")
    if len(seen) != summary["queued_anchors"] or summary["pending_human"] != len(seen) - summary["human_reviewed"]:
        raise ValueError("Queue全anchor／pending集計が不正です")
    if summary["stale_document_holds"] != len(index["stale_holds"]):
        raise ValueError("stale document hold集計が不正です")
    print(
        f"Authority review queue validated: anchors={len(seen)} batches={summary['batches']} "
        f"pending-human={summary['pending_human']} decisions={summary['decisions']} "
        f"stale-holds={summary['stale_document_holds']} semantic/depth-credit=0"
    )


if __name__ == "__main__":
    main()
