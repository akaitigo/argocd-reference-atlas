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
    rejected("surface-readiness-output-retreat", lambda value: value["outputs"].remove(output(value, "artifacts/core-v2/surface-inventory-readiness.json")))
    rejected("surface-readiness-harness-unbound", lambda value: output(value, "artifacts/core-v2/surface-inventory-readiness.json")["depends_on"].remove("harness.surface-inventory-readiness"))
    rejected("root-inventory-output-retreat", lambda value: value["outputs"].remove(output(value, "artifacts/core-v2/root-surface-inventory-closure.json")))
    rejected("root-inventory-harness-unbound", lambda value: output(value, "artifacts/core-v2/root-surface-inventory-closure.json")["depends_on"].remove("harness.root-surface-inventory"))
    rejected("root-matrix-output-retreat", lambda value: value["outputs"].remove(output(value, "artifacts/core-v2/root-verification-matrix-closure.json")))
    rejected("root-matrix-harness-unbound", lambda value: output(value, "artifacts/core-v2/root-verification-matrix-closure.json")["depends_on"].remove("harness.root-verification-matrix"))
    rejected("root-contract-gap-output-retreat", lambda value: value["outputs"].remove(output(value, "artifacts/core-v2/root-contract-adapter-gap.json")))
    rejected("root-contract-gap-harness-unbound", lambda value: output(value, "artifacts/core-v2/root-contract-adapter-gap.json")["depends_on"].remove("harness.core-v2-root-contract-gap"))
    rejected("root-contract-gap-matrix-unbound", lambda value: output(value, "artifacts/core-v2/root-contract-adapter-gap.json")["depends_on"].remove(output(value, "artifacts/core-v2/root-verification-matrix-closure.json")["id"]))
    rejected("scenario-root-gap-unbound", lambda value: output(value, "artifacts/core-v2/scenario-plan-gap.json")["depends_on"].remove(output(value, "artifacts/core-v2/root-contract-adapter-gap.json")["id"]))
    rejected("scenario-schema-input-retreat", lambda value: value["inputs"].pop(next(index for index, item in enumerate(value["inputs"]) if item["id"] == "harness.core-v2-scenario-schema-gap")))
    rejected("scenario-schema-output-retreat", lambda value: value["outputs"].remove(output(value, "artifacts/core-v2/scenario-proof-index-schema-gap.json")))
    rejected("scenario-schema-harness-unbound", lambda value: output(value, "artifacts/core-v2/scenario-proof-index-schema-gap.json")["depends_on"].remove("harness.core-v2-scenario-schema-gap"))
    rejected("scenario-schema-migration-unbound", lambda value: output(value, "artifacts/core-v2/scenario-proof-index-schema-gap.json")["depends_on"].remove(output(value, "migrations/scenario-class-refusal-v1.json")["id"]))
    rejected("root-scenario-schema-unbound", lambda value: output(value, "artifacts/core-v2/root-contract-adapter-gap.json")["depends_on"].remove(output(value, "artifacts/core-v2/scenario-proof-index-schema-gap.json")["id"]))
    rejected("first-attempt-weakened", lambda value: next(item for item in value["runs"] if item["id"] == "run.core-v2-skill-router").update(attempts=2))
    rejected("authority-input-retreat", lambda value: value["inputs"].pop(next(index for index, item in enumerate(value["inputs"]) if item["id"] == "harness.authority-denominator")))
    rejected("authority-output-retreat", lambda value: value["outputs"].remove(output(value, "authority/extraction.snapshot.json")))
    rejected("authority-source-unbound", lambda value: output(value, "authority/extraction.snapshot.json")["depends_on"].remove("source.authority-lock-inventory"))
    rejected("authority-first-attempt-weakened", lambda value: next(item for item in value["runs"] if item["id"] == "run.authority-denominator").update(attempts=2))
    rejected("authority-decisions-input-retreat", lambda value: value["inputs"].pop(next(index for index, item in enumerate(value["inputs"]) if item["id"] == "source.authority-human-decisions")))
    rejected("authority-body-output-retreat", lambda value: value["outputs"].remove(output(value, "authority/body-inventory.snapshot.json")))
    rejected("authority-review-output-retreat", lambda value: value["outputs"].remove(output(value, "authority/review-queue.snapshot.json")))
    rejected("root-inventory-body-unbound", lambda value: output(value, "artifacts/core-v2/root-surface-inventory-closure.json")["depends_on"].remove(output(value, "authority/body-inventory.snapshot.json")["id"]))
    rejected("root-inventory-review-unbound", lambda value: output(value, "artifacts/core-v2/root-surface-inventory-closure.json")["depends_on"].remove(output(value, "authority/review-queue.snapshot.json")["id"]))
    rejected("root-inventory-decisions-unbound", lambda value: output(value, "artifacts/core-v2/root-surface-inventory-closure.json")["depends_on"].remove("source.authority-human-decisions"))
    rejected("root-matrix-decisions-unbound", lambda value: output(value, "artifacts/core-v2/root-verification-matrix-closure.json")["depends_on"].remove("source.authority-human-decisions"))
    rejected("repository-contract-unbound", lambda value: output(value, "artifacts/core-v2/evidence-dependency-extension.json")["depends_on"].remove("source.repository-contract"))
    rejected("content-policy-unbound", lambda value: output(value, "artifacts/core-v2/evidence-dependency-extension.json")["depends_on"].remove("harness.content-policy"))
    rejected("core-standard-input-retreat", lambda value: value["inputs"].pop(next(index for index, item in enumerate(value["inputs"]) if item["id"] == "harness.core-standard-artifacts")))
    rejected("core-standard-output-retreat", lambda value: value["outputs"].remove(output(value, "artifacts/pattern-scenarios/results.json")))
    rejected("core-standard-harness-unbound", lambda value: output(value, "migrations/scenario-class-refusal-v1.json")["depends_on"].remove("harness.core-standard-artifacts"))
    rejected("core-standard-first-attempt-weakened", lambda value: next(item for item in value["runs"] if item["id"] == "run.core-standard-artifacts").update(attempts=2))
    print("Core v2 Evidence Dependency extension fixtures passed: positive=1 negative=37")


if __name__ == "__main__":
    main()
