#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Extended Cluster LabまたはSkill EvalからCore Evidence recordを生成する。"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KINDS = {
    "architecture": "conformance",
    "applicationset": "conformance",
    "connection": "attack",
    "hook-wave": "test-report",
    "access-boundary": "attack",
    "high-availability": "recovery",
    "observability": "measurement",
    "drift": "test-report",
    "auto-recovery": "recovery",
    "upgrade-migration": "migration",
    "operations": "recovery",
    "skill-eval": "skill-eval",
}


def fail(message: str) -> None:
    raise ValueError(message)


def root_field(path: Path, key: str) -> str:
    prefix = f"{key}: "
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip().strip("\"'")
    fail(f"{path.relative_to(ROOT)}に{key}がありません")


def tree_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
    for path in sorted(set(files), key=lambda item: str(item.relative_to(ROOT)) if ROOT in item.parents else str(item)):
        label = str(path.relative_to(ROOT)) if ROOT in path.parents else path.name
        digest.update(label.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_digest(lab: str) -> str:
    if lab == "skill-eval":
        return tree_digest([
            ROOT / ".agents/skills/argocd-atlas-router",
            ROOT / "coverage.yaml",
            ROOT / "atlas/claims/index.yaml",
            ROOT / "evals/forward-cases.json",
        ])
    bare = ROOT / ".runtime/source/repo.git"
    if not bare.is_dir():
        fail("ローカルGit fixtureがありません")
    archive = subprocess.run(
        ["git", f"--git-dir={bare}", "archive", "main"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    return hashlib.sha256(archive).hexdigest()


def main() -> int:
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in KINDS:
            fail("usage: record_extended.py LAB")
        lab = sys.argv[1]
        spec = ROOT / "labs" / lab / "lab.yaml"
        evidence_id = root_field(spec, "evidence_id")
        claim_id = root_field(spec, "claim_id")
        artifact = ROOT / "evidence/raw" / evidence_id / "result.json"
        if not artifact.is_file() or not artifact.stat().st_size:
            fail(f"raw artifactがありません: {artifact.relative_to(ROOT)}")

        if lab == "skill-eval":
            harness_paths = [ROOT / "scripts/grade_skill_forward_eval.py", spec]
            environment_paths = [ROOT / "evals/forward-cases.json", artifact]
            profile = "local"
            version = "v3.5.2"
            producer = "codex-independent-forward-evaluator"
            command = "make skill-forward-eval"
        else:
            harness_paths = [
                ROOT / "scripts/extended/common.sh",
                ROOT / "scripts/extended/run.sh",
                ROOT / "scripts/extended/run-suite.sh",
                ROOT / "scripts/extended/cases" / f"{lab}.sh",
                ROOT / "scripts/evidence/record_extended.py",
                ROOT / "scripts/build-local-source.sh",
                spec,
            ]
            if lab in {"high-availability", "upgrade-migration"}:
                harness_paths.append(ROOT / "scripts/extended/isolation.sh")
            if lab == "high-availability":
                environment_paths = [
                    ROOT / "environments/kind/argocd-v3.5.2-ha.lock",
                    ROOT / ".runtime/extended/downloads/high-availability-argocd-install.yaml",
                    ROOT / ".runtime/extended/high-availability-kind-config.yaml",
                ]
            elif lab == "upgrade-migration":
                environment_paths = [
                    ROOT / "environments/kind/argocd-v3.4.8.lock",
                    ROOT / "environments/kind/argocd-v3.5.2.lock",
                    ROOT / ".runtime/extended/downloads/upgrade-migration-v3.4.8-argocd-install.yaml",
                    ROOT / ".runtime/extended/downloads/upgrade-migration-v3.5.2-install.yaml",
                    ROOT / ".runtime/extended/upgrade-migration-v3.4.8-kind-config.yaml",
                ]
            else:
                environment_paths = [
                    ROOT / "environments/kind/argocd-v3.5.2.lock",
                    ROOT / ".runtime/downloads/argocd-install.yaml",
                    ROOT / ".runtime/downloads/argocd-VERSION",
                    ROOT / ".runtime/kind-config.yaml",
                ]
            profile = "cluster"
            version = "v3.4.8-to-v3.5.2" if lab == "upgrade-migration" else "v3.5.2"
            producer = "argocd-atlas-kind-extended-harness"
            command = f"make extended-lab-{lab}"

        content = artifact.read_bytes()
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = ROOT / "evidence/records" / f"{evidence_id}.evidence.yaml"
        record.write_text(
            "\n".join([
                "schema_version: 1",
                f"id: {evidence_id}",
                "atlas_id: argocd-reference-atlas",
                f"claim_ids: [{claim_id}]",
                f"kind: {KINDS[lab]}",
                f"producer: {producer}",
                f"command: {command}",
                f'created_at: "{created}"',
                "environment:",
                f"  profile: {profile}",
                f"  manifest_digest: sha256:{tree_digest(environment_paths)}",
                f"  lab: {lab}",
                f"  argocd_version: {version}",
                f"source_digest: sha256:{source_digest(lab)}",
                f"harness_digest: sha256:{tree_digest(harness_paths)}",
                "artifact:",
                f"  uri: {artifact.relative_to(ROOT)}",
                f"  digest: sha256:{hashlib.sha256(content).hexdigest()}",
                "  media_type: application/json",
                f"  size_bytes: {len(content)}",
                "verdict: pass",
                "retention: git",
                "",
            ]),
            encoding="utf-8",
        )
        print(f"Core evidence recordを生成しました: {record.relative_to(ROOT)}")
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
