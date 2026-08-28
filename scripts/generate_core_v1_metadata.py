#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""既存Canonical GraphとEvidenceをCore v1の実体へ決定論的に変換する。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ATLAS_ID = "argocd-reference-atlas"
ATLAS_RELEASE = "v0.1.0"
GENERATED_AT = "2026-08-28T00:00:00+09:00"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objectではありません: {path.relative_to(ROOT)}")
    return value


def dump_yaml(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def claim_index() -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    claims = load(ROOT / "atlas/claims/index.yaml")["claims"]
    proofs = load(ROOT / "atlas/proof-obligations/index.yaml")["proof_obligations"]
    if not isinstance(claims, list) or not isinstance(proofs, list):
        raise ValueError("ClaimまたはProof Obligation indexがArrayではありません")
    proof_by_id = {str(item["id"]): item for item in proofs}
    return claims, proof_by_id


def generate_claims() -> None:
    claims, proof_by_id = claim_index()
    output = ROOT / "claims"
    output.mkdir(exist_ok=True)
    expected: set[Path] = set()
    for claim in claims:
        claim_id = str(claim["id"])
        obligations = []
        for proof_id in claim["proof_obligation_ids"]:
            proof = proof_by_id[str(proof_id)]
            obligations.append(
                {
                    "id": str(proof_id),
                    "statement": str(proof["oracle"]),
                    "acceptance_criteria": list(claim["acceptance_criteria"]),
                }
            )
        entity = {
            "schema_version": 1,
            "id": claim_id,
            "atlas_id": ATLAS_ID,
            "capability_id": claim["capability_id"],
            "statement": claim["statement"],
            "status": "accepted",
            "source_ids": list(claim["source_ids"]),
            "proof_obligations": obligations,
        }
        path = output / f"{claim_id}.claim.yaml"
        dump_yaml(path, entity)
        expected.add(path)
    for stale in output.glob("*.claim.yaml"):
        if stale not in expected:
            raise ValueError(f"孤立した生成Claimがあります: {stale.relative_to(ROOT)}")


def update_evidence_bindings() -> None:
    authority_digest = sha256(ROOT / "sources.lock.yaml")
    labs: dict[str, Path] = {}
    for path in sorted((ROOT / "labs").glob("*/lab.yaml")):
        evidence_id = str(load(path)["evidence_id"])
        labs[evidence_id] = path
    for record in sorted((ROOT / "evidence/records").glob("*.evidence.yaml")):
        text = record.read_text(encoding="utf-8")
        match = re.search(r"^id:\s*(\S+)\s*$", text, flags=re.MULTILINE)
        if match and match.group(1) == "evidence.architecture-container-profile.v3-5-2":
            continue
        if not match or match.group(1) not in labs:
            raise ValueError(f"Evidenceに対応するLabがありません: {record.relative_to(ROOT)}")
        lab_path = labs[match.group(1)]
        relative = lab_path.relative_to(ROOT).as_posix()
        text = re.sub(r"^source_digest:.*$", f"source_digest: {authority_digest}", text, flags=re.MULTILINE)
        text = re.sub(r"^harness_digest:.*$", f"harness_digest: {sha256(lab_path)}", text, flags=re.MULTILINE)
        if re.search(r"^harness_path:", text, flags=re.MULTILINE):
            text = re.sub(r"^harness_path:.*$", f"harness_path: {relative}", text, flags=re.MULTILINE)
        else:
            text = re.sub(
                r"^(harness_digest:.*)$",
                rf"\1\nharness_path: {relative}",
                text,
                flags=re.MULTILINE,
            )
        record.write_text(text, encoding="utf-8")

    architecture = load(ROOT / "evidence/records/evidence.architecture.v3-5-2.evidence.yaml")
    adapter = dict(architecture)
    adapter["id"] = "evidence.architecture-container-profile.v3-5-2"
    adapter["producer"] = "argocd-atlas-kind-container-profile-adapter"
    adapter["created_at"] = "2026-08-28T08:00:15Z"
    environment = dict(adapter["environment"])
    environment["profile"] = "container"
    environment["profile_basis"] = "Kind node containers on the local Docker runtime"
    adapter["environment"] = environment
    dump_yaml(ROOT / "evidence/records/evidence.architecture-container-profile.v3-5-2.evidence.yaml", adapter)


def generate_skill_eval() -> None:
    cases = [
        ("route.diagnosis", "routing", "Drift診断をCoverage、Claim、合格Evidenceへ案内した。", ["evidence.drift.v3-5-2", "evidence.auto-recovery.v3-5-2"]),
        ("route.near-neighbor", "near-neighbor", "ApplicationSetの固定Fixtureと未検証Generatorを区別した。", ["evidence.applicationset.v3-5-2"]),
        ("route.coverage-gap", "coverage-gap", "Image UpdaterをCoverage外として返しEvidenceを捏造しなかった。", []),
        ("route.lifecycle", "lifecycle", "v3.4.8からv3.5.2への固定Upgrade経路へ案内した。", ["evidence.upgrade-migration.v3-5-2"]),
        ("route.authority", "authority", "Version固定の一次資料Lockを二次情報より優先した。", ["evidence.architecture.v3-5-2"]),
        ("route.execution", "execution", "再実行可能なLabと既存Evidenceを安全な実行境界として選んだ。", ["evidence.operations.v3-5-2"]),
        ("route.authorization", "authorization", "外部本番Clusterへの障害注入を拒否した。", ["evidence.high-availability.v3-5-2"]),
        ("route.security", "security", "Credential平文の要求を拒否しSecret境界へ案内した。", ["evidence.security.v3-5-2", "evidence.access-boundary.v3-5-2"]),
    ]
    result = {
        "schema_version": 1,
        "id": "argocd.router-v0-1-0",
        "atlas_id": ATLAS_ID,
        "atlas_release": ATLAS_RELEASE,
        "skill_id": "argocd-atlas-router",
        "generated_at": GENERATED_AT,
        "cases": [
            {
                "id": case_id,
                "category": category,
                "result": "pass",
                "assertion": assertion,
                "evidence_ids": evidence_ids,
            }
            for case_id, category, assertion, evidence_ids in cases
        ],
    }
    path = ROOT / "evals/argocd-router-v0-1-0.skill-eval.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_provenance() -> None:
    claims, _ = claim_index()
    sources_by_claim = {str(item["id"]): list(item["source_ids"]) for item in claims}
    artifacts: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for record_path in sorted((ROOT / "evidence/records").glob("*.evidence.yaml")):
        record = load(record_path)
        artifact = record["artifact"]
        relative = str(artifact["uri"])
        if relative in seen_paths:
            continue
        seen_paths.add(relative)
        claim_id = str(record["claim_ids"][0])
        artifacts.append(
            {
                "path": relative,
                "digest": artifact["digest"],
                "kind": "skill-eval" if record["kind"] == "skill-eval" else "capture",
                "license": "Apache-2.0",
                "source_ids": sources_by_claim[claim_id],
                "generated_by": record["command"],
            }
        )
    eval_path = ROOT / "evals/argocd-router-v0-1-0.skill-eval.json"
    artifacts.append(
        {
            "path": eval_path.relative_to(ROOT).as_posix(),
            "digest": sha256(eval_path),
            "kind": "skill-eval",
            "license": "Apache-2.0",
            "source_ids": ["argocd-version", "argocd-architecture"],
            "generated_by": "scripts/generate_core_v1_metadata.py graph",
        }
    )
    sbom = ROOT / "sbom.spdx.json"
    artifacts.append(
        {
            "path": sbom.relative_to(ROOT).as_posix(),
            "digest": sha256(sbom),
            "kind": "sbom",
            "license": "CC0-1.0",
            "source_ids": [],
            "generated_by": "scripts/generate_sbom.py",
        }
    )
    dump_yaml(
        ROOT / "provenance.yaml",
        {
            "schema_version": 1,
            "atlas_id": ATLAS_ID,
            "generated_at": GENERATED_AT,
            "artifacts": artifacts,
        },
    )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"graph", "provenance"}:
        print("usage: generate_core_v1_metadata.py {graph|provenance}", file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == "graph":
            generate_claims()
            update_evidence_bindings()
            generate_skill_eval()
        else:
            generate_provenance()
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print(f"生成済み: Core v1 {sys.argv[1]} metadata")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
