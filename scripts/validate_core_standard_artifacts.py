#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Core標準gap Artifactと全row ID migrationをfail-closed検証する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

import generate_core_standard_artifacts as contract


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_bundle(root: Path = contract.ROOT) -> dict[Path, Any]:
    return {
        path: json.loads((root / path).read_text(encoding="utf-8"))
        for path in contract.output_paths()
    }


def validate_bundle(bundle: dict[Path, Any], root: Path = contract.ROOT) -> None:
    expected_paths = set(contract.output_paths())
    require(set(bundle) == expected_paths, "Core標準Artifact集合が欠落または増加しています")
    index = json.loads((root / contract.SCENARIO_INDEX).read_text(encoding="utf-8"))
    registry = yaml.safe_load((root / contract.RUNTIME_REGISTRY).read_text(encoding="utf-8"))
    manifest = bundle[contract.MANIFEST]
    reference = bundle[contract.REFERENCE_RESULTS]
    pattern = bundle[contract.PATTERN_RESULTS]
    migration = bundle[contract.MIGRATION]
    baseline = bundle[contract.BASELINE]
    publish = bundle[contract.PUBLISH_MANIFEST]

    require(manifest["status"] == "bounded-integration-proof", "gap-only Manifestをverified扱いしています")
    require(manifest["runtime"] == "gap-only-no-runtime-credit", "Manifestが未実行Runtime境界を失っています")
    require([item["id"] for item in manifest["scenarios"]] == list(contract.CORE_SCENARIOS), "Core 10 Scenarioが順序付きで閉じていません")
    for item in manifest["scenarios"]:
        require(len(item["patterns"]) == 100 and len(set(item["patterns"])) == 100, f"Scenario Pattern denominatorが縮小しています: {item['id']}")

    require(reference["status"] == "failed", "未実行Reference Systemをpass扱いしています")
    require(reference["counts"] == {"total": 10, "passed": 0, "failed": 0, "flaky": 0, "skipped": 10}, "Reference System gap countsが不正です")
    require([item["scenario"] for item in reference["tests"]] == list(contract.CORE_SCENARIOS), "Reference System gapの10 Scenarioが不完全です")
    for field in ("real_runtime", "fixture_runtime_credit", "integrated_evidence_runtime_credit", "historical_evidence_runtime_credit"):
        require(reference["environment"][field] is False, f"Reference System gapがruntime creditを持っています: {field}")
    require(reference["environment"]["runtime_attempts"] == 0 and reference["environment"]["retries"] == 0, "未実行Reference Systemのattempt/retryが不正です")
    for item in reference["tests"]:
        require(item["final_status"] == "skipped" and item["outcome"] == "not-run-core-standard-gap" and item["error"], f"Reference Scenarioを実行済みに偽装しています: {item['scenario']}")
        for key in ("trace", "screenshot"):
            artifact = item[key]
            relative = Path(artifact["path"])
            payload = (json.dumps(bundle[relative], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            require(artifact["digest"] == contract.sha256_bytes(payload) and artifact["bytes"] == len(payload), f"gap Artifact bindingが不正です: {relative}")
            require(bundle[relative]["runtime_executed"] is False and bundle[relative]["completion_credit"] is False, f"gap ArtifactがRuntime creditを持っています: {relative}")

    zero_counts = {"rows": 0, "variants": 0, "total": 0, "passed": 0, "failed": 0, "flaky": 0, "skipped": 0}
    require(pattern["status"] == "failed" and pattern["counts"] == zero_counts and pattern["tests"] == [], "未実行Pattern Scenario reportを成功世代として公開しています")
    require(pattern["profile"] == "gap-only-no-runtime" and pattern["environment"]["real_runtime"] is False, "Pattern Scenario gapが実Runtime profileを名乗っています")
    require(pattern["environment"]["dedicated_runtime_reports_preserved"] == len(registry["reports"]) == 13, "既存13 Runtime reportの保持境界が不正です")
    for field in ("fixture_runtime_credit", "integrated_evidence_runtime_credit", "historical_evidence_runtime_credit"):
        require(pattern["environment"][field] is False, f"非Runtime EvidenceがPattern creditを持っています: {field}")

    rows = migration["rows"]
    require(len(rows) == len(index["files"]) == 1000, "旧→新row ID mappingが全件ではありません")
    old_ids = [item["old_row_id"] for item in rows]
    new_ids = [item["new_row_id"] for item in rows]
    require(old_ids == [item["id"] for item in index["files"]] and len(set(old_ids)) == 1000, "旧row ID集合または順序が非後退baselineと不一致です")
    require(len(set(new_ids)) == 1000, "Core row ID mappingが重複しています")
    renamed = 0
    for source, item in zip(index["files"], rows):
        core = contract.CORE_BY_LEGACY[source["scenario"]]
        expected_id = source["id"].rsplit(".", 1)[0] + "." + core
        expected_path = source["path"].rsplit("/", 1)[0] + "/" + core + ".proof.json"
        require(item["new_row_id"] == expected_id and item["new_path"] == expected_path and item["core_scenario"] == core, f"row ID migrationが不正です: {source['id']}")
        require(item["runtime_credit"] is False and item["completion_eligible"] is False and item["status"] == "mapped-gap-not-promoted", f"mappingだけでRuntime/Completion creditを付与しています: {source['id']}")
        if source["scenario"] == "rejection":
            renamed += 1
            require(item["mapping_kind"] == "renamed" and ".rejection" not in item["new_row_id"] and "/rejection." not in item["new_path"], f"legacy rejectionがCore rowへ漏れています: {source['id']}")
        else:
            require(item["mapping_kind"] == "identity" and item["old_row_id"] == item["new_row_id"], f"非rejection rowを不要に置換しています: {source['id']}")
    require(renamed == 100 and migration["counts"] == {"old_rows": 1000, "new_rows": 1000, "identity": 900, "renamed_rejection_to_refusal": 100, "runtime_credit": 0, "completion_eligible": 0}, "Scenario migration集計が不正です")
    require([item["core"] for item in migration["scenario_mapping"]] == list(contract.CORE_SCENARIOS), "Core Scenario mappingが10 class identityを満たしません")

    require(baseline["source_commit"] == contract.BASELINE_COMMIT and baseline["old_row_count"] == baseline["new_row_count"] == 1000, "Scenario migration baseline identity/countが不正です")
    require(baseline["old_order_digest"] == contract.id_digest(old_ids) and baseline["old_set_digest"] == contract.id_digest(sorted(old_ids)), "旧row ID baselineが縮小または並替えされています")
    require(baseline["new_order_digest"] == contract.id_digest(new_ids) and baseline["new_set_digest"] == contract.id_digest(sorted(new_ids)), "新row ID baselineが縮小または重複しています")
    require(baseline["renamed_row_count"] == 100 and baseline["identity_row_count"] == 900, "Scenario migration baseline構造が不正です")

    listed = {Path(item["path"]): item for item in publish["files"]}
    expected_listed = expected_paths - {contract.PUBLISH_MANIFEST}
    require(set(listed) == expected_listed and publish["runtime_credit"] is False, "atomic publish manifestのfile集合またはRuntime境界が不正です")
    for relative in expected_listed:
        payload = (json.dumps(bundle[relative], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        require(listed[relative]["digest"] == contract.sha256_bytes(payload) and listed[relative]["bytes"] == len(payload), f"atomic publish bindingが不正です: {relative}")


def validate_current(root: Path = contract.ROOT) -> None:
    bundle = load_bundle(root)
    validate_bundle(bundle, root)
    expected = contract.build_documents()
    for relative, payload in expected.items():
        require((root / relative).read_bytes() == payload, f"Core標準Artifactが現在input/generatorと一致しません: {relative}")
    require(not contract.STAGING.exists() and not contract.BACKUP.exists(), "Core標準Artifact staging/backup残骸があります")


def main() -> None:
    validate_current()
    print("Core standard gap artifacts validated: scenarios=10 mappings=1000 runtime_credit=0")


if __name__ == "__main__":
    main()
