#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Router Skillと意味的Eval Corpusの静的契約を検証する。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "router-cases.json"
SKILL_PATH = ROOT / ".agents" / "skills" / "argocd-atlas-router" / "SKILL.md"
ROUTES_PATH = SKILL_PATH.parent / "references" / "routes.md"
OPENAI_PATH = SKILL_PATH.parent / "agents" / "openai.yaml"
COVERAGE_PATH = ROOT / "coverage.yaml"

REQUIRED_MODES = {"design", "implementation", "diagnosis", "recovery", "migration", "review"}
KNOWN_TARGETS = {
    "application.declarative-model",
    "reconciliation.continuous-loop",
    "sync.order-and-policy",
    "diff.desired-live-comparison",
    "health.resource-assessment",
    "promotion.git-mediated-change",
    "security.secret-boundary",
    "failure.degraded-dependency",
    "recovery.control-plane-restore",
}
PERMISSIONS = {"read-only", "local-kind-write", "denied"}
CASE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TARGET_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{path.relative_to(ROOT)}をJSONとして読めません: {error}")


def coverage_target_ids(path: Path) -> set[str]:
    """Core Schemaに従うcoverage.yamlのtargets配下からIDだけを抽出する。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"coverage.yamlを読めません: {error}")

    in_targets = False
    result: set[str] = set()
    for line in lines:
        if re.fullmatch(r"targets:\s*", line):
            in_targets = True
            continue
        if not in_targets:
            continue
        match = re.fullmatch(r"\s+-\s+id:\s*['\"]?([a-z0-9.-]+)['\"]?\s*", line)
        if match:
            result.add(match.group(1))
    return result


def validate_skill() -> None:
    for path in (SKILL_PATH, ROUTES_PATH, OPENAI_PATH):
        if not path.is_file():
            fail(f"必須Skill Artifactがありません: {path.relative_to(ROOT)}")

    skill = SKILL_PATH.read_text(encoding="utf-8")
    header = re.match(r"\A---\n(?P<header>.*?)\n---\n", skill, re.DOTALL)
    if not header:
        fail("SKILL.mdのYAML Frontmatterがありません")
    if not re.search(r"^name:\s*argocd-atlas-router\s*$", header.group("header"), re.MULTILINE):
        fail("SKILL.mdのnameはargocd-atlas-routerである必要があります")
    description = re.search(r"^description:\s*(.+)$", header.group("header"), re.MULTILINE)
    if not description or not 20 <= len(description.group(1).strip()) <= 400:
        fail("SKILL.mdのdescriptionは20〜400文字である必要があります")

    routes = ROUTES_PATH.read_text(encoding="utf-8")
    missing_targets = sorted(target for target in KNOWN_TARGETS if target not in routes)
    if missing_targets:
        fail(f"routes.mdにCapability Routeがありません: {', '.join(missing_targets)}")

    metadata = OPENAI_PATH.read_text(encoding="utf-8")
    if "$argocd-atlas-router" not in metadata:
        fail("agents/openai.yamlのdefault_promptは$argocd-atlas-routerを明示する必要があります")


def validate_cases() -> None:
    document = load_json(CASES_PATH)
    if not isinstance(document, dict):
        fail("router-cases.jsonのRootはObjectである必要があります")
    if document.get("schema_version") != 1:
        fail("router-cases.jsonのschema_versionは1である必要があります")
    if document.get("skill_id") != "argocd-atlas-router":
        fail("router-cases.jsonのskill_idがRouterと一致しません")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        fail("router-cases.jsonには1件以上のCaseが必要です")

    seen_ids: set[str] = set()
    seen_modes: set[str] = set()
    seen_targets: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            fail(f"cases[{index}]はObjectである必要があります")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
            fail(f"cases[{index}].idが不正です")
        if case_id in seen_ids:
            fail(f"Case IDが重複しています: {case_id}")
        seen_ids.add(case_id)
        mode = case.get("mode")
        if mode not in REQUIRED_MODES:
            fail(f"{case_id}のmodeが不正です: {mode}")
        seen_modes.add(mode)
        if not isinstance(case.get("prompt"), str) or len(case["prompt"].strip()) < 10:
            fail(f"{case_id}のpromptが短すぎます")

        expected = case.get("expected")
        if not isinstance(expected, dict):
            fail(f"{case_id}.expectedはObjectである必要があります")
        targets = expected.get("target_ids")
        if not isinstance(targets, list) or len(targets) != len(set(targets)):
            fail(f"{case_id}.expected.target_idsは重複のないArrayである必要があります")
        for target in targets:
            if not isinstance(target, str) or not TARGET_ID.fullmatch(target):
                fail(f"{case_id}のTarget IDが不正です: {target}")
            if target not in KNOWN_TARGETS:
                fail(f"{case_id}が契約外Targetを参照しています: {target}")
            seen_targets.add(target)
        if expected.get("requires_coverage_check") is not True:
            fail(f"{case_id}はCoverage確認を必須にする必要があります")
        if not isinstance(expected.get("requires_execution_evidence"), bool):
            fail(f"{case_id}.requires_execution_evidenceはBooleanである必要があります")
        if expected.get("permission") not in PERMISSIONS:
            fail(f"{case_id}.permissionが不正です")
        for field in ("pass_conditions", "hard_fail_conditions"):
            values = expected.get(field)
            if not isinstance(values, list) or len(values) < 2 or not all(isinstance(value, str) and len(value) >= 8 for value in values):
                fail(f"{case_id}.{field}には2件以上の意味的条件が必要です")

    missing_modes = REQUIRED_MODES - seen_modes
    if missing_modes:
        fail(f"代表Eval Modeが不足しています: {', '.join(sorted(missing_modes))}")
    missing_targets = KNOWN_TARGETS - seen_targets
    if missing_targets:
        fail(f"Evalで未参照のTargetがあります: {', '.join(sorted(missing_targets))}")

    if not COVERAGE_PATH.is_file():
        fail("coverage.yamlがないためEvalのTarget参照を検証できません")
    actual_targets = coverage_target_ids(COVERAGE_PATH)
    missing_in_coverage = KNOWN_TARGETS - actual_targets
    if missing_in_coverage:
        fail(f"coverage.yamlにEval Targetがありません: {', '.join(sorted(missing_in_coverage))}")

    special_cases = {"coverage-outside-no-fabrication", "permission-no-unrequested-fix", "security-local-only"}
    if not special_cases <= seen_ids:
        fail("捏造防止、権限制約、Security境界のEvalが不足しています")


def main() -> int:
    try:
        validate_skill()
        validate_cases()
    except ValueError as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print("検証済み: Router SkillとEval Corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
