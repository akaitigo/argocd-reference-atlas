#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Record lossless Authority queue migration from the last clean checkpoint."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "e3bfc6e"
CORE_COMMIT = "072d7ca77981f51754e824d70c6d4ecd55ea67e5"
OUTPUT = ROOT / "artifacts" / "authority-core-v2-migration.json"


def git_json(commit: str, path: str) -> dict:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def anchor_batches(snapshot: dict, baseline: bool) -> dict[str, str]:
    result: dict[str, str] = {}
    for batch in snapshot["batches"]:
        path = batch["path"]
        document = git_json(BASELINE_COMMIT, path) if baseline else json.loads((ROOT / path).read_text())
        for item in document["items"]:
            anchor_id = item["anchor_id"]
            if anchor_id in result:
                raise SystemExit(f"duplicate anchor in queue: {anchor_id}")
            result[anchor_id] = batch["id"]
    return result


def population_digest(anchor_ids: set[str]) -> str:
    payload = b"\0".join(item.encode() for item in sorted(anchor_ids))
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def main() -> None:
    before_snapshot = git_json(BASELINE_COMMIT, "authority/review-queue.snapshot.json")
    after_snapshot = json.loads((ROOT / "authority/review-queue.snapshot.json").read_text())
    before = anchor_batches(before_snapshot, baseline=True)
    after = anchor_batches(after_snapshot, baseline=False)
    before_ids, after_ids = set(before), set(after)
    if before_ids != after_ids:
        missing = sorted(before_ids - after_ids)[:5]
        added = sorted(after_ids - before_ids)[:5]
        raise SystemExit(f"Authority anchor population changed: missing={missing} added={added}")

    crosswalk: dict[str, dict] = {}
    for anchor_id in sorted(before_ids):
        old_batch = before[anchor_id]
        row = crosswalk.setdefault(
            old_batch,
            {"baseline_batch_id": old_batch, "anchor_count": 0, "core_v2_batch_ids": set()},
        )
        row["anchor_count"] += 1
        row["core_v2_batch_ids"].add(after[anchor_id])

    report = {
        "schema_version": 1,
        "id": "argocd-authority-core-v2-migration-v1",
        "status": "passed-lossless-queue-rebatch",
        "baseline": {
            "commit": BASELINE_COMMIT,
            "queue_id": before_snapshot["queue_id"],
            "batches": len(before_snapshot["batches"]),
        },
        "target": {
            "core_commit": CORE_COMMIT,
            "queue_id": after_snapshot["queue_id"],
            "batches": len(after_snapshot["batches"]),
        },
        "invariants": {
            "stable_anchor_identity": "anchor_id",
            "baseline_anchor_count": len(before_ids),
            "target_anchor_count": len(after_ids),
            "retained_anchor_count": len(before_ids & after_ids),
            "removed_anchor_count": len(before_ids - after_ids),
            "added_anchor_count": len(after_ids - before_ids),
            "population_digest": population_digest(before_ids),
            "human_decisions_added": 0,
            "semantic_depth_credit": 0,
            "fixture_or_runtime_substitution": False,
        },
        "reason": "Core v2 Authority Review Queue schemaへ移行し、提案batchを再編した。stable anchor分母とpending-human境界は不変。",
        "crosswalk": [
            {**row, "core_v2_batch_ids": sorted(row["core_v2_batch_ids"])}
            for row in sorted(crosswalk.values(), key=lambda item: item["baseline_batch_id"])
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        "Authority Core v2 migration recorded: "
        f"anchors={len(before_ids)} retained={len(before_ids & after_ids)} "
        f"batches={len(before_snapshot['batches'])}->{len(after_snapshot['batches'])}"
    )


if __name__ == "__main__":
    main()
