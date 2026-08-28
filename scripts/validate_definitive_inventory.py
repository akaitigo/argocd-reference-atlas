#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Domain-native Definitive InventoryのID、Coverage、Evidence接続を検査する。"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "definitive" / "surface-inventory.yaml"
GAP_LEDGER = ROOT / "definitive" / "gap-ledger.yaml"
PARITY_MATRIX = ROOT / "definitive" / "fe-parity-matrix.json"
DEPTH_PARITY = ROOT / "definitive" / "argocd-depth-parity.json"


def ids(path: Path, pattern: str) -> set[str]:
    regex = re.compile(pattern)
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = regex.match(line)
        if match:
            value = match.group(1)
            if value in result:
                raise ValueError(f"duplicate ID in {path.relative_to(ROOT)}: {value}")
            result.add(value)
    return result


def inline_items() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^  - \{(.+)}$", line)
        if not match:
            continue
        item: dict[str, str] = {}
        for pair in match.group(1).split(", "):
            key, value = pair.split(": ", 1)
            item[key] = value
        result.append(item)
    return result


def binding_ids() -> tuple[set[str], set[str]]:
    evidence: set[str] = set()
    items: set[str] = set()
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        evidence_match = re.match(r"^  - evidence_id: (\S+)$", line)
        item_match = re.match(r"^    item_ids: \[(.*)]$", line)
        if evidence_match:
            evidence.add(evidence_match.group(1))
        if item_match:
            items.update(value.strip() for value in item_match.group(1).split(","))
    return evidence, items


def main() -> None:
    inventory_items = inline_items()
    inventory_ids = {item["id"] for item in inventory_items}
    if len(inventory_ids) != len(inventory_items):
        raise ValueError("Inventory item IDが重複しています")

    coverage_ids = ids(ROOT / "coverage.yaml", r"^  - id: (\S+)$")
    evidence_ids = {
        next(
            line.split(": ", 1)[1]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("id: ")
        )
        for path in (ROOT / "evidence" / "records").glob("*.evidence.yaml")
    }
    gap_ids = ids(GAP_LEDGER, r"^  - id: (gap\.\S+)$")

    allowed_states = {"covered", "partial", "missing"}
    required_areas = {
        "application", "applicationset", "project", "connection", "auth", "sync", "diff", "health",
        "drift", "secret-boundary", "extensions", "availability", "observability", "recovery",
        "migration", "compatibility", "performance", "notifications", "system", "comparison",
    }
    actual_areas = {item["area"] for item in inventory_items}
    if missing := required_areas - actual_areas:
        raise ValueError(f"Inventory areaが不足しています: {sorted(missing)}")

    for item in inventory_items:
        if item["target_id"] not in coverage_ids:
            raise ValueError(f"{item['id']}が未定義Targetを参照しています: {item['target_id']}")
        if item["state"] not in allowed_states:
            raise ValueError(f"{item['id']}のstateが不正です: {item['state']}")
        locator = item["locator"]
        if locator.startswith(("definitive/", "labs/")) and not (ROOT / locator).is_file():
            raise ValueError(f"{item['id']}のlocal locatorがありません: {locator}")

    required_generators = {
        "list", "cluster", "git-directory", "git-file", "scm-provider", "pull-request",
        "cluster-decision-resource", "matrix", "merge", "plugin",
    }
    generator_ids = {
        item["id"].removeprefix("applicationset.generator.")
        for item in inventory_items
        if item["id"].startswith("applicationset.generator.")
    }
    if generator_ids != required_generators:
        raise ValueError(f"ApplicationSet Generator Inventoryが不一致です: {sorted(generator_ids)}")

    bound_evidence, bound_items = binding_ids()
    if missing := bound_evidence - evidence_ids:
        raise ValueError(f"未定義Evidence bindingがあります: {sorted(missing)}")
    if missing := bound_items - inventory_ids:
        raise ValueError(f"未定義Inventory item bindingがあります: {sorted(missing)}")
    covered_or_partial = {item["id"] for item in inventory_items if item["state"] in {"covered", "partial"}}
    if missing := covered_or_partial - bound_items:
        raise ValueError(f"covered/partial itemにbounded Evidenceがありません: {sorted(missing)}")
    if not gap_ids:
        raise ValueError("Gap Ledgerが空です")

    parity = json.loads(PARITY_MATRIX.read_text(encoding="utf-8"))
    axes = parity.get("axes", [])
    axis_ids = {axis["id"] for axis in axes}
    required_axis_ids = {
        "authority-extraction", "application-reconciliation", "sync-wave-hook", "applicationset",
        "multi-source", "config-management", "rbac-sso", "secrets", "high-availability",
        "notifications", "observability", "performance-capacity", "upgrade-migration",
        "drift-refusal", "failure-recovery", "version-compatibility", "integrated-reference-system",
        "comparison", "skill-eval", "core-v2-gate",
    }
    if axis_ids != required_axis_ids:
        raise ValueError(f"FE Parity axisが不一致です: {sorted(axis_ids)}")
    for axis in axes:
        if not axis.get("required_signals"):
            raise ValueError(f"Parity axisにrequired signalがありません: {axis['id']}")
        unknown = set(axis.get("gap_ids", [])) - gap_ids
        if unknown:
            raise ValueError(f"Parity axisが未定義Gapを参照しています: {axis['id']} {sorted(unknown)}")
        unknown_evidence = set(axis.get("bounded_evidence_ids", [])) - evidence_ids
        if unknown_evidence:
            raise ValueError(f"Parity axisが未定義Evidenceを参照しています: {axis['id']} {sorted(unknown_evidence)}")
    atlas_status = next(
        line.split(":", 1)[1].strip()
        for line in (ROOT / "atlas.yaml").read_text(encoding="utf-8").splitlines()
        if line.startswith("status:")
    )
    open_parity_gaps = sum(len(axis.get("gap_ids", [])) for axis in axes)
    if (atlas_status == "complete" or parity.get("status") == "complete") and open_parity_gaps:
        raise ValueError("FE Parity Gapが残る状態でcompleteにできません")

    depth = json.loads(DEPTH_PARITY.read_text(encoding="utf-8"))
    expected_reference_commit = "4a0b2df8e2091a963bd0e0e1bbccef9c84b49a45"
    if depth.get("reference", {}).get("commit") != expected_reference_commit:
        raise ValueError("FE Depth Reference commitが固定値と一致しません")
    expected_reference_files = {
        "FE_DEPTH_REFERENCE.json",
        "docs/DEFINITIVE_GATE_V2_REFERENCE.md",
        "fixtures/definitive-gate-v2/authority-surface-inventory.fixture.json",
        "fixtures/definitive-gate-v2/evidence-granularity.fixture.json",
        "fixtures/definitive-gate-v2/profile-incompatibility.fixture.json",
        "fixtures/definitive-gate-v2/variant-comparison.fixture.json",
        "baselines/definitive-gate-v2.json",
    }
    reference_files = depth.get("reference", {}).get("files", [])
    if {item.get("path") for item in reference_files} != expected_reference_files:
        raise ValueError("FE Depth Referenceの正本/4 fixtures/baseline参照が不一致です")
    if any(not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) for item in reference_files):
        raise ValueError("FE Depth Reference file digestが不正です")
    if depth.get("reference", {}).get("frontend_summary") != {"satisfied": 1, "partial": 17, "missing": 0}:
        raise ValueError("FE自身の1/18 satisfied境界が保持されていません")
    locator_reference = depth.get("authority_locator_reference", {})
    if locator_reference.get("commit") != "841ec2fa399606a10305021a8bcd396713b8cee5":
        raise ValueError("FE copyright-safe Authority locator正本がDepth parityへ接続されていません")
    expected_authority_artifacts = {
        "artifact": "authority/extraction.snapshot.json",
        "body_inventory_artifact": "authority/body-inventory.snapshot.json",
        "baseline_artifact": "baselines/authority-body-inventory-v1.json",
        "migration_artifact": "migrations/authority-body-inventory-v1.json",
    }
    if any(locator_reference.get(key) != value for key, value in expected_authority_artifacts.items()):
        raise ValueError("Authority locator artifact参照が不正です")
    queue_reference = depth.get("authority_review_queue_reference", {})
    expected_queue_reference = {
        "repository": "frontend-behavior-atlas",
        "commit": "de2f016b8b44ea67afdb08c0552044807505984e",
        "queue_artifact": "authority/review-queue.snapshot.json",
        "decision_ledger": "authority/reviews/decisions.json",
    }
    if any(queue_reference.get(key) != value for key, value in expected_queue_reference.items()) or not queue_reference.get("rule"):
        raise ValueError("FE Authority Review Queue正本または昇格境界がDepth parityへ接続されていません")
    if depth.get("denominator_policy", {}).get("absolute_frontend_counts_are_thresholds") is not False:
        raise ValueError("FE絶対件数をArgo CD thresholdに転用できません")
    if depth.get("proof_contract", {}).get("aggregate_evidence_is_completion_proof") is not False:
        raise ValueError("Aggregate Evidenceを専用Proofの代替にできません")
    if depth.get("proof_contract", {}).get("mock_or_static_substitutes_for_real_runtime") is not False:
        raise ValueError("mock/staticを実Runtime Proofの代替にできません")

    depth_axes = depth.get("axes", [])
    expected_depth_axis_ids = {
        "authority-body-digestion", "surface-atomic-behavior-variant", "real-runtime-lab",
        "scenario-normal", "scenario-boundary", "scenario-refusal", "scenario-failure",
        "scenario-recovery", "scenario-migration", "scenario-operations", "scenario-security",
        "scenario-performance", "scenario-compatibility", "artifact-trace",
        "integrated-reference-system", "skill-eval", "rights-provenance", "non-regression-gate",
    }
    if {axis.get("id") for axis in depth_axes} != expected_depth_axis_ids or len(depth_axes) != 18:
        raise ValueError("argocd-depth-parityの18軸がFE Depth Referenceと一致しません")
    depth_status_counts: dict[str, int] = {"satisfied": 0, "partial": 0, "missing": 0}
    for axis in depth_axes:
        axis_id = axis["id"]
        status = axis.get("status")
        if status not in depth_status_counts:
            raise ValueError(f"Depth parity axis statusが不正です: {axis_id} {status}")
        depth_status_counts[status] += 1
        denominator = axis.get("argocd_denominator", {})
        if not denominator.get("expression") or not denominator.get("source"):
            raise ValueError(f"Argo CD固有denominatorがありません: {axis_id}")
        if denominator.get("closure") not in {"open", "closed"}:
            raise ValueError(f"denominator closureが不正です: {axis_id}")
        if not axis.get("proof_unit"):
            raise ValueError(f"専用Proof粒度がありません: {axis_id}")
        unknown = set(axis.get("gap_ids", [])) - gap_ids
        if unknown:
            raise ValueError(f"Depth parity axisが未定義Gapを参照しています: {axis_id} {sorted(unknown)}")
        unknown_evidence = set(axis.get("bounded_evidence_ids", [])) - evidence_ids
        if unknown_evidence:
            raise ValueError(f"Depth parity axisが未定義Evidenceを参照しています: {axis_id} {sorted(unknown_evidence)}")
        if status == "satisfied" and (axis.get("gap_ids") or denominator.get("closure") != "closed"):
            raise ValueError(f"Gapまたはopen denominatorがある軸をsatisfiedにできません: {axis_id}")
        if status != "satisfied" and not axis.get("gap_ids"):
            raise ValueError(f"未達軸にGap IDがありません: {axis_id}")
    if depth.get("summary") != depth_status_counts:
        raise ValueError(f"Depth parity summaryが実軸と一致しません: {depth_status_counts}")
    open_depth_gaps = sum(len(axis.get("gap_ids", [])) for axis in depth_axes)
    if (atlas_status == "complete" or depth.get("status") == "complete") and (
        depth_status_counts["satisfied"] != 18 or open_depth_gaps
    ):
        raise ValueError("18軸Gap 0でない状態をcompleteにできません")

    print(
        f"definitive inventory validated: items={len(inventory_items)} "
        f"areas={len(actual_areas)} gaps={len(gap_ids)} evidence_bindings={len(bound_evidence)} "
        f"parity_axes={len(axes)} parity_gap_links={open_parity_gaps} "
        f"depth_axes={len(depth_axes)} depth_satisfied={depth_status_counts['satisfied']} "
        f"depth_gap_links={open_depth_gaps}"
    )


if __name__ == "__main__":
    main()
