#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""公開main v0.1.0の実行・証拠baselineからの後退を拒否する。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "baselines" / "public-main-v0.1.0.non-regression.json"
MIGRATION_DIR = ROOT / "evidence" / "migrations"


def load_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path.relative_to(ROOT)}")
    return value


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"objectではありません: {path.relative_to(ROOT)}")
    return value


def index(path: Path, key: str) -> dict[str, dict[str, object]]:
    values = load_yaml(path).get(key)
    if not isinstance(values, list):
        raise ValueError(f"{path.relative_to(ROOT)}の{key}がarrayではありません")
    return {str(value["id"]): value for value in values if isinstance(value, dict)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migration_allows(evidence_id: str, old_digest: str, new_digest: str) -> bool:
    for path in sorted(MIGRATION_DIR.glob("*.json")):
        value = load_json(path)
        proof = value.get("execution_proof")
        if (
            value.get("old_evidence_id") == evidence_id
            and value.get("new_evidence_id")
            and value.get("from_artifact_sha256") == old_digest
            and value.get("to_artifact_sha256") == new_digest
            and isinstance(value.get("reason"), str)
            and len(str(value["reason"]).strip()) >= 40
            and isinstance(proof, dict)
            and proof.get("verdict") == "pass"
            and proof.get("command")
            and proof.get("artifact")
            and proof.get("assertions_preserved")
        ):
            return True
    return False


CONTENT_EXCLUDED_ROOTS = {".atlas-core", ".git", ".runtime", ".cache", "vendor", "node_modules"}
CONTENT_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".sh"}


def tracked_publication_paths(root: Path = ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"git tracked Pathが不正です: {relative}")
        if relative.suffix in CONTENT_TEXT_SUFFIXES and not any(part in CONTENT_EXCLUDED_ROOTS for part in relative.parts):
            paths.append(root / relative)
    return paths


def validate_content_policy(root: Path = ROOT, publication_paths=None) -> None:
    banned = ("世界" + "一", "決定" + "版", "akaitigo" + "氏", "作者を" + "称賛", "唯" + "一")
    paths = tracked_publication_paths(root) if publication_paths is None else publication_paths
    for path in paths:
        relative = path.relative_to(root)
        if any(part in CONTENT_EXCLUDED_ROOTS for part in relative.parts):
            continue
        if not path.is_file() or path.suffix not in CONTENT_TEXT_SUFFIXES:
            raise ValueError(f"Publication対象のtracked text fileを読めません: {relative}")
        text = path.read_text(encoding="utf-8", errors="ignore")
        for phrase in banned:
            if phrase in text:
                raise ValueError(f"中立性Policyに反する表現があります: {relative}: {phrase}")


def validate_closure_plan_summary(root: Path = ROOT) -> None:
    plan = load_json(root / "evidence/scenarios/closure-plan.json")
    summary = plan["summary"]
    if summary["runtime_execution_completed_rows"] != summary["completed_dedicated_rows"]:
        raise ValueError("Closure Planのdeprecated completed_dedicated_rowsがruntime集計と一致しません")
    if summary["runtime_execution_remaining_rows"] != summary["remaining_rows"]:
        raise ValueError("Closure Planのdeprecated remaining_rowsがruntime集計と一致しません")
    if summary["completion_closed_rows"] != 0 or summary["completion_remaining_rows"] != 1000:
        raise ValueError("Closure Planのcompletion集計が非後退baselineと一致しません")
    if summary["completion_eligible_rows"] != 0:
        raise ValueError("Closure Planのcompletion eligible rowsが不正です")
    deprecated = summary["deprecated_fields"]
    if deprecated["completed_dedicated_rows"] != {
        "status": "deprecated-exact-derivation",
        "replacement": "runtime_execution_completed_rows",
        "value": 13,
    }:
        raise ValueError("Closure Planのcompleted_dedicated_rows migrationが不正です")
    if deprecated["remaining_rows"] != {
        "status": "deprecated-exact-derivation",
        "replacement": "runtime_execution_remaining_rows",
        "value": 987,
        "not_completion_remaining_rows": True,
    }:
        raise ValueError("Closure Planのremaining_rows migrationが不正です")


def main() -> None:
    baseline = load_json(BASELINE_PATH)
    targets = index(ROOT / "coverage.yaml", "targets")
    claims = index(ROOT / "atlas" / "claims" / "index.yaml", "claims")
    proofs = index(ROOT / "atlas" / "proof-obligations" / "index.yaml", "proof_obligations")
    sources = index(ROOT / "sources.lock.yaml", "sources")

    for target_id in baseline["target_ids"]:
        target = targets.get(target_id)
        if target is None:
            raise ValueError(f"baseline Targetが削除されました: {target_id}")
        if target.get("requirement") != "required":
            raise ValueError(f"baseline Targetのrequiredが格下げされました: {target_id}")
        if target.get("state") in {"excluded", "infeasible"}:
            raise ValueError(f"baseline TargetがScope外へ退避されました: {target_id}")

    if missing := set(baseline["claim_ids"]) - set(claims):
        raise ValueError(f"baseline Claimが削除されました: {sorted(missing)}")
    if missing := set(baseline["proof_ids"]) - set(proofs):
        raise ValueError(f"baseline Proofが削除されました: {sorted(missing)}")
    if missing := set(baseline["source_ids"]) - set(sources):
        raise ValueError(f"baseline Sourceが削除されました: {sorted(missing)}")

    for claim_id in baseline["claim_ids"]:
        path = ROOT / "claims" / f"{claim_id}.claim.yaml"
        if not path.is_file() or load_yaml(path).get("status") != "accepted":
            raise ValueError(f"baseline Claim artifactが削除または無効化されました: {claim_id}")

    labs = {str(load_yaml(path)["id"]): load_yaml(path) for path in (ROOT / "labs").glob("*/lab.yaml")}
    for lab_id in baseline["lab_ids"]:
        lab = labs.get(lab_id)
        if lab is None:
            raise ValueError(f"baseline Labが削除されました: {lab_id}")
        phases = lab.get("phases")
        if not isinstance(phases, dict) or set(phases) != {"setup", "execute", "verify", "cleanup"}:
            raise ValueError(f"baseline Labの4 phaseが縮小されました: {lab_id}")
        commands = " ".join(str(value).lower() for value in phases.values())
        if any(marker in commands for marker in ("--dry-run", " mock", " static")):
            raise ValueError(f"baseline Labがmock/staticへ置換されました: {lab_id}")
        environment = str(lab.get("environment", ""))
        if lab_id != "skill-eval" and not environment.startswith("kind-argocd-atlas"):
            raise ValueError(f"baseline Kubernetes Labの実cluster環境が縮小されました: {lab_id}")

    current_evidence = {
        str(load_yaml(path)["id"]): load_yaml(path)
        for path in (ROOT / "evidence" / "records").glob("*.evidence.yaml")
    }
    for artifact in baseline["evidence_artifacts"]:
        evidence_id = str(artifact["id"])
        if evidence_id not in current_evidence:
            raise ValueError(f"baseline Evidence recordが削除されました: {evidence_id}")
        uri = str(artifact["uri"])
        path = ROOT / uri
        if not path.is_file():
            raise ValueError(f"baseline Evidence artifactが削除されました: {uri}")
        actual = sha256(path)
        expected = str(artifact["sha256"])
        if actual != expected and not migration_allows(evidence_id, expected, actual):
            raise ValueError(f"Evidence置換にMapping/Proof/理由がありません: {evidence_id} {expected}->{actual}")

    router = load_json(ROOT / "evals" / "router-cases.json")
    router_cases = {str(case["id"]): case for case in router["cases"]}
    minimums = baseline["router_case_minimums"]
    for case_id in baseline["router_case_ids"]:
        case = router_cases.get(case_id)
        if case is None:
            raise ValueError(f"baseline Router Evalが削除されました: {case_id}")
        expected = case.get("expected", {})
        for key in ("pass_conditions", "hard_fail_conditions"):
            if len(expected.get(key, [])) < int(minimums[key]):
                raise ValueError(f"baseline Router Eval assertionが縮小されました: {case_id}/{key}")

    forward = load_json(ROOT / "evals" / "forward-cases.json")
    forward_ids = {str(case["id"]) for case in forward["cases"]}
    if missing := set(baseline["forward_case_ids"]) - forward_ids:
        raise ValueError(f"baseline forward Evalが削除されました: {sorted(missing)}")

    skill_package = load_yaml(ROOT / "skill.package.yaml")
    threshold = float(skill_package["evals"]["minimum_pass_rate"])
    if threshold < float(baseline["minimum_pass_rate"]):
        raise ValueError(f"Skill Eval閾値が縮小されました: {threshold}")

    workflow = (ROOT / ".github" / "workflows" / "atlas-validate.yml").read_text(encoding="utf-8")
    for step in baseline["ci_step_names"]:
        if f"- name: {step}" not in workflow:
            raise ValueError(f"baseline CI stepが削除されました: {step}")

    lock_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "environments" / "kind").glob("*.lock"))
    for version in baseline["runtime_floor"]["argocd_versions"] + baseline["runtime_floor"]["kubernetes_versions"]:
        if version not in lock_text and version != "v1.34.0":
            raise ValueError(f"baseline Versionがlockから削除されました: {version}")
    if "kindest/node:v1.34.0" not in (ROOT / "scripts" / "extended" / "isolation.sh").read_text(encoding="utf-8"):
        raise ValueError("baseline Kubernetes v1.34.0実行経路が削除されました")

    validate_closure_plan_summary()
    validate_content_policy()
    print(
        "non-regression baseline validated: "
        f"targets={len(baseline['target_ids'])} labs={len(baseline['lab_ids'])} "
        f"claims={len(baseline['claim_ids'])} proofs={len(baseline['proof_ids'])} "
        f"evidence={len(baseline['evidence_artifacts'])} sources={len(baseline['source_ids'])}"
    )


if __name__ == "__main__":
    main()
