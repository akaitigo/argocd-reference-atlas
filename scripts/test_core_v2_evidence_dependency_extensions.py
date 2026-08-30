#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for the additive Core v2 dependency graph nodes."""

from __future__ import annotations

import copy

import evidence_dependency_graph as contract
from generate_core_v2_dependency_extension import GRAPH, validate_extension


def rejected(name: str, mutate) -> None:
    fixture = copy.deepcopy(contract.load(GRAPH))
    mutate(fixture)
    try:
        validate_extension(fixture)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def output(document: dict, path: str) -> dict:
    return next(item for item in document["outputs"] if item["path"] == path)


def main() -> None:
    document = contract.load(GRAPH)
    validate_extension(document)
    rejected("input-retreat", lambda value: value["inputs"].pop(next(index for index, item in enumerate(value["inputs"]) if item["id"] == "harness.core-v2-skill-router")))
    rejected("output-retreat", lambda value: value["outputs"].remove(output(value, "evals/definitive-skill-router.json")))
    rejected("skill-harness-unbound", lambda value: output(value, "evals/definitive-skill-router.json")["depends_on"].remove("harness.core-v2-skill-router"))
    rejected("scenario-harness-unbound", lambda value: output(value, "artifacts/core-v2/scenario-plan-gap.json")["depends_on"].remove("harness.core-v2-scenario-plan"))
    rejected("first-attempt-weakened", lambda value: next(item for item in value["runs"] if item["id"] == "run.core-v2-skill-router").update(attempts=2))
    rejected("authority-input-retreat", lambda value: value["inputs"].pop(next(index for index, item in enumerate(value["inputs"]) if item["id"] == "harness.authority-denominator")))
    rejected("authority-output-retreat", lambda value: value["outputs"].remove(output(value, "authority/extraction.snapshot.json")))
    rejected("authority-source-unbound", lambda value: output(value, "authority/extraction.snapshot.json")["depends_on"].remove("source.authority-lock-inventory"))
    rejected("authority-first-attempt-weakened", lambda value: next(item for item in value["runs"] if item["id"] == "run.authority-denominator").update(attempts=2))
    rejected("repository-contract-unbound", lambda value: output(value, "artifacts/core-v2/evidence-dependency-extension.json")["depends_on"].remove("source.repository-contract"))
    rejected("content-policy-unbound", lambda value: output(value, "artifacts/core-v2/evidence-dependency-extension.json")["depends_on"].remove("harness.content-policy"))
    print("Core v2 Evidence Dependency extension fixtures passed: positive=1 negative=11")


if __name__ == "__main__":
    main()
