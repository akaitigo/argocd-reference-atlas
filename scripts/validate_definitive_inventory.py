#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Domain-native Definitive InventoryのID、Coverage、Evidence接続を検査する。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "definitive" / "surface-inventory.yaml"
GAP_LEDGER = ROOT / "definitive" / "gap-ledger.yaml"


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
        "migration", "compatibility", "performance",
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

    print(
        f"definitive inventory validated: items={len(inventory_items)} "
        f"areas={len(actual_areas)} gaps={len(gap_ids)} evidence_bindings={len(bound_evidence)}"
    )


if __name__ == "__main__":
    main()
