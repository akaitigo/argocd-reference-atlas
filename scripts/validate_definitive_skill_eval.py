#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Definitive Skill matrix、境界、全Target状態、独立Forward記録を検証する。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_definitive_skill_eval import FORWARD, OUTPUT, RAW_RESULT, build_artifact, build_raw_result  # noqa: E402
from generate_skill_mastery_contract import OUTPUT as CONTRACT, build_contract  # noqa: E402


def main() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract != build_contract():
        raise ValueError("Skill mastery contractがmastery／coverage正本と一致しません")
    artifact = json.loads(OUTPUT.read_text(encoding="utf-8"))
    expected = build_artifact()
    if artifact != expected:
        raise ValueError("Definitive Skill EvalがRouter／Manifest／Evidence／Forward入力と一致しません")
    raw = json.loads(RAW_RESULT.read_text(encoding="utf-8"))
    if raw != build_raw_result(artifact):
        raise ValueError("Definitive Skill Evidence raw resultがEval Artifactと一致しません")
    summary = artifact["summary"]
    if summary != {
        "outcomes": 8,
        "surfaces": 14,
        "matrix_cells": 112,
        "matrix_contract_passed": 112,
        "matrix_contract_failed": 0,
        "routed": 111,
        "mastery_routing_gaps": 1,
        "supported_runtime_targets_routed": 21,
        "uncovered_supported_runtime_targets": [],
        "target_states": {"covered": 8, "missing": 8, "partial": 14},
        "open_required_targets": 22,
        "boundary_cases": 7,
        "boundary_passed": 7,
        "boundary_failed": 0,
        "matrix_pass_is_completion": False,
    }:
        raise ValueError(f"Definitive Skill Eval summaryが期待する未完了境界と一致しません: {summary}")
    if artifact["status"] != "incomplete-target-or-routing-gaps" or artifact["semantic_scope"] != "deterministic-router-contract-plus-independent-agent-forward-eval-not-completion-certificate":
        raise ValueError("Matrix passをCompletionへ昇格しています")
    matrix_ids = {item["id"] for item in artifact["matrix"]}
    if len(matrix_ids) != 112 or any(item["result"] != "pass" for item in artifact["matrix"]):
        raise ValueError("8 Outcome x 14 Surface matrixが完全ではありません")
    gaps = [item for item in artifact["matrix"] if item["support_status"] == "mastery-routing-gap"]
    if [item["id"] for item in gaps] != ["skill.build.failure-recovery"]:
        raise ValueError("Mastery routing gapが隠蔽または増減しています")
    if len(artifact["all_target_state_inventory"]) != 30 or any(item["requirement"] != "required" for item in artifact["all_target_state_inventory"]):
        raise ValueError("全required Target stateが機械記録されていません")
    for item in artifact["matrix"]:
        if not item["source_bindings"] or not any(binding["runtime_proof"] for binding in item["runtime_evidence_bindings"]):
            raise ValueError(f"Matrix cellにAuthorityまたは実Kubernetes/controller Evidenceがありません: {item['id']}")
    forward = json.loads(FORWARD.read_text(encoding="utf-8"))
    if forward.get("verdict") != "pass" or forward.get("completion_claim") is not False:
        raise ValueError("独立Agent Forward Evalが未合格またはCompletionへ誤用されています")
    if forward.get("evaluator", {}).get("role") != "independent-agent" or forward.get("summary") != {"cases": 10, "passed": 10, "failed": 0, "outcomes_covered": ["build", "choose", "delegate", "evolve", "operate", "troubleshoot", "understand", "verify"]}:
        raise ValueError("独立Agent provenanceまたは8 Outcome coverageが不正です")
    print(
        "Definitive Skill Eval validated: matrix=112/112 routed=111 routing-gap=1 "
        "targets=30 states=8/14/8 boundaries=7/7 independent-forward=10/10 completion=false"
    )


if __name__ == "__main__":
    main()
