#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for root Surface Inventory fail-closed compilation."""

from __future__ import annotations

import copy
import json

from generate_root_surface_inventory import OUTPUT, compile_inventory, validate


def rejected(name: str, mutate) -> None:
    fixture = json.loads(OUTPUT.read_text(encoding="utf-8"))
    mutate(fixture)
    try:
        validate(fixture)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    document = json.loads(OUTPUT.read_text(encoding="utf-8"))
    validate(document)
    try:
        compile_inventory(document)
    except ValueError:
        pass
    else:
        raise AssertionError("Human Review 0でroot Inventory emitが成功しました")
    rejected("pending-denominator-concealed", lambda value: value["denominator"].update(authority_pending_human=0))
    rejected("semantic-credit-forged", lambda value: value["closure"].update(semantic_credit=1))
    rejected("human-decision-forged", lambda value: value["closure"].update(human_decisions=1))
    rejected("runtime-completion-forged", lambda value: value["closure"].update(completion_eligible_scenario_rows=1))
    rejected("root-present-forged", lambda value: value["root_inventory"].update(present=True))
    rejected("blocker-omission", lambda value: value["root_inventory"]["blockers"].pop())
    rejected("stale-input-retreat", lambda value: value["dependency_contract"]["tracked_input_paths"].remove("authority/reviews/decisions.json"))
    rejected("stale-rerun-omission", lambda value: value["dependency_contract"].update(required_rerun=""))
    print("Root Surface Inventory fixtures passed: positive=1 negative=9")


if __name__ == "__main__":
    main()
