#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Authority Review Decision境界の正例・負例をlocal fixtureで検証する。"""

from __future__ import annotations

from copy import deepcopy

from authority_review_queue import body_artifacts, build_queue, review_binding, stale_hold, validate_decisions


def expect_rejected(label: str, decision: dict, items: dict[str, dict]) -> None:
    try:
        validate_decisions([decision], items)
    except ValueError:
        return
    raise ValueError(f"不正なAuthority review decisionを受理しました: {label}")


def main() -> None:
    _, batches, _ = build_queue()
    items = {item["anchor_id"]: item for batch in batches for item in batch["items"]}
    first = items[sorted(items)[0]]
    valid = {
        "decision_id": "decision.contract-fixture-include",
        "action": "include",
        "anchor_ids": [first["anchor_id"]],
        "source_bindings": [review_binding(first)],
        "rationale": "一次資料の固定locatorを人が確認し、Controller Surfaceへ昇格する根拠と境界を記録した。",
        "reviewer": "human-reviewer-fixture",
        "reviewed_at": "2026-08-28T12:00:00+09:00",
        "review_method": "manual-primary-source",
        "mapping": [{"old_anchor_id": first["anchor_id"], "new_item_ids": ["controller.fixture-surface"]}],
        "result_items": [{"id": "controller.fixture-surface", "item_type": "surface"}],
    }
    decided, promoted = validate_decisions([valid], items)
    if decided != {first["anchor_id"]} or promoted != {"controller.fixture-surface"}:
        raise ValueError("正しい人手Decisionのmapping結果が不正です")

    automated = deepcopy(valid)
    automated["reviewer"] = "agent"
    expect_rejected("machine-reviewer", automated, items)

    stale_binding = deepcopy(valid)
    stale_binding["source_bindings"][0]["locked_source_digest"] = "sha256:" + "0" * 64
    expect_rejected("source-digest-mismatch", stale_binding, items)

    locator_mismatch = deepcopy(valid)
    locator_mismatch["source_bindings"][0]["context_start"] += 1
    expect_rejected("locator-offset-mismatch", locator_mismatch, items)

    mapping_mismatch = deepcopy(valid)
    mapping_mismatch["result_items"][0]["id"] = "controller.unmapped-result"
    expect_rejected("mapping-result-mismatch", mapping_mismatch, items)

    body_field = deepcopy(valid)
    body_field["source_bindings"][0]["text"] = "forbidden"
    expect_rejected("unexpected-body-field", body_field, items)

    stale = deepcopy(body_artifacts()[0])
    stale["fetch"]["status"] = "stale"
    hold = stale_hold(stale, first["review_queue_tool_digest"])
    if hold["status"] != "hold-stale-document-relock-required" or hold["reason"] != "locked-document-body-digest-mismatch":
        raise ValueError("stale documentがQueue昇格経路からholdされません")

    print("Authority review decision contract tests passed: positive=1 negative=5 stale-hold=1")


if __name__ == "__main__":
    main()
