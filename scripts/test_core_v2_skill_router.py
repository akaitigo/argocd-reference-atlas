#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for the Core v2 Skill Router projection."""

from __future__ import annotations

import copy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_core_v2_skill_router import BOUNDARIES, build  # noqa: E402


def validate(document: dict) -> None:
    matrix = document["matrix"]
    identities = {(item["outcome"], item["surface"]) for item in matrix}
    if len(matrix) != 112 or len(identities) != 112:
        raise ValueError("8 Outcome×14 Surface denominator changed")
    if {item["id"] for item in document["boundary_cases"]} != BOUNDARIES:
        raise ValueError("fail-closed boundary set changed")
    if any(not item.get("implementation_bindings") or not item.get("source_bindings") or not item.get("evidence_bindings") for item in matrix):
        raise ValueError("cell lost implementation/source/evidence binding")
    if document["summary"]["mastery_routing_gaps"] != sum(item.get("support_status") != "routed" for item in matrix):
        raise ValueError("routing gap summary mismatch")
    if document["status"] == "subject-skill-ready":
        raise ValueError("incomplete router promoted to complete")


def rejected(name: str, mutate) -> None:
    fixture = copy.deepcopy(build())
    mutate(fixture)
    try:
        validate(fixture)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    validate(build())
    rejected("matrix-shrink", lambda value: value["matrix"].pop())
    rejected("boundary-removal", lambda value: value["boundary_cases"].pop())
    rejected("evidence-unbound", lambda value: value["matrix"][0].update(evidence_bindings=[]))
    rejected("routing-gap-hidden", lambda value: value["summary"].update(mastery_routing_gaps=0))
    rejected("false-complete", lambda value: value.update(status="subject-skill-ready"))
    print("Core v2 Skill Router fixtures passed: positive=1 negative=5")


if __name__ == "__main__":
    main()
