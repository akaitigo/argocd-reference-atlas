#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Core v2 Scenario Proof Schema adapterをstaging検証し、gap reportだけを公開する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT.parent / "reference-atlas-core"
STAGING = ROOT / ".runtime/core-scenario-proof-index-next"
CANDIDATE = ROOT / ".runtime/core-scenario-proof-index-next.staging"
ROLLBACK = ROOT / ".runtime/core-scenario-proof-index-next.rollback"
ATLAS_CORE_BINARY = ROOT / ".cache/atlas-core"
OUTPUT = ROOT / "artifacts/core-v2/scenario-proof-index-schema-gap.json"
LEGACY_INDEX = Path("evidence/scenarios/index.json")
MIGRATION = Path("migrations/scenario-class-refusal-v1.json")
MIGRATION_BASELINE = Path("baselines/scenario-row-id-migration-v1.json")
CORE_MANIFEST = Path("integrations/reference-system/manifest.json")
REFERENCE_RESULTS = Path("artifacts/reference-system/results.json")
PATTERN_RESULTS = Path("artifacts/pattern-scenarios/results.json")
VARIANT_CONTRACT = Path("definitive/scenario-variant-contract.yaml")
GENERATOR = Path("scripts/generate_core_v2_scenario_schema_gap.py")
INDEX_SCHEMA = CORE_ROOT / "schemas/scenario-proof-index.schema.json"
ROW_SCHEMA = CORE_ROOT / "schemas/scenario-proof-row.schema.json"
CORE_COMMIT = "072d7ca77981f51754e824d70c6d4ecd55ea67e5"
GENERATED_AT = "2026-08-31T00:00:00Z"
LEGACY_TO_CORE = {
    "normal": "normal", "boundary": "boundary", "rejection": "refusal",
    "failure": "failure", "recovery": "recovery", "migration": "migration",
    "operations": "operations", "security": "security",
    "performance": "performance", "compatibility": "compatibility",
}
CORE_SCENARIOS = tuple(LEGACY_TO_CORE.values())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load(path: Path, root: Path = ROOT) -> dict[str, Any]:
    value = json.loads((root / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path}")
    return value


def aggregate(documents: dict[Path, bytes]) -> str:
    value = hashlib.sha256()
    for path in sorted(documents, key=lambda item: item.as_posix()):
        value.update(path.as_posix().encode("utf-8"))
        value.update(b"\0")
        value.update(documents[path])
        value.update(b"\0")
    return "sha256:" + value.hexdigest()


def id_digest(values: list[str]) -> str:
    return sha256_bytes(("\n".join(values) + "\n").encode("utf-8"))


def staged_row_path(pattern_id: str, scenario: str) -> Path:
    return Path(f"evidence/scenarios/core-v2-gap/behaviors/{pattern_id}/{scenario}.proof.json")


def build_documents() -> dict[Path, bytes]:
    legacy = load(LEGACY_INDEX)
    migration = load(MIGRATION)
    manifest = load(CORE_MANIFEST)
    reference = load(REFERENCE_RESULTS)
    migration_rows = {item["old_row_id"]: item for item in migration["rows"]}
    manifest_by_scenario = {item["id"]: item for item in manifest["scenarios"]}
    reference_by_scenario = {item["scenario"]: item for item in reference["tests"]}
    generator_digest = sha256_file(ROOT / GENERATOR)
    variant_digest = sha256_file(ROOT / VARIANT_CONTRACT)
    documents: dict[Path, bytes] = {}
    files: list[dict[str, Any]] = []
    by_scenario = {
        scenario: {"rows": 0, "pattern_specific": 0, "runtime_identity": 0, "integrated_pattern_mapped": 0, "gaps": 0}
        for scenario in CORE_SCENARIOS
    }
    for record in legacy["files"]:
        old_path = Path(record["path"])
        old_row = load(old_path)
        mapped = migration_rows[record["id"]]
        scenario = LEGACY_TO_CORE[record["scenario"]]
        path = staged_row_path(record["pattern_id"], scenario)
        integrated = manifest_by_scenario[scenario]
        result = reference_by_scenario[scenario]
        row = {
            "schema_version": 1,
            "id": mapped["new_row_id"],
            "atlas_id": "argocd-reference-atlas",
            "generated_at": GENERATED_AT,
            "behavior_scope": "current-domain-pattern-not-authority-atomic",
            "pattern_id": record["pattern_id"],
            "behavior_id": record["behavior_id"],
            "target_id": old_row["target_id"],
            "target_set": old_row["target_set"],
            "scenario": scenario,
            "applicability": "required",
            "status": "pattern-specific-gap",
            "classification": {
                "method": "legacy-scenario-class-gap-adapter",
                "matcher_digest": sha256_file(ROOT / MIGRATION),
                "state_ids": [record["scenario"], scenario],
                "semantic_scope_match": False,
            },
            "source_bindings": [{
                "variant_id": "pending-authority-human-review",
                "path": VARIANT_CONTRACT.as_posix(),
                "digest": variant_digest,
            }],
            "pattern_evidence": {
                "capture_environment_identity": None,
                "capture_harness_digest": generator_digest,
                "capture_records": [],
                "benchmark_environment": None,
                "benchmark_records": [],
                "compatibility_environment": None,
                "compatibility_records": [],
            },
            "integrated_reference": {
                "manifest": CORE_MANIFEST.as_posix(),
                "result": REFERENCE_RESULTS.as_posix(),
                "pattern_mapped": record["pattern_id"] in integrated["patterns"],
                "runtime_boundaries": integrated["runtime_boundaries"],
                "assertions": integrated["assertions"],
                "outcome": result["outcome"],
                "attempts": result["attempts"],
                "trace": result["trace"],
                "screenshot": result["screenshot"],
            },
            "closure": {
                "dedicated_row": True,
                "dedicated_artifact": True,
                "pattern_specific_evidence": False,
                "real_runtime_identity": False,
                "integrated_runtime_trace": False,
                "authority_atomic_behavior": False,
                "completion_eligible": False,
            },
            "gaps": [
                "Authority Human Review済みAtomic behaviorではない。",
                "全Variantを専用Argo CD/Kubernetes Runtimeで実行していない。",
                "Reference traceは明示gapでありBehavior固有Runtime traceではない。",
                "Schema adapterはRuntime、Semantic、Completion creditを持たない。",
            ],
        }
        payload = json_bytes(row)
        documents[path] = payload
        files.append({
            "id": row["id"], "pattern_id": row["pattern_id"], "behavior_id": row["behavior_id"],
            "scenario": scenario, "path": path.as_posix(), "digest": sha256_bytes(payload),
            "status": "pattern-specific-gap",
        })
        counts = by_scenario[scenario]
        counts["rows"] += 1
        counts["integrated_pattern_mapped"] += int(row["integrated_reference"]["pattern_mapped"])
        counts["gaps"] += 1
    source_paths = [LEGACY_INDEX, MIGRATION, MIGRATION_BASELINE, CORE_MANIFEST, REFERENCE_RESULTS, PATTERN_RESULTS, VARIANT_CONTRACT, GENERATOR]
    index = {
        "schema_version": 1,
        "id": "argocd-scenario-proof-core-v2-schema-gap-v1",
        "atlas_id": "argocd-reference-atlas",
        "generated_at": GENERATED_AT,
        "status": "incomplete-authority-atomic-and-runtime-closure",
        "denominator": "100-current-domain-patterns-x-10-core-scenarios",
        "tool_digest": generator_digest,
        "source_digests": {path.as_posix(): sha256_file(ROOT / path) for path in source_paths},
        "summary": {
            "patterns": 100, "scenarios": 10, "rows": 1000,
            "dedicated_artifacts": 1000, "pattern_specific_rows": 0,
            "pattern_specific_runtime_rows": 0, "pattern_specific_capture_rows": 0,
            "pattern_specific_gaps": 1000, "integrated_trace_rows": 0,
            "authority_atomic_rows": 0, "completion_eligible_rows": 0,
        },
        "by_scenario": by_scenario,
        "files": files,
        "completion_limits": [
            "Schema適合は実Argo CD/Kubernetes Runtime、Authority Human Review、Completionの代替ではない。",
            "canonical evidence/scenarios/index.jsonは全row移行と実Runtime再実行が閉じるまで置換しない。",
        ],
    }
    documents[Path("evidence/scenarios/index.json")] = json_bytes(index)
    return documents


def receipt_path(staging: Path) -> Path:
    return staging / ".core-schema-validation.json"


def validation_log_path(staging: Path) -> Path:
    return staging / ".atlas-validate.log"


def remove_staging(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def write_staging(
    documents: dict[Path, bytes], staging: Path = CANDIDATE, *, inject_failure: bool = False,
) -> None:
    remove_staging(staging)
    try:
        for index, (path, payload) in enumerate(documents.items()):
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            if inject_failure and index == 10:
                raise RuntimeError("injected staging generation failure")
        validate_staging(documents, staging)
    except Exception:
        remove_staging(staging)
        raise


def validate_staging(documents: dict[Path, bytes], staging: Path = STAGING) -> None:
    expected = set(documents)
    actual = {
        path.relative_to(staging)
        for path in staging.rglob("*.json")
        if path.name != ".core-schema-validation.json"
    }
    require(actual == expected, "Scenario Schema staging output集合が不一致です")
    index = load(Path("evidence/scenarios/index.json"), staging)
    require(index["summary"] == {"patterns": 100, "scenarios": 10, "rows": 1000, "dedicated_artifacts": 1000, "pattern_specific_rows": 0, "pattern_specific_runtime_rows": 0, "pattern_specific_capture_rows": 0, "pattern_specific_gaps": 1000, "integrated_trace_rows": 0, "authority_atomic_rows": 0, "completion_eligible_rows": 0}, "Core Scenario index gap countsが不正です")
    require(list(index["by_scenario"]) == list(CORE_SCENARIOS), "Core 10 Scenario orderが不正です")
    require(len(index["files"]) == 1000 and len({item["id"] for item in index["files"]}) == 1000 and len({item["path"] for item in index["files"]}) == 1000, "Core Scenario row denominatorが縮小または重複しています")
    renamed = 0
    for record in index["files"]:
        path = Path(record["path"])
        payload = documents[path]
        require((staging / path).read_bytes() == payload and record["digest"] == sha256_bytes(payload), f"staged row digestが不正です: {path}")
        row = json.loads(payload)
        require(row["status"] == "pattern-specific-gap" and row["closure"] == {"dedicated_row": True, "dedicated_artifact": True, "pattern_specific_evidence": False, "real_runtime_identity": False, "integrated_runtime_trace": False, "authority_atomic_behavior": False, "completion_eligible": False}, f"staged rowがgap-onlyではありません: {path}")
        require(row["source_bindings"][0]["variant_id"] == "pending-authority-human-review" and row["classification"]["semantic_scope_match"] is False, f"Authority/Variantを自動昇格しています: {path}")
        require(row["scenario"] in CORE_SCENARIOS and row["integrated_reference"]["trace"].get("action_stream") is not True, f"明示gap traceが実Runtime streamを名乗っています: {path}")
        if row["scenario"] == "refusal":
            renamed += 1
            require(".rejection" not in row["id"] and "/rejection.proof.json" not in path.as_posix(), f"legacy rejectionがCore rowへ漏れています: {path}")
    require(renamed == 100, "rejection→refusal staged rowが100件ではありません")
    for path, payload in documents.items():
        require((staging / path).read_bytes() == payload, f"stagingが決定論的生成物と一致しません: {path}")


def promote_staging(
    candidate: Path = CANDIDATE,
    destination: Path = STAGING,
    rollback: Path = ROLLBACK,
    *,
    inject_failure: bool = False,
) -> None:
    require(candidate.is_dir(), "Core Schema検証済みcandidate stagingがありません")
    remove_staging(rollback)
    previous_moved = False
    try:
        if destination.exists():
            os.replace(destination, rollback)
            previous_moved = True
        if inject_failure:
            raise RuntimeError("injected staging swap failure")
        os.replace(candidate, destination)
    except Exception:
        if destination.exists():
            remove_staging(destination)
        if previous_moved and rollback.exists():
            os.replace(rollback, destination)
        remove_staging(candidate)
        raise
    remove_staging(rollback)


def validate_candidate_schema(staging: Path = CANDIDATE, atlas: Path = ATLAS_CORE_BINARY) -> None:
    documents = build_documents()
    validate_staging(documents, staging)
    files = sorted((staging / "evidence/scenarios").rglob("*.json"))
    require(len(files) == 1001, "Core Schema candidate file数が1001ではありません")
    output: list[str] = []
    try:
        for offset in range(0, len(files), 200):
            completed = subprocess.run(
                [str(atlas), "validate", *(str(path) for path in files[offset:offset + 200])],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "Core Schema validation failed"
                raise RuntimeError(detail)
            output.append(completed.stdout)
        validation_log_path(staging).write_text("".join(output), encoding="utf-8")
    except Exception:
        remove_staging(staging)
        raise


def record_schema_pass(
    staging: Path = CANDIDATE,
    destination: Path = STAGING,
    *,
    inject_swap_failure: bool = False,
) -> None:
    documents = build_documents()
    validate_staging(documents, staging)
    validation_log = validation_log_path(staging)
    require(validation_log.is_file(), "Core Schema validation logがありません")
    lines = validation_log.read_text(encoding="utf-8").splitlines()
    require(len(lines) == 1001, "Core Schema validation件数が1001ではありません")
    require(sum("scenario-proof-index.schema.json" in line for line in lines) == 1, "Scenario index Schema validation receiptが不正です")
    require(sum("scenario-proof-row.schema.json" in line for line in lines) == 1000, "Scenario row Schema validation receiptが不正です")
    receipt = {
        "schema_version": 1,
        "core_commit": CORE_COMMIT,
        "index_schema_digest": sha256_file(INDEX_SCHEMA),
        "row_schema_digest": sha256_file(ROW_SCHEMA),
        "validated_files": 1001,
        "index_files": 1,
        "row_files": 1000,
        "staging_aggregate_digest": aggregate(documents),
        "validation_log_digest": sha256_file(validation_log),
    }
    receipt_path(staging).write_bytes(json_bytes(receipt))
    promote_staging(staging, destination, destination.with_name(destination.name + ".rollback"), inject_failure=inject_swap_failure)


def build_report(staging: Path = STAGING) -> dict[str, Any]:
    documents = build_documents()
    validate_staging(documents, staging)
    receipt = receipt_path(staging)
    require(receipt.is_file(), "Core Schema validation receiptがありません")
    receipt = json.loads(receipt.read_text(encoding="utf-8"))
    require(receipt["staging_aggregate_digest"] == aggregate(documents) and receipt["validated_files"] == 1001, "Core Schema receiptが現在stagingと一致しません")
    index = json.loads(documents[Path("evidence/scenarios/index.json")])
    file_rows = index["files"]
    migration = load(MIGRATION)
    return {
        "schema_version": 1,
        "id": "argocd-core-v2-scenario-proof-schema-adapter-gap-v1",
        "status": "incomplete-schema-valid-staging-not-published",
        "core_commit": CORE_COMMIT,
        "inputs": {path: digest for path, digest in index["source_digests"].items()},
        "staging": {
            "root": ".runtime/core-scenario-proof-index-next",
            "candidate_root": ".runtime/core-scenario-proof-index-next.staging",
            "rollback_root": ".runtime/core-scenario-proof-index-next.rollback",
            "generated_files": len(documents),
            "index_files": 1,
            "row_files": 1000,
            "aggregate_digest": aggregate(documents),
            "promotion": "core-schema-pass-then-atomic-directory-rename",
            "publish_on": "schema-validation-and-runtime-closure",
            "failed_generation": "discard-candidate-and-retain-prior-staging",
            "failed_validation": "discard-candidate-and-retain-prior-staging-report-and-canonical-index",
            "failed_swap": "rollback-prior-staging-and-retain-report-and-canonical-index",
        },
        "schema_validation": {
            "status": "passed",
            "core_commit": receipt["core_commit"],
            "index_schema_digest": receipt["index_schema_digest"],
            "row_schema_digest": receipt["row_schema_digest"],
            "validated_files": receipt["validated_files"],
            "index_files": receipt["index_files"],
            "row_files": receipt["row_files"],
        },
        "denominator": index["summary"],
        "scenario_classes": list(index["by_scenario"]),
        "row_identity": {
            "ids_digest": id_digest([item["id"] for item in file_rows]),
            "paths_digest": id_digest([item["path"] for item in file_rows]),
            "digests_digest": id_digest([item["digest"] for item in file_rows]),
            "mapping_counts": migration["counts"],
        },
        "canonical_publication": {
            "path": LEGACY_INDEX.as_posix(),
            "current_digest": sha256_file(ROOT / LEGACY_INDEX),
            "emitted": False,
            "legacy_index_preserved": True,
            "reason": "Schema適合stagingは実Runtime、Authority Atomic behavior、completion-eligible Proofを持たないためcanonicalへ発行しない。",
        },
        "credit": {"runtime": 0, "semantic": 0, "completion": 0},
        "remaining_gaps": {
            "authority_pending_human": 63889,
            "dedicated_runtime_rows": 13,
            "remaining_runtime_rows": 987,
            "authority_atomic_rows": 0,
            "completion_eligible_rows": 0,
            "integrated_trace_rows": 0,
        },
    }


def validate_report(report: dict[str, Any]) -> None:
    require(report["status"] == "incomplete-schema-valid-staging-not-published", "Scenario Schema adapterが完了扱いです")
    staging = report["staging"]
    require(staging["root"] == ".runtime/core-scenario-proof-index-next" and staging["candidate_root"] == ".runtime/core-scenario-proof-index-next.staging" and staging["rollback_root"] == ".runtime/core-scenario-proof-index-next.rollback", "Scenario Schema staging path契約が不正です")
    require(staging["promotion"] == "core-schema-pass-then-atomic-directory-rename" and staging["failed_generation"] == "discard-candidate-and-retain-prior-staging" and staging["failed_validation"] == "discard-candidate-and-retain-prior-staging-report-and-canonical-index" and staging["failed_swap"] == "rollback-prior-staging-and-retain-report-and-canonical-index", "Scenario Schema atomic staging契約が縮小しています")
    require(report["schema_validation"]["status"] == "passed" and report["schema_validation"]["validated_files"] == 1001 and report["schema_validation"]["row_files"] == 1000, "Core Schema validation denominatorが不正です")
    denominator = report["denominator"]
    require(denominator["patterns"] == 100 and denominator["rows"] == denominator["dedicated_artifacts"] == denominator["pattern_specific_gaps"] == 1000, "Scenario Schema denominatorが縮小しています")
    require(denominator["pattern_specific_rows"] == denominator["pattern_specific_runtime_rows"] == denominator["integrated_trace_rows"] == denominator["authority_atomic_rows"] == denominator["completion_eligible_rows"] == 0, "Schema adapterがProof creditを持っています")
    require(report["scenario_classes"] == list(CORE_SCENARIOS) and "rejection" not in report["scenario_classes"] and "refusal" in report["scenario_classes"], "rejection→refusal Schema mappingが不正です")
    require(report["row_identity"]["mapping_counts"] == {"old_rows": 1000, "new_rows": 1000, "identity": 900, "renamed_rejection_to_refusal": 100, "runtime_credit": 0, "completion_eligible": 0}, "Scenario row mappingが非後退ではありません")
    require(report["canonical_publication"]["emitted"] is False and report["canonical_publication"]["legacy_index_preserved"] is True and report["canonical_publication"]["current_digest"] == sha256_file(ROOT / LEGACY_INDEX), "canonical indexを早期置換しています")
    require(report["credit"] == {"runtime": 0, "semantic": 0, "completion": 0}, "Schema adapterへcreditを付与しています")
    require(report["remaining_gaps"] == {"authority_pending_human": 63889, "dedicated_runtime_rows": 13, "remaining_runtime_rows": 987, "authority_atomic_rows": 0, "completion_eligible_rows": 0, "integrated_trace_rows": 0}, "独立Gapを隠しています")


def publish_report(report: dict[str, Any], target: Path = OUTPUT, inject_failure: bool = False) -> None:
    validate_report(report)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".next")
    temporary.write_bytes(json_bytes(report))
    if inject_failure:
        temporary.unlink()
        raise RuntimeError("injected report publish failure")
    os.replace(temporary, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--validate-candidate", action="store_true")
    parser.add_argument("--record-schema-pass", action="store_true")
    parser.add_argument("--publish-report", action="store_true")
    args = parser.parse_args()
    if sum((args.stage, args.validate_candidate, args.record_schema_pass, args.publish_report)) != 1:
        raise ValueError("--stage、--validate-candidate、--record-schema-pass、--publish-reportのいずれか1つが必要です")
    if args.stage:
        documents = build_documents()
        write_staging(documents)
        validate_staging(documents, CANDIDATE)
        print("Core v2 Scenario Schema candidate staged: index=1 rows=1000 runtime_credit=0")
    elif args.validate_candidate:
        validate_candidate_schema()
        print("Core v2 Scenario Schema candidate validated: files=1001")
    elif args.record_schema_pass:
        record_schema_pass()
        print("Core v2 Scenario Schema receipt recorded: validated=1001")
    else:
        report = build_report()
        publish_report(report)
        shutil.rmtree(STAGING)
        print("Core v2 Scenario Schema gap published: rows=1000 canonical=false completion=0")


if __name__ == "__main__":
    main()
