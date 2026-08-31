#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""security-004専用Runtime trancheのstatic preflight contractを検証する。"""

from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "scenarios"))
import run_security_004  # noqa: E402


CLOSURE_PLAN = ROOT / "evidence/scenarios/closure-plan.json"
VARIANT_CONTRACT = ROOT / "definitive/scenario-variant-contract.yaml"
RUNNER = ROOT / "scripts/scenarios/run_security_004.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON objectではありません: {path}")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"YAML objectではありません: {path}")
    return value


def variant_overrides() -> dict[str, list[str]]:
    contract = load_yaml(VARIANT_CONTRACT)
    overrides = {}
    for item in contract["denominator"]["surface_overrides"]:
        overrides[item["surface_id"]] = [variant["id"] for variant in item["variants"]]
    return overrides


def tranche_rows() -> dict[str, Any]:
    plan = load_json(CLOSURE_PLAN)
    tranches = {item["id"]: item for item in plan["tranches"]}
    require("security-004" in tranches, "closure planにsecurity-004 trancheがありません")
    tranche = tranches["security-004"]
    require(tranche["scenario"] == "security", "security-004 trancheのscenarioが不正です")
    return tranche


def publish_contract() -> dict[str, bool]:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    state = {
        "publish_evidence_tree": False,
        "full_run_passed_true": False,
        "write_publish_manifest": False,
        "validate_publish_manifest": False,
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        if name == "publish_evidence_tree":
            state["publish_evidence_tree"] = True
            for keyword in node.keywords:
                if keyword.arg == "full_run_passed" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    state["full_run_passed_true"] = True
        elif name == "write_publish_manifest":
            state["write_publish_manifest"] = True
        elif name == "validate_publish_manifest":
            state["validate_publish_manifest"] = True
    return state


def current_state() -> dict[str, Any]:
    closure = tranche_rows()
    row_ids = closure["row_ids"]
    expected_row_ids = sorted(f"closure.{item['surface_id']}.security" for item in run_security_004.REPORT_VARIANTS.values())
    actual_row_ids = sorted(row_ids)
    report_variants = copy.deepcopy(run_security_004.REPORT_VARIANTS)
    return {
        "report_ids": sorted(report_variants),
        "surface_ids": sorted(item["surface_id"] for item in report_variants.values()),
        "variants_by_surface": {item["surface_id"]: list(item["variants"]) for item in report_variants.values()},
        "expected_row_ids": expected_row_ids,
        "actual_row_ids": actual_row_ids,
        "artifact_kinds": copy.deepcopy(run_security_004.ARTIFACT_KINDS),
        "publish_contract": publish_contract(),
    }


def validate(document: dict[str, Any]) -> None:
    require(document["report_ids"] == sorted(run_security_004.REPORT_VARIANTS), "report ID集合が不正です")
    surface_ids = document["surface_ids"]
    require(len(surface_ids) == 4 and len(set(surface_ids)) == 4, "security-004 surface集合が不正です")
    require(document["actual_row_ids"] == document["expected_row_ids"], "closure plan security-004 row集合がrunnerと一致しません")
    require(set(document["artifact_kinds"]) == {"resource_state", "controller_log", "metric", "trace"}, "artifact channel集合が不正です")
    overrides = variant_overrides()
    total_variants = 0
    for surface_id in surface_ids:
        require(surface_id in overrides, f"variant contract overrideがありません: {surface_id}")
        expected = overrides[surface_id]
        actual = document["variants_by_surface"][surface_id]
        require(actual == expected, f"variant contractとrunnerが一致しません: {surface_id}")
        require(len(actual) == 2 and len(set(actual)) == 2, f"variant集合が不正です: {surface_id}")
        total_variants += len(actual)
    require(total_variants == 8, "security-004 total variant数が不正です")
    publish = document["publish_contract"]
    require(publish["publish_evidence_tree"], "atomic publish callがありません")
    require(publish["full_run_passed_true"], "full_run_passed=Trueでpublishしていません")
    require(publish["write_publish_manifest"], "atomic publish manifestを書いていません")
    require(publish["validate_publish_manifest"], "atomic publish manifestを検証していません")


def rejected(name: str, mutate) -> None:
    value = current_state()
    mutate(value)
    try:
        validate(value)
    except AssertionError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    validate(current_state())
    rejected("missing-security-row", lambda value: value["actual_row_ids"].pop())
    rejected("duplicate-surface", lambda value: value["surface_ids"].append(value["surface_ids"][0]))
    rejected("variant-mismatch", lambda value: value["variants_by_surface"].__setitem__("applicationset.generator.cluster", ["approved-cluster-selected", "restricted-cluster-excluded"]))
    rejected("artifact-channel-retreat", lambda value: value["artifact_kinds"].pop("trace"))
    rejected("publish-without-full-run", lambda value: value["publish_contract"].__setitem__("full_run_passed_true", False))
    rejected("publish-manifest-omitted", lambda value: value["publish_contract"].__setitem__("write_publish_manifest", False))
    rejected("validate-manifest-omitted", lambda value: value["publish_contract"].__setitem__("validate_publish_manifest", False))
    print("security-004 preflight fixtures passed: positive=1 negative=7")


if __name__ == "__main__":
    main()
