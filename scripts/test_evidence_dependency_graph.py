#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Argo CD Evidence Dependency Graphの変更・漏れ・退避・構造縮小を拒否する。"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

import evidence_dependency_graph as contract


def require_rejected(name: str, graph: dict, root: Path = contract.ROOT, contains: str | None = None) -> None:
    try:
        contract.validate_graph(root, graph)
    except contract.DependencyContractError as error:
        if contains and contains not in str(error):
            raise AssertionError(f"{name}は異なる理由で失敗しました: {error}") from error
        return
    raise AssertionError(f"negative fixtureを受理しました: {name}")


def materialize(root: Path, graph: dict) -> None:
    paths = {"evidence/dependency-graph.json", "evidence/scenarios/index.json", "evidence/scenarios/closure-plan.json"}
    paths |= {member for item in graph["inputs"] for member in item["members"]}
    paths |= {item["path"] for item in graph["outputs"]}
    for relative in sorted(paths):
        source, target = contract.ROOT / relative, root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, target)


def replace_json(path: Path, value: dict) -> None:
    path.unlink()
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_output_digest(graph: dict, relative: str, root: Path) -> None:
    for output in graph["outputs"]:
        if output["path"] == relative:
            output["digest"] = contract.sha256_file(root / relative)
            return
    raise AssertionError(f"outputがありません: {relative}")


def refresh_fixture_input_bindings(graph: dict, relative: str, root: Path) -> None:
    for item in graph["inputs"]:
        if relative not in item["members"]:
            continue
        value = contract.aggregate_member_digest(root, item["members"])
        item["baseline_digest"] = value
        item["current_digest"] = value
        for run in graph["runs"]:
            for binding in run["input_bindings"]:
                if binding["input_id"] == item["id"]:
                    binding["digest"] = value


def main() -> None:
    graph = contract.load(contract.GRAPH)
    contract.validate_graph(contract.ROOT, graph)

    digest_only = copy.deepcopy(graph)
    digest_only["inputs"][0]["baseline_digest"] = "sha256:" + "0" * 64
    digest_only["inputs"][0]["observed_at"] = "2026-08-29T00:00:00Z"
    require_rejected("input-change-digest-only", digest_only, contains="digest-only closure")

    missing_rerun = copy.deepcopy(graph)
    scenario_output = next(item for item in missing_rerun["outputs"] if item["kind"] == "scenario-proof")
    run = next(item for item in missing_rerun["runs"] if item["id"] == scenario_output["run_id"])
    run["output_ids"].remove(scenario_output["id"])
    require_rejected("missing-rerun-output", missing_rerun, contains="first-attempt full-run")

    stale = copy.deepcopy(graph)
    stale["outputs"][0]["status"] = "stale"
    require_rejected("stale-output", stale, contains="stale")

    retreated = copy.deepcopy(graph)
    raw = next(item for item in retreated["outputs"] if item["path"].startswith("evidence/raw/"))
    retreated["outputs"] = [item for item in retreated["outputs"] if item["id"] != raw["id"]]
    retreated["required_outputs"].remove(raw["path"])
    for run in retreated["runs"]:
        if raw["id"] in run["output_ids"]:
            run["output_ids"].remove(raw["id"])
    require_rejected("output-retreat", retreated, contains="退避")

    with tempfile.TemporaryDirectory() as directory:
        fixture_root = Path(directory)
        materialize(fixture_root, graph)

        proof_shrink = copy.deepcopy(graph)
        index_path = fixture_root / "evidence/scenarios/index.json"
        index = contract.load(index_path)
        index["files"] = index["files"][1:]
        replace_json(index_path, index)
        update_output_digest(proof_shrink, "evidence/scenarios/index.json", fixture_root)
        refresh_fixture_input_bindings(proof_shrink, "evidence/scenarios/index.json", fixture_root)
        require_rejected("proof-structure-shrink", proof_shrink, fixture_root, "scenario-proof-index")

        original_index = contract.load(contract.INDEX)
        replace_json(index_path, original_index)
        plan_shrink = copy.deepcopy(graph)
        plan_path = fixture_root / "evidence/scenarios/closure-plan.json"
        plan = contract.load(plan_path)
        plan["rows"] = plan["rows"][:-1]
        replace_json(plan_path, plan)
        update_output_digest(plan_shrink, "evidence/scenarios/closure-plan.json", fixture_root)
        require_rejected("closure-plan-structure-shrink", plan_shrink, fixture_root, "scenario-closure-plan")

        replace_json(plan_path, contract.load(contract.ROOT / "evidence/scenarios/closure-plan.json"))
        completion_ambiguity = copy.deepcopy(graph)
        plan = contract.load(plan_path)
        plan["summary"]["completion_remaining_rows"] = 987
        plan["summary"]["completion_closed_rows"] = 13
        replace_json(plan_path, plan)
        update_output_digest(completion_ambiguity, "evidence/scenarios/closure-plan.json", fixture_root)
        require_rejected("closure-plan-completion-ambiguity", completion_ambiguity, fixture_root, "completion")

    print("Evidence Dependency negative fixtures passed: positive=1 negative=7")


if __name__ == "__main__":
    main()
