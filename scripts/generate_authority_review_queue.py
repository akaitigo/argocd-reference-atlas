#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Authority raw anchorの人手Review Queueを決定論的に生成する。"""

from __future__ import annotations

import json

from authority_review_queue import DECISIONS, QUEUE_DIR, QUEUE_INDEX, ROOT, build_queue, empty_ledger


def main() -> None:
    index, batches, ledger = build_queue()
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    expected = {f"{batch['batch_id']}.json" for batch in batches}
    for path in QUEUE_DIR.glob("*.json"):
        if path.name not in expected:
            path.unlink()
    for batch in batches:
        path = QUEUE_DIR / f"{batch['batch_id']}.json"
        path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    if not DECISIONS.exists():
        DECISIONS.write_text(json.dumps(empty_ledger(index["queue_id"]), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif ledger["queue_id"] != index["queue_id"]:
        raise ValueError("既存Decision ledgerを別Queue IDへ自動移行できません")
    QUEUE_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = index["summary"]
    print(
        f"Authority review queue: anchors={summary['queued_anchors']} batches={summary['batches']} "
        f"pending-human={summary['pending_human']} decisions={summary['decisions']} "
        f"stale-holds={summary['stale_document_holds']} semantic/depth-credit=0"
    )


if __name__ == "__main__":
    main()
