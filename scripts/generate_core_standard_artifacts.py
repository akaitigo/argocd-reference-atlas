#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Core v2標準Artifactをgap-only stagingから原子的に公開する。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".runtime/core-standard-artifacts-next"
BACKUP = ROOT / ".runtime/core-standard-artifacts-previous"
LEGACY_MANIFEST = Path("integrations/reference-system/manifest.yaml")
LEGACY_RESULTS = Path("evidence/reference-system/results.json")
SCENARIO_INDEX = Path("evidence/scenarios/index.json")
RUNTIME_REGISTRY = Path("evidence/scenarios/runtime/index.yaml")
MANIFEST = Path("integrations/reference-system/manifest.json")
REFERENCE_RESULTS = Path("artifacts/reference-system/results.json")
PATTERN_RESULTS = Path("artifacts/pattern-scenarios/results.json")
MIGRATION = Path("migrations/scenario-class-refusal-v1.json")
BASELINE = Path("baselines/scenario-row-id-migration-v1.json")
PUBLISH_MANIFEST = Path("artifacts/core-v2/core-standard-artifacts-publish.json")
GENERATOR = Path("scripts/generate_core_standard_artifacts.py")
VALIDATOR = Path("scripts/validate_core_standard_artifacts.py")
GENERATED_AT = "2026-08-31T00:00:00Z"
BASELINE_COMMIT = "7b2192335a66618a76fd932ad4f5c105a8b00f29"
LEGACY_SCENARIOS = (
    "normal", "boundary", "rejection", "failure", "recovery",
    "migration", "operations", "security", "performance", "compatibility",
)
CORE_SCENARIOS = (
    "normal", "boundary", "refusal", "failure", "recovery",
    "migration", "operations", "security", "performance", "compatibility",
)
CORE_BY_LEGACY = dict(zip(LEGACY_SCENARIOS, CORE_SCENARIOS))
COMPLETION_LIMITS = [
    "Core標準Artifactのgap-only投影であり、統合Argo CD Runtimeを実行していない。",
    "既存Lab、fixture、統合Evidence、historical Evidenceを専用Scenario Runtime creditへ変換しない。",
    "Authority Human Review、approved Variant denominator、Atomic behavior bindingが0の間はCompletion eligibleを0に保つ。",
    "Pattern Scenarioの未実行987 rowをgapとして保持し、既存13 dedicated Runtime reportと混同しない。",
]


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def binding(path: Path, root: Path = ROOT) -> dict[str, Any]:
    target = root / path
    return {"path": path.as_posix(), "digest": sha256_file(target), "bytes": target.stat().st_size}


def aggregate_digest(paths: list[Path], root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def id_digest(values: list[str]) -> str:
    return sha256_bytes(("\n".join(values) + "\n").encode("utf-8"))


def load_json(path: Path, root: Path = ROOT) -> dict[str, Any]:
    value = json.loads((root / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path}")
    return value


def gap_path(scenario: str, kind: str) -> Path:
    return Path(f"artifacts/reference-system/gaps/{scenario}.{kind}-gap.json")


def output_paths() -> list[Path]:
    gaps = [gap_path(scenario, kind) for scenario in CORE_SCENARIOS for kind in ("trace", "screenshot")]
    return [MANIFEST, REFERENCE_RESULTS, PATTERN_RESULTS, MIGRATION, BASELINE, *gaps, PUBLISH_MANIFEST]


def build_documents() -> dict[Path, bytes]:
    legacy_manifest = yaml.safe_load((ROOT / LEGACY_MANIFEST).read_text(encoding="utf-8"))
    legacy_results = load_json(LEGACY_RESULTS)
    index = load_json(SCENARIO_INDEX)
    files = index["files"]
    if index["scenario_order"] != list(LEGACY_SCENARIOS) or len(files) != 1000:
        raise ValueError("legacy Scenario denominatorが期待する100×10ではありません")

    patterns_by_scenario: dict[str, list[str]] = {}
    for legacy in LEGACY_SCENARIOS:
        patterns_by_scenario[legacy] = [item["pattern_id"] for item in files if item["scenario"] == legacy]
        if len(patterns_by_scenario[legacy]) != 100 or len(set(patterns_by_scenario[legacy])) != 100:
            raise ValueError(f"legacy Scenario row集合が100件ではありません: {legacy}")

    legacy_scenarios = {item["id"]: item for item in legacy_manifest["scenarios"]}
    manifest_scenarios = []
    for legacy, core in CORE_BY_LEGACY.items():
        source = legacy_scenarios[legacy]
        manifest_scenarios.append({
            "id": core,
            "patterns": patterns_by_scenario[legacy],
            "runtime_boundaries": [
                *[f"controller:{item}" for item in source["controller_components"]],
                *[f"kubernetes:{item}" for item in source["kubernetes_behaviors"]],
            ],
            "assertions": source["assertions"],
        })
    manifest = {
        "schema_version": 1,
        "id": "argocd-core-reference-system-gap-contract-v1",
        "status": "bounded-integration-proof",
        "subject": "argocd-v3-5-2-core-standard-gap-contract-not-runtime-completion",
        "entry": LEGACY_MANIFEST.as_posix(),
        "runtime": "gap-only-no-runtime-credit",
        "test": VALIDATOR.as_posix(),
        "evidence": REFERENCE_RESULTS.as_posix(),
        "scenarios": manifest_scenarios,
        "completion_limits": COMPLETION_LIMITS,
    }

    documents: dict[Path, bytes] = {}
    for scenario in CORE_SCENARIOS:
        documents[gap_path(scenario, "trace")] = json_bytes({
            "schema_version": 1,
            "kind": "explicit-runtime-gap",
            "scenario": scenario,
            "runtime_executed": False,
            "runtime_attempts": 0,
            "required_streams": ["action", "network", "resource"],
            "present_streams": [],
            "completion_credit": False,
        })
        documents[gap_path(scenario, "screenshot")] = json_bytes({
            "schema_version": 1,
            "kind": "explicit-screenshot-gap",
            "scenario": scenario,
            "runtime_executed": False,
            "capture_present": False,
            "completion_credit": False,
        })

    source_digest = aggregate_digest([LEGACY_MANIFEST, LEGACY_RESULTS, SCENARIO_INDEX])
    harness_digest = aggregate_digest([GENERATOR, VALIDATOR])
    tests = []
    for scenario in CORE_SCENARIOS:
        trace = gap_path(scenario, "trace")
        screenshot = gap_path(scenario, "screenshot")
        trace_bytes, screenshot_bytes = documents[trace], documents[screenshot]
        tests.append({
            "id": f"argocd.reference-system.{scenario}.gap",
            "scenario": scenario,
            "title": f"{scenario} integrated Runtime gap",
            "file": LEGACY_MANIFEST.as_posix(),
            "line": 1,
            "outcome": "not-run-core-standard-gap",
            "attempts": 1,
            "duration_ms": 0,
            "final_status": "skipped",
            "error": "専用統合Runtimeは未実行。gap-only ArtifactはRuntime Evidenceではない。",
            "trace": {"path": trace.as_posix(), "digest": sha256_bytes(trace_bytes), "bytes": len(trace_bytes)},
            "screenshot": {"path": screenshot.as_posix(), "digest": sha256_bytes(screenshot_bytes), "bytes": len(screenshot_bytes)},
        })
    reference_results = {
        "schema_version": 1,
        "id": manifest["id"],
        "created_at": GENERATED_AT,
        "status": "failed",
        "command": "python3 scripts/generate_core_standard_artifacts.py",
        "profile": "gap-only-no-runtime",
        "counts": {"total": 10, "passed": 0, "failed": 0, "flaky": 0, "skipped": 10},
        "duration_ms": 1,
        "source_digest": source_digest,
        "harness_digest": harness_digest,
        "environment": {
            "profile_kind": "gap-only",
            "real_runtime": False,
            "runtime_attempts": 0,
            "retries": 0,
            "trace_mode": "off",
            "argocd_version": "v3.5.2",
            "kubernetes_context": None,
            "fixture_runtime_credit": False,
            "integrated_evidence_runtime_credit": False,
            "historical_evidence_runtime_credit": False,
        },
        "trace_contract": {
            "per_scenario": True,
            "required_streams": ["action", "network", "resource"],
            "console_events": "required-but-not-captured",
        },
        "completion_limits": COMPLETION_LIMITS,
        "tests": tests,
    }

    runtime_registry = yaml.safe_load((ROOT / RUNTIME_REGISTRY).read_text(encoding="utf-8"))
    pattern_results = {
        "schema_version": 1,
        "id": "argocd-pattern-scenario-runtime-gap-v1",
        "created_at": GENERATED_AT,
        "status": "failed",
        "command": "python3 scripts/generate_core_standard_artifacts.py",
        "profile": "gap-only-no-runtime",
        "counts": {"rows": 0, "variants": 0, "total": 0, "passed": 0, "failed": 0, "flaky": 0, "skipped": 0},
        "source_digest": aggregate_digest([SCENARIO_INDEX, RUNTIME_REGISTRY]),
        "harness_digest": harness_digest,
        "environment": {
            "profile_kind": "gap-only",
            "real_runtime": False,
            "runtime_attempts": 0,
            "retries": 0,
            "trace_mode": "off",
            "argocd_version": "v3.5.2",
            "kubernetes_context": None,
            "fixture_runtime_credit": False,
            "integrated_evidence_runtime_credit": False,
            "historical_evidence_runtime_credit": False,
            "dedicated_runtime_reports_preserved": len(runtime_registry["reports"]),
        },
        "retention_contract": {
            "publish_on": "full-run-passed",
            "failed_run": "retain-prior-success",
            "swap": "staged-directory-rename-with-rollback",
        },
        "trace_contract": {
            "per_variant": True,
            "required_streams": ["action", "network", "resource"],
            "oracle_attachment": "required-but-not-captured",
        },
        "completion_limits": COMPLETION_LIMITS,
        "tests": [],
    }

    rows = []
    old_ids, new_ids = [], []
    for item in files:
        old_id, legacy = item["id"], item["scenario"]
        core = CORE_BY_LEGACY[legacy]
        new_id = old_id.rsplit(".", 1)[0] + "." + core
        old_path = item["path"]
        new_path = old_path.rsplit("/", 1)[0] + "/" + core + ".proof.json"
        old_ids.append(old_id)
        new_ids.append(new_id)
        rows.append({
            "old_row_id": old_id,
            "new_row_id": new_id,
            "old_path": old_path,
            "new_path": new_path,
            "legacy_scenario": legacy,
            "core_scenario": core,
            "mapping_kind": "renamed" if legacy == "rejection" else "identity",
            "old_proof_digest": item["digest"],
            "new_proof_emitted": False if legacy == "rejection" else True,
            "status": "mapped-gap-not-promoted",
            "runtime_credit": False,
            "completion_eligible": False,
        })
    migration = {
        "schema_version": 1,
        "id": "argocd-scenario-class-refusal-migration-v1",
        "status": "incomplete-mapping-only-no-runtime-credit",
        "source": {"path": SCENARIO_INDEX.as_posix(), "digest": sha256_file(ROOT / SCENARIO_INDEX)},
        "scenario_mapping": [
            {"legacy": legacy, "core": core, "mapping_kind": "renamed" if legacy == "rejection" else "identity"}
            for legacy, core in CORE_BY_LEGACY.items()
        ],
        "counts": {"old_rows": 1000, "new_rows": 1000, "identity": 900, "renamed_rejection_to_refusal": 100, "runtime_credit": 0, "completion_eligible": 0},
        "rows": rows,
    }
    baseline = {
        "schema_version": 1,
        "id": "argocd-scenario-row-id-migration-baseline-v1",
        "source_commit": BASELINE_COMMIT,
        "old_row_count": len(old_ids),
        "new_row_count": len(new_ids),
        "legacy_scenario_order": list(LEGACY_SCENARIOS),
        "core_scenario_order": list(CORE_SCENARIOS),
        "old_order_digest": id_digest(old_ids),
        "old_set_digest": id_digest(sorted(old_ids)),
        "new_order_digest": id_digest(new_ids),
        "new_set_digest": id_digest(sorted(new_ids)),
        "renamed_row_count": sum(item["mapping_kind"] == "renamed" for item in rows),
        "identity_row_count": sum(item["mapping_kind"] == "identity" for item in rows),
        "runtime_credit_floor": 0,
        "completion_eligible_floor": 0,
    }

    documents[MANIFEST] = json_bytes(manifest)
    documents[REFERENCE_RESULTS] = json_bytes(reference_results)
    documents[PATTERN_RESULTS] = json_bytes(pattern_results)
    documents[MIGRATION] = json_bytes(migration)
    documents[BASELINE] = json_bytes(baseline)
    listed = []
    for relative in sorted((path for path in documents), key=lambda item: item.as_posix()):
        payload = documents[relative]
        listed.append({"path": relative.as_posix(), "digest": sha256_bytes(payload), "bytes": len(payload)})
    documents[PUBLISH_MANIFEST] = json_bytes({
        "schema_version": 1,
        "id": "argocd-core-standard-artifacts-atomic-publish-v1",
        "generated_at": GENERATED_AT,
        "status": "gap-artifacts-current",
        "staging_root": ".runtime/core-standard-artifacts-next",
        "backup_root": ".runtime/core-standard-artifacts-previous",
        "publication": {
            "publish_on": "full-generation-and-verifier-passed",
            "failed_generation": "retain-prior-success",
            "swap": "per-file-rename-with-transaction-rollback",
        },
        "runtime_credit": False,
        "files": listed,
    })
    return documents


def write_staging(documents: dict[Path, bytes], staging: Path = STAGING) -> None:
    if staging.exists():
        shutil.rmtree(staging)
    for relative, payload in documents.items():
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def validate_staged(documents: dict[Path, bytes], staging: Path = STAGING) -> None:
    """canonicalを変更する前にstagingの構造と決定性を検証する。"""
    import validate_core_standard_artifacts as verifier

    bundle = verifier.load_bundle(staging)
    verifier.validate_bundle(bundle, ROOT)
    for relative, payload in documents.items():
        if (staging / relative).read_bytes() != payload:
            raise ValueError(f"staging outputが現在input/generatorと一致しません: {relative}")


def publish_staged(
    root: Path,
    staging: Path,
    backup: Path,
    paths: list[Path],
    inject_failure_after: int | None = None,
) -> None:
    if backup.exists():
        shutil.rmtree(backup)
    published: list[Path] = []
    backed_up: list[Path] = []
    try:
        for index, relative in enumerate(paths):
            staged, final, previous = staging / relative, root / relative, backup / relative
            if not staged.is_file():
                raise ValueError(f"staging outputがありません: {relative}")
            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                previous.parent.mkdir(parents=True, exist_ok=True)
                os.replace(final, previous)
                backed_up.append(relative)
            os.replace(staged, final)
            published.append(relative)
            if inject_failure_after is not None and index == inject_failure_after:
                raise RuntimeError("injected publish failure")
    except Exception:
        for relative in reversed(published):
            final = root / relative
            if final.exists():
                final.unlink()
        for relative in reversed(backed_up):
            previous, final = backup / relative, root / relative
            if previous.exists():
                final.parent.mkdir(parents=True, exist_ok=True)
                os.replace(previous, final)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if backup.exists():
        shutil.rmtree(backup)


def main() -> None:
    documents = build_documents()
    expected = output_paths()
    if set(documents) != set(expected):
        raise ValueError("Core標準Artifact output集合が不一致です")
    write_staging(documents)
    try:
        validate_staged(documents)
    except Exception:
        if STAGING.exists():
            shutil.rmtree(STAGING)
        raise
    publish_staged(ROOT, STAGING, BACKUP, expected)
    print("Core standard gap artifacts generated: scenarios=10 mappings=1000 runtime_credit=0")


if __name__ == "__main__":
    main()
