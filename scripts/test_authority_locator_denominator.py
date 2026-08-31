#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for the Authority inventory candidate denominator."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_authority_locators import audit_inventory_denominator, expected_inventory_bindings  # noqa: E402


def inputs() -> tuple[list[dict], dict[str, dict]]:
    lock = yaml.safe_load((ROOT / "sources.lock.yaml").read_text(encoding="utf-8"))
    coverage = yaml.safe_load((ROOT / "coverage.yaml").read_text(encoding="utf-8"))
    claim_index = yaml.safe_load((ROOT / "atlas/claims/index.yaml").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in lock["sources"]}
    targets = {item["id"]: item for item in coverage["targets"]}
    claims = {item["id"]: item for item in claim_index["claims"]}
    candidates = []
    for path in sorted((ROOT / "authority/surfaces-draft").glob("*.json")):
        candidates.extend(json.loads(path.read_text(encoding="utf-8"))["candidate_surfaces"])
    return candidates, expected_inventory_bindings(sources, targets, claims)


def rejected(name: str, mutate) -> None:
    candidates, expected = inputs()
    mutate(candidates, expected)
    try:
        audit_inventory_denominator(candidates, expected)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    candidates, expected = inputs()
    classified, unclassified = audit_inventory_denominator(candidates, expected)
    if unclassified != 15:
        raise AssertionError(f"unclassified denominator changed: {unclassified}")
    rejected("candidate-omission", lambda values, expected: values.remove(next(item for item in values if item["edge_id"] in expected)))
    rejected("candidate-duplicate", lambda values, expected: values.append(copy.deepcopy(next(item for item in values if item["edge_id"] in expected))))
    rejected("target-rebound", lambda values, expected: next(item for item in values if item["edge_id"] in expected).update(target_id="target.rebound"))
    rejected("claim-gap-hidden", lambda values, expected: next(item for item in values if item["claim_id"].startswith("unclassified.claim.")).update(claim_id="claim.hidden"))
    rejected("capability-gap-hidden", lambda values, expected: next(item for item in values if item["capability_id"].startswith("unclassified.capability.")).update(capability_id="capability.hidden"))
    print(f"Authority locator denominator fixtures passed: classified={classified} unclassified={unclassified} positive=1 negative=5")


if __name__ == "__main__":
    main()
