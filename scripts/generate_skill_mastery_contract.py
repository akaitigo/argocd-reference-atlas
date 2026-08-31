#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Argo CD Router Skill用のMastery／Target契約を正本Manifestから生成する。"""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".agents" / "skills" / "argocd-atlas-router" / "references" / "mastery-contract.json"
FE_REFERENCE = {
    "repository": "frontend-behavior-atlas",
    "commit": "8a9e34a89a55cc53702032783c06ede7246a286f",
    "files": [
        {"path": ".agents/skills/fe-behavior-advisor/references/mastery-contract.json", "sha256": "f2d6ec5bc979cacaee6a8086654449b739d1b88a36134ea8c72b109baf5f376e"},
        {"path": ".agents/skills/fe-behavior-advisor/scripts/advisor-router.mjs", "sha256": "993326210fecfafa4843d9c11929cddc5bd93c2c9fac6c85a79b9dcf43120c07"},
        {"path": "scripts/lib/definitive-skill-eval.ts", "sha256": "8209f3deb47eff03a2f88822a7a2af52dd9a3a3d44b74e88e42e84e2c3d1b5b6"},
        {"path": "scripts/lib/mastery-contract.ts", "sha256": "cf939059fa698e23c97c0cb8f08ff2289d37f9abca145cb8320a59425c41e363"},
        {"path": "evals/fe-behavior-advisor.definitive-skill-eval.json", "sha256": "566c9f3cea248f49c24f769c88695b10c15bbdb956c08bcfa68dbe7e96c18d0a"},
    ],
}

TARGET_QUERIES = {
    "application.declarative-model": "ApplicationのSource Destination Sync Policyという宣言境界を確認したい",
    "reconciliation.continuous-loop": "Live drift後にApplication controllerが再評価して収束する条件を確認したい",
    "sync.order-and-policy": "Sync optionとResource適用順序と失敗停止Policyを確認したい",
    "diff.desired-live-comparison": "Desired manifestとLive resourceの差分とignore境界を確認したい",
    "health.resource-assessment": "Child resourceからApplication Healthを集約する挙動を確認したい",
    "promotion.git-mediated-change": "Gitの宣言変更を介した環境Promotionを確認したい",
    "security.secret-boundary": "Repository Cluster Evidence間でSecret平文を残さない境界を確認したい",
    "failure.degraded-dependency": "Repository依存停止時のArgo CD劣化と誤成功防止を確認したい",
    "recovery.control-plane-restore": "Application ProjectをBackupからRestoreして再構成する条件を確認したい",
    "architecture.control-plane-components": "API Server repo-server Application controllerの責任境界を確認したい",
    "applicationset.generator-templating": "ApplicationSet Generator入力とTemplate生成集合を確認したい",
    "connection.repository-cluster-registration": "Repository資格情報とCluster接続Secretの登録拒否境界を確認したい",
    "sync.hook-wave-lifecycle": "Sync Hook Phase Waveと後続停止のLifecycleを確認したい",
    "security.rbac-sso-access-boundary": "Identity Argo CD RBAC ProjectとCredential access拒否を確認したい",
    "availability.high-availability": "Argo CD component replica Redis HAと局所障害継続を確認したい",
    "observability.metrics-logs": "Controller repo-server API ServerのMetric LogをApplication状態へ相関したい",
    "drift.tracking-and-refresh": "Resource trackingとRefresh抑制と実Driftを区別したい",
    "recovery.automated-resynchronization": "Automated sync prune selfHeal retryの安全条件を確認したい",
    "migration.version-upgrade": "Argo CD v3.4.8からv3.5.2へのBackup Upgrade検証を確認したい",
    "operations.routine-control": "Refresh Sync Wait診断Backupの停止条件を確認したい",
    "skill.router-evaluation": "Router SkillのCoverage Evidence権限境界を評価したい",
    "performance.capacity-cost-baseline": "Application一万件の性能容量Cost基準を確認したい",
    "compatibility.broad-version-generator-matrix": "複数Kubernetes Versionと全ApplicationSet Generator互換を確認したい",
    "security.external-idp-interactive-sso": "実IdP login MFA Group Token lifecycleを確認したい",
    "availability.host-network-rto-rpo": "Node喪失Network partition時のRTO RPOを確認したい",
    "migration.multi-version-rollback-matrix": "複数Argo CD Version間の実Rollback Matrixを確認したい",
    "observability.distributed-trace-incident-capacity": "OTLP Trace Incident SLO Telemetry容量を確認したい",
    "operations.notifications-delivery": "Notification controllerの配信再試行回復と秘密保護を確認したい",
    "system.integrated-reference-gitops": "Repository Cluster Identity Notificationを統合したReference Systemを確認したい",
    "architecture.evidence-backed-comparison": "HA Sharding方式を同一Runtime条件のEvidenceで比較したい",
}

EXECUTION_CONTRACTS = {
    "understand": {"mode": "design", "mutation_policy": "read-only", "required_output_fields": ["target", "coverage-state", "authority", "runtime-evidence", "boundary"]},
    "choose": {"mode": "design", "mutation_policy": "read-only", "required_output_fields": ["target", "bounded-alternatives", "tradeoffs", "coverage-state", "acceptance-criteria"]},
    "build": {"mode": "implementation", "mutation_policy": "explicit-authorization-required", "required_output_fields": ["target", "authorized-change-scope", "lab", "runtime-evidence", "verification"]},
    "verify": {"mode": "review", "mutation_policy": "read-only", "required_output_fields": ["target", "oracle", "authority", "runtime-evidence", "coverage-gap"]},
    "operate": {"mode": "operations", "mutation_policy": "read-only-unless-mutation-requested", "required_output_fields": ["target", "telemetry", "runbook", "stop-condition", "recovery"]},
    "troubleshoot": {"mode": "diagnosis", "mutation_policy": "read-only", "required_output_fields": ["target", "reproduction", "failure-stage", "controller-signal", "recovery-condition"]},
    "evolve": {"mode": "migration", "mutation_policy": "explicit-authorization-required", "required_output_fields": ["target", "old-new-mapping", "compatibility", "migration-evidence", "rollback"]},
    "delegate": {"mode": "review", "mutation_policy": "explicit-authorization-required", "required_output_fields": ["target", "authorized-change-scope", "acceptance-criteria", "stop-condition", "review"]},
}


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Object YAMLではありません: {path.relative_to(ROOT)}")
    return value


def build_contract() -> dict:
    mastery = load_yaml(ROOT / "mastery.yaml")
    coverage = load_yaml(ROOT / "coverage.yaml")
    target_ids = {target["id"] for target in coverage["targets"]}
    if target_ids != set(TARGET_QUERIES):
        raise ValueError(f"Target query契約がCoverageと一致しません: missing={sorted(target_ids-set(TARGET_QUERIES))} extra={sorted(set(TARGET_QUERIES)-target_ids)}")
    if {item["id"] for item in mastery["outcomes"]} != set(EXECUTION_CONTRACTS):
        raise ValueError("Outcome execution contractがmastery.yamlと一致しません")
    return {
        "schema_version": 1,
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "reference": FE_REFERENCE,
        "generated_from": ["mastery.yaml", "coverage.yaml", "sources.lock.yaml", "claims/*.claim.yaml", "evidence/records/*.evidence.yaml"],
        "outcomes": mastery["outcomes"],
        "surfaces": mastery["surfaces"],
        "execution_contracts": EXECUTION_CONTRACTS,
        "target_routes": [
            {
                "id": target["id"],
                "title": target["title"],
                "target_set": target["target_set"],
                "state": target["state"],
                "query": TARGET_QUERIES[target["id"]],
            }
            for target in coverage["targets"]
        ],
        "coverage_policy": {
            "verified_states": ["covered"],
            "gap_states": ["partial", "missing", "planned", "expired"],
            "matrix_pass_is_completion": False,
            "no_match": "coverage-gap",
        },
        "decision_boundaries": {
            "mutation_without_authorization": "blocked",
            "authority_semantic_decision": "external-human-decision-required",
            "stale_source_relock_without_explicit_procedure": "blocked",
            "ambiguous_or_unknown_query": "coverage-gap",
        },
        "stop_conditions": [
            "coverage-gap",
            "mastery-routing-gap",
            "unverified-runtime-evidence",
            "unauthorized-mutation",
            "external-human-decision-required",
            "stale-source-relock-explicit-procedure-required",
            "source-binding-mismatch",
            "rights-or-sensitive-data-unclear",
        ],
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_contract(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Generated Argo CD Skill mastery contract: outcomes=8 surfaces=14 targets=30")


if __name__ == "__main__":
    main()
