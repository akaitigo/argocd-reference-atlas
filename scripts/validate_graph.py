#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Atlas固有Graphの参照整合性とEvidence接続を検証する。"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INLINE_LIST = re.compile(r"^\[(.*)]$")


def fail(message: str) -> None:
    raise ValueError(message)


def scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def inline_list(value: str) -> list[str]:
    match = INLINE_LIST.fullmatch(value.strip())
    if not match:
        fail(f"inline listを解釈できません: {value}")
    body = match.group(1).strip()
    if not body:
        return []
    return [scalar(item) for item in body.split(",")]


def root_value(path: Path, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.fullmatch(line)
        if match:
            return scalar(match.group(1))
    fail(f"{path.relative_to(ROOT)}に{key}がありません")


def records(path: Path, section: str) -> list[dict[str, str]]:
    """2-space indentのYAML record配列から、このAtlasで使うscalarだけを読む。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((index for index, line in enumerate(lines) if line == f"{section}:"), None)
    if start is None:
        fail(f"{path.relative_to(ROOT)}にsection {section}がありません")
    result: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        item = re.fullmatch(r"  - ([a-z_]+):\s*(.*?)\s*", line)
        field = re.fullmatch(r"    ([a-z_]+):\s*(.*?)\s*", line)
        if item:
            if current is not None:
                result.append(current)
            current = {item.group(1): scalar(item.group(2))}
        elif field and current is not None:
            current[field.group(1)] = field.group(2).strip()
    if current is not None:
        result.append(current)
    if not result:
        fail(f"{path.relative_to(ROOT)}のsection {section}が空です")
    return result


def by_id(items: list[dict[str, str]], label: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in items:
        item_id = scalar(item.get("id", ""))
        if not item_id:
            fail(f"{label}にidがないrecordがあります")
        if item_id in result:
            fail(f"{label} IDが重複しています: {item_id}")
        result[item_id] = item
    return result


def evidence_ids() -> set[str]:
    result: set[str] = set()
    for path in sorted((ROOT / "evidence" / "records").glob("*.evidence.yaml")):
        evidence_id = root_value(path, "id")
        if evidence_id in result:
            fail(f"Evidence IDが重複しています: {evidence_id}")
        result.add(evidence_id)
    return result


def validate() -> None:
    atlas = ROOT / "atlas.yaml"
    coverage_file = ROOT / "coverage.yaml"
    sources_file = ROOT / "sources.lock.yaml"
    capability_file = ROOT / "atlas" / "capabilities" / "index.yaml"
    claim_file = ROOT / "atlas" / "claims" / "index.yaml"
    proof_file = ROOT / "atlas" / "proof-obligations" / "index.yaml"

    certificate = ROOT / "evidence" / "completion-certificate.json"
    status = root_value(atlas, "status")
    if status == "complete" and not certificate.is_file():
        fail("complete状態にはCompletion Certificateが必要です")
    if status == "incomplete" and certificate.exists():
        fail("incomplete状態でCompletion Certificateを配置できません")

    expected_lock = root_value(coverage_file, "authority_lock_digest")
    actual_lock = "sha256:" + hashlib.sha256(sources_file.read_bytes()).hexdigest()
    if expected_lock != actual_lock:
        fail(f"Authority Lock digestが一致しません: expected={expected_lock}, actual={actual_lock}")

    targets = by_id(records(coverage_file, "targets"), "Coverage Target")
    capabilities = by_id(records(capability_file, "capabilities"), "Capability")
    claims = by_id(records(claim_file, "claims"), "Claim")
    proofs = by_id(records(proof_file, "proof_obligations"), "Proof Obligation")
    sources = by_id(records(sources_file, "sources"), "Authority Source")
    actual_evidence = evidence_ids()

    mapped_targets = {scalar(item.get("coverage_target_id", "")) for item in capabilities.values()}
    implemented_targets = {
        target_id
        for target_id, item in targets.items()
        if scalar(item.get("state", "")) in {"covered", "partial"}
    }
    if implemented_targets != mapped_targets:
        fail(f"implemented Target/Capability対応が一致しません: targets={sorted(implemented_targets)}, mapped={sorted(mapped_targets)}")

    for capability_id, capability in capabilities.items():
        target_id = scalar(capability.get("coverage_target_id", ""))
        for claim_id in inline_list(capability.get("claim_ids", "[]")):
            if claim_id not in claims:
                fail(f"{capability_id}が未定義Claimを参照しています: {claim_id}")
            if scalar(claims[claim_id].get("capability_id", "")) != capability_id:
                fail(f"{claim_id}のCapability逆参照が一致しません")
        for source_id in inline_list(capability.get("source_ids", "[]")):
            if source_id not in sources:
                fail(f"{capability_id}が未定義Sourceを参照しています: {source_id}")
        target_claims = inline_list(targets[target_id].get("claim_ids", "[]"))
        if sorted(target_claims) != sorted(inline_list(capability.get("claim_ids", "[]"))):
            fail(f"{target_id}のClaim接続がCapabilityと一致しません")

    for claim_id, claim in claims.items():
        for source_id in inline_list(claim.get("source_ids", "[]")):
            if source_id not in sources:
                fail(f"{claim_id}が未定義Sourceを参照しています: {source_id}")
        for proof_id in inline_list(claim.get("proof_obligation_ids", "[]")):
            if proof_id not in proofs:
                fail(f"{claim_id}が未定義Proof Obligationを参照しています: {proof_id}")
            if scalar(proofs[proof_id].get("claim_id", "")) != claim_id:
                fail(f"{proof_id}のClaim逆参照が一致しません")

    expected_evidence: set[str] = set()
    for proof_id, proof in proofs.items():
        lab_id = scalar(proof.get("lab_id", ""))
        if not lab_id.startswith("lab."):
            fail(f"{proof_id}のlab_idが不正です: {lab_id}")
        lab_path = ROOT / "labs" / lab_id.removeprefix("lab.") / "lab.yaml"
        if not lab_path.is_file():
            fail(f"{proof_id}のLabがありません: {lab_path.relative_to(ROOT)}")
        if root_value(lab_path, "target_id") not in targets:
            fail(f"{lab_path.relative_to(ROOT)}が未定義Targetを参照しています")
        if root_value(lab_path, "claim_id") != scalar(proof.get("claim_id", "")):
            fail(f"{lab_path.relative_to(ROOT)}のClaimがProof Obligationと一致しません")
        expected_id = scalar(proof.get("expected_evidence_id", ""))
        expected_evidence.add(expected_id)
        if root_value(lab_path, "evidence_id") != expected_id:
            fail(f"{lab_path.relative_to(ROOT)}のEvidence IDがProof Obligationと一致しません")

    missing_proof_evidence = expected_evidence - actual_evidence
    if missing_proof_evidence:
        fail(f"Proof ObligationのEvidenceがありません: {sorted(missing_proof_evidence)}")

    linked_evidence: set[str] = set()
    for target_id, target in targets.items():
        state = scalar(target.get("state", ""))
        linked = set(inline_list(target.get("evidence_ids", "[]")))
        linked_evidence.update(linked)
        if state == "covered" and not linked:
            fail(f"covered TargetにEvidenceがありません: {target_id}")
        missing = linked - actual_evidence
        if missing:
            fail(f"{target_id}が存在しないEvidenceを参照しています: {sorted(missing)}")
    unknown_evidence = actual_evidence - linked_evidence
    if unknown_evidence:
        fail(f"Coverage Targetへ接続されていないEvidenceがあります: {sorted(unknown_evidence)}")


def main() -> int:
    try:
        validate()
    except (OSError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print("検証済み: Authority、Coverage、Capability、Claim、Proof、Lab、Evidence Graph")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
