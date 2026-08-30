#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for the fail-closed Surface Inventory readiness bridge."""

from __future__ import annotations

import copy
import json

from generate_surface_inventory_readiness import OUTPUT, validate


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
    rejected("candidate-edge-omission", lambda value: value["candidate_mappings"].pop())
    rejected("artifact-digest-substitution", lambda value: value["candidate_artifacts"][0].update(digest="sha256:" + "0" * 64))
    rejected("unreviewed-final-promotion", lambda value: value["candidate_mappings"][0].update(final_surface_promoted=True))
    rejected("unreviewed-completion-credit", lambda value: value["summary"].update(completion_credit=1))
    rejected("unreviewed-root-emission", lambda value: value["root_inventory_gate"].update(emission_allowed=True))
    rejected("claim-gap-concealment", lambda value: value["summary"].update(candidate_claim_binding_gaps=0))
    print("Surface Inventory readiness fixtures passed: positive=1 negative=6")


if __name__ == "__main__":
    main()
