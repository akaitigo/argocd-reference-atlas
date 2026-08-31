#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Evidence treeをstagingで完成させ、検証後にrenameで公開する。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable


class AtomicEvidencePublishError(RuntimeError):
    """Evidenceの原子的公開契約を満たせなかった。"""


class FullRunNotPassed(AtomicEvidencePublishError):
    """full-runがpassしていないため公開しない。"""


Rename = Callable[[Path, Path], None]


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _generation_digest(artifacts: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for artifact in artifacts:
        digest.update(artifact["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(artifact["digest"].encode("ascii"))
        digest.update(b"\0")
        digest.update(str(artifact["bytes"]).encode("ascii"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _normalize_relative_paths(paths: Iterable[Path | str]) -> list[Path]:
    normalized: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts or path == Path("."):
            raise AtomicEvidencePublishError(f"Artifact pathはtree内の相対pathである必要があります: {path}")
        normalized.append(path)
    if len(normalized) != len(set(normalized)):
        raise AtomicEvidencePublishError("Artifact pathが重複しています")
    return sorted(normalized, key=lambda item: item.as_posix())


def write_publish_manifest(
    staging_root: Path,
    manifest_path: Path | str,
    artifact_paths: Iterable[Path | str],
    *,
    reporter_id: str,
    reference_commit: str,
) -> dict[str, Any]:
    """今回のrunが生成したArtifact集合だけをmanifestへ固定する。"""
    relative_paths = _normalize_relative_paths(artifact_paths)
    artifacts: list[dict[str, Any]] = []
    for relative in relative_paths:
        path = staging_root / relative
        if not path.is_file():
            raise AtomicEvidencePublishError(f"生成対象Artifactがありません: {relative.as_posix()}")
        artifacts.append({"path": relative.as_posix(), "digest": _sha256(path), "bytes": path.stat().st_size})
    manifest_relative = _normalize_relative_paths([manifest_path])[0]
    manifest = {
        "schema_version": 1,
        "id": reporter_id,
        "status": "passed",
        "reference": {
            "repository": "frontend-behavior-atlas",
            "commit": reference_commit,
            "contract": "atomic-evidence-retention",
        },
        "retention_contract": {
            "publish_on": "full-run-passed",
            "failed_run": "retain-prior-success",
            "swap": "staged-directory-rename-with-rollback",
            "partial_overwrite": "rejected",
            "mixed_generation": "rejected",
        },
        "artifact_count": len(artifacts),
        "generation_digest": _generation_digest(artifacts),
        "artifacts": artifacts,
    }
    target = staging_root / manifest_relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate_publish_manifest(
    staging_root: Path,
    manifest_path: Path | str,
    expected_artifact_paths: Iterable[Path | str],
) -> dict[str, Any]:
    """集合、size、digest、generation digestを再計算し、部分生成と混在を拒否する。"""
    manifest_relative = _normalize_relative_paths([manifest_path])[0]
    path = staging_root / manifest_relative
    if not path.is_file():
        raise AtomicEvidencePublishError("Atomic publish manifestがありません")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise AtomicEvidencePublishError(f"Atomic publish manifestを読めません: {error}") from error
    expected = [item.as_posix() for item in _normalize_relative_paths(expected_artifact_paths)]
    artifacts = manifest.get("artifacts")
    if manifest.get("status") != "passed" or not isinstance(artifacts, list):
        raise AtomicEvidencePublishError("full-run pass manifestではありません")
    actual = [item.get("path") for item in artifacts if isinstance(item, dict)]
    if actual != expected or manifest.get("artifact_count") != len(expected):
        raise AtomicEvidencePublishError("Artifact集合がfull-run分母と一致しません")
    rebuilt: list[dict[str, Any]] = []
    for artifact in artifacts:
        relative = _normalize_relative_paths([artifact["path"]])[0]
        artifact_path = staging_root / relative
        if not artifact_path.is_file():
            raise AtomicEvidencePublishError(f"Manifest対象Artifactがありません: {relative.as_posix()}")
        rebuilt_item = {"path": relative.as_posix(), "digest": _sha256(artifact_path), "bytes": artifact_path.stat().st_size}
        if rebuilt_item != artifact:
            raise AtomicEvidencePublishError(f"Artifactが別generationと混在または破損しています: {relative.as_posix()}")
        rebuilt.append(rebuilt_item)
    if manifest.get("generation_digest") != _generation_digest(rebuilt):
        raise AtomicEvidencePublishError("generation digestが一致しません")
    return manifest


def _default_rename(source: Path, destination: Path) -> None:
    os.rename(source, destination)


def _require_safe_siblings(output_root: Path, staging_root: Path, backup_root: Path) -> None:
    roots = [path.absolute() for path in (output_root, staging_root, backup_root)]
    if len(set(roots)) != 3 or any(path.parent != roots[0].parent for path in roots):
        raise AtomicEvidencePublishError("output、staging、backupは異なる同階層directoryである必要があります")
    if roots[0].name in {"", ".", ".."} or roots[0].parent == roots[0]:
        raise AtomicEvidencePublishError("広すぎるEvidence rootは公開対象にできません")


def publish_evidence_tree(
    output_root: Path,
    staging_root: Path,
    backup_root: Path,
    populate: Callable[[Path], None],
    validate: Callable[[Path], None],
    *,
    full_run_passed: bool,
    rename: Rename = _default_rename,
) -> None:
    """既存treeを保持したstagingを構築し、full-run pass後だけswapする。"""
    _require_safe_siblings(output_root, staging_root, backup_root)
    if backup_root.exists():
        raise AtomicEvidencePublishError(f"前回swapのbackupが残っています: {backup_root}")
    if staging_root.exists():
        shutil.rmtree(staging_root)
    if output_root.is_dir():
        shutil.copytree(output_root, staging_root, symlinks=True)
    elif output_root.exists():
        raise AtomicEvidencePublishError("Evidence output rootがdirectoryではありません")
    else:
        staging_root.mkdir(parents=True)

    previous_retained = False
    try:
        populate(staging_root)
        if not full_run_passed:
            raise FullRunNotPassed("full-runがpassしていないため、直前成功Evidenceを保持しました")
        validate(staging_root)
        if output_root.exists():
            rename(output_root, backup_root)
            previous_retained = True
        try:
            rename(staging_root, output_root)
        except Exception as swap_error:
            if previous_retained:
                try:
                    rename(backup_root, output_root)
                    previous_retained = False
                except Exception as rollback_error:
                    raise AtomicEvidencePublishError(
                        f"Evidence swapとrollbackが失敗しました。直前成功Evidenceはbackupに保持されています: {backup_root}"
                    ) from rollback_error
            raise AtomicEvidencePublishError("Evidence swapに失敗し、直前成功Evidenceへrollbackしました") from swap_error
        if previous_retained:
            shutil.rmtree(backup_root)
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise
