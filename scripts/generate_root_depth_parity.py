#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Bind the root depth parity input to the definitive gap without claiming completion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "definitive" / "argocd-depth-parity.json"
REFERENCE = ROOT / "authority" / "FE_DEPTH_REFERENCE.json"
ROOT_DEPTH = ROOT / "depth.parity.yaml"
OUTPUT = ROOT / "artifacts" / "core-v2" / "root-depth-parity-closure.json"
INPUT_PATHS = [SOURCE, REFERENCE, ROOT_DEPTH]
REFERENCE_DIGEST = "sha256:2452696f9807b7d4a8ffb22b3ba37f079a25a34ac2370d78423445b96064582a"
REFERENCE_COMMIT = "4a0b2df8e2091a963bd0e0e1bbccef9c84b49a45"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path.relative_to(ROOT)}")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path.relative_to(ROOT)}")
    return value


def build() -> dict[str, Any]:
    source = load_json(SOURCE)
    root_depth = load_yaml(ROOT_DEPTH)
    axes = source["axes"]
    axis_status = {axis["id"]: axis["status"] for axis in axes}
    open_axes = [axis["id"] for axis in axes if axis["status"] != "satisfied"]
    blockers = [
        "depth-parity-incomplete",
        "authority-semantic-review-zero",
        "approved-variant-denominator-zero",
        "dedicated-runtime-rows-remaining",
    ]
    return {
        "schema_version": 1,
        "id": "argocd-root-depth-parity-closure-v1",
        "status": "blocked-human-authority-and-proof-closure",
        "inputs": {path.relative_to(ROOT).as_posix(): digest(path) for path in INPUT_PATHS},
        "dependency_contract": {
            "graph_output": "artifacts/core-v2/root-depth-parity-closure.json",
            "tracked_input_paths": [path.relative_to(ROOT).as_posix() for path in INPUT_PATHS],
            "stale_on_any_input_digest_change": True,
            "required_rerun": "python3 scripts/generate_root_depth_parity.py && python3 scripts/test_root_depth_parity.py",
            "digest_only_closure_forbidden": True,
        },
        "policy": {
            "root_file_required": True,
            "reference_commit_pinned": True,
            "root_completion_status_must_remain_incomplete_until_gap_zero": True,
            "authority_absolute_counts_transplant_forbidden": True,
            "runtime_credit_requires_dedicated_rows": True,
        },
        "source_depth_parity": {
            "path": "definitive/argocd-depth-parity.json",
            "status": source["status"],
            "summary": source["summary"],
            "open_axes": open_axes,
            "axis_status": axis_status,
            "completion_claim": source["completion_claim"],
        },
        "root_depth_parity": {
            "path": "depth.parity.yaml",
            "present": ROOT_DEPTH.is_file(),
            "completion_status": root_depth["completion_status"],
            "row_count": len(root_depth["rows"]),
            "reference_path": root_depth["reference"]["path"],
            "reference_digest": root_depth["reference"]["digest"],
            "reference_commit": root_depth["reference"]["commit"],
        },
        "credit": {
            "semantic": 0,
            "runtime": 0,
            "completion": 0,
        },
        "blockers": blockers,
    }


def validate(document: dict[str, Any]) -> None:
    if document != build():
        raise ValueError("root Depth Parity closure artifactが現在入力からの導出値と一致しません")
    source = document["source_depth_parity"]
    root_depth = document["root_depth_parity"]
    if source["status"] != "incomplete" or source["completion_claim"] != "neither-bounded-complete-nor-subject-definitive":
        raise ValueError("source depth parityが未完状態を失っています")
    if source["summary"] != {"satisfied": 1, "partial": 15, "missing": 2}:
        raise ValueError("source depth parity summaryが変化しています")
    if source["axis_status"].get("non-regression-gate") != "satisfied":
        raise ValueError("単独のsatisfied軸が崩れています")
    if len(source["open_axes"]) != 17:
        raise ValueError("open axis countが変化しています")
    if not root_depth["present"] or root_depth["completion_status"] != "incomplete" or root_depth["row_count"] != 0:
        raise ValueError("root depth parityがfail-closed shapeを失っています")
    if root_depth["reference_path"] != "authority/FE_DEPTH_REFERENCE.json":
        raise ValueError("root reference pathが不正です")
    if root_depth["reference_digest"] != REFERENCE_DIGEST or root_depth["reference_commit"] != REFERENCE_COMMIT:
        raise ValueError("root reference pinが不正です")
    if digest(REFERENCE) != REFERENCE_DIGEST:
        raise ValueError("固定FE Depth Reference digestが一致しません")
    if document["credit"] != {"semantic": 0, "runtime": 0, "completion": 0}:
        raise ValueError("depth parity closureへcreditが付与されています")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = build()
    if args.check:
        validate(load_json(OUTPUT))
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validate(document)
    print(
        "Root Depth Parity closure: "
        f"status={document['status']} open_axes={len(document['source_depth_parity']['open_axes'])} "
        f"rows={document['root_depth_parity']['row_count']}"
    )


if __name__ == "__main__":
    main()
