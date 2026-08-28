#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Definitive Skill EvalのEvidence recordを決定論生成する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "evidence/raw/evidence.skill-definitive-eval.v3-5-2/result.json"
OUTPUT = ROOT / "evidence/records/evidence.skill-definitive-eval.v3-5-2.evidence.yaml"
HARNESS = ROOT / "scripts/generate_definitive_skill_eval.py"
CONTRACT = ROOT / ".agents/skills/argocd-atlas-router/references/mastery-contract.json"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_record() -> dict:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    if raw.get("verdict") != "pass" or raw.get("completion_claim") is not False:
        raise ValueError("Definitive Skill Eval raw resultが合格または非Completion境界を満たしていません")
    return {
        "schema_version": 1,
        "id": "evidence.skill-definitive-eval.v3-5-2",
        "atlas_id": "argocd-reference-atlas",
        "claim_ids": ["claim.skill.coverage-grounded-routing"],
        "kind": "skill-eval",
        "producer": "argocd-atlas-definitive-skill-eval-harness",
        "command": "make skill-definitive-eval",
        "created_at": "2026-08-28T13:00:00Z",
        "environment": {
            "profile": "local",
            "manifest_digest": sha256(CONTRACT),
            "lab": "skill-definitive-eval",
            "argocd_version": "v3.5.2",
        },
        "source_digest": "sha256:fc76f2c5267059ae59c118c9f4924c51e4ca179476a687cced7f43ae1c977674",
        "harness_digest": sha256(HARNESS),
        "harness_path": HARNESS.relative_to(ROOT).as_posix(),
        "artifact": {
            "uri": RAW.relative_to(ROOT).as_posix(),
            "digest": sha256(RAW),
            "media_type": "application/json",
            "size_bytes": RAW.stat().st_size,
        },
        "verdict": "pass",
        "retention": "git",
    }


def main() -> None:
    OUTPUT.write_text(yaml.safe_dump(build_record(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    print("Generated Definitive Skill Eval Evidence record")


if __name__ == "__main__":
    main()
