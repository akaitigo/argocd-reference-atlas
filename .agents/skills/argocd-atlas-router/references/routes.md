# RouteとCapability Index

このReferenceは、依頼のMode、Mastery Outcome／Surface、Coverage Targetを選ぶときだけ読みます。Outcome／Surfaceは`mastery.yaml`、Targetの実際の状態、Claim ID、Evidence IDは`coverage.yaml`を正本として再確認します。

領域の入口と直接Target／隣接Target／Gapは[Router Index](../../../../docs/ROUTER_INDEX.md)を使います。選択後に必要な文書だけを開きます。

- 操作手順と停止条件: [Domain Runbooks](../../../../docs/runbooks/DOMAIN_RUNBOOKS.md)
- 設計選択と棄却理由: [Domain Decisions](../../../../docs/adrs/DOMAIN_DECISIONS.md)
- 症状、反証、危険な早合点: [Failure-mode Catalog](../../../../docs/failure-modes/DOMAIN_FAILURE_MODES.md)
- Evidenceの強さと限界: [Evidence Interpretation Guide](../../../../docs/evidence/INTERPRETATION_GUIDE.md)

| Mode | 主なOutcome | 主なSurface |
|---|---|---|
| design | understand, choose | orientation-scope, architecture-design, decision-comparison, security-privacy-safety |
| implementation | build, verify | implementation-construction, testing-verification |
| diagnosis | troubleshoot, operate | operations-observability, failure-recovery |
| recovery | troubleshoot, operate | failure-recovery, operations-observability |
| migration | evolve | compatibility-integration, migration-evolution-deprecation |
| review | verify, delegate | testing-verification, provenance-rights, agent-skill |

性能、互換性、移行、運用などRequired Surfaceの成果物がCoverageに不足する場合は、近いTargetで代用せずMastery Gapとして返します。

## design

- `application.declarative-model`: Applicationを宣言的な管理単位として設計する。
- `architecture.control-plane-components`: API Server、Repository Server、Application Controllerの責任境界を設計する。
- `applicationset.generator-templating`: Generator入力と生成Application集合の境界を設計する。
- `connection.repository-cluster-registration`: RepositoryとDestination Clusterの接続境界を分離する。
- `reconciliation.continuous-loop`: 継続的Reconciliationの責任境界と収束条件を設計する。
- `promotion.git-mediated-change`: Gitを介した環境間Promotionと承認境界を設計する。
- `security.secret-boundary`: Repository、Argo CD、Cluster間のSecret境界を設計する。
- `security.rbac-sso-access-boundary`: Identity、RBAC、Credential accessを分離する。
- `security.external-idp-interactive-sso`: 実IdP login、session、MFA、group lifecycleのmissing Gapへ案内する。
- `availability.high-availability`: Component冗長化、Shard、Stateful dependencyを比較する。
- `performance.capacity-cost-baseline`: Application／Repository／Cluster／Shard規模とCost基準のmissing Gapへ案内する。
- `availability.host-network-rto-rpo`: Host／Node／Network faultと測定RTO/RPOのmissing Gapへ案内する。

出力では、候補、選択理由、前提、禁止境界、検証に使うLabを分けます。

## implementation

- `application.declarative-model`: Application ManifestとSource/Destinationの不変条件を実装する。
- `applicationset.generator-templating`: 固定Generator入力とTemplateからApplication集合を構成する。
- `connection.repository-cluster-registration`: Repository／Cluster登録の許可・拒否境界を構成する。
- `sync.order-and-policy`: Sync Policy、Wave/Hook、順序、失敗時の停止条件を実装する。
- `sync.hook-wave-lifecycle`: Hook Phase、削除Policy、Wave Lifecycleを構成する。
- `promotion.git-mediated-change`: Environment差分をGit上の変更として実装する。
- `security.secret-boundary`: 実Credentialを記録せずSecret参照境界を実装する。
- `recovery.automated-resynchronization`: Automated sync、prune、selfHeal、retryの明示Policyを構成する。

利用可能なLabの`setup`から`cleanup`までを一つのHarnessとして扱い、途中のコマンドだけを成功証拠にしません。

## diagnosis

- `diff.desired-live-comparison`: DesiredとLiveの差、差分正規化、無視規則を確認する。
- `drift.tracking-and-refresh`: Resource tracking、Refresh抑制、Diffを区別する。
- `health.resource-assessment`: Resource HealthとApplication集約状態を確認する。
- `failure.degraded-dependency`: Repository、API、Controller等の依存劣化を再現し観測する。
- `reconciliation.continuous-loop`: 再試行、収束、停止状態を確認する。
- `observability.metrics-logs`: Metric、Log、Application状態を同じContextへ相関する。
- `operations.routine-control`: 読取、変更、停止、完了条件を持つ運用手順へ分解する。

最初に観測、次に反証可能な原因候補、最後に最小の確認操作を示します。単一のLog断片だけで根本原因を断定しません。

## recovery

- `failure.degraded-dependency`: 障害注入条件と期待する劣化状態を確認する。
- `recovery.control-plane-restore`: Control Plane復旧、再同期、復旧後不変条件を確認する。
- `recovery.automated-resynchronization`: 自動再同期Policyの作動条件と停止条件を確認する。
- `health.resource-assessment`: 復旧後のHealthと収束を確認する。

Runbookの前提、停止条件、Rollback、復旧判定、残留影響を示します。ローカル専用Kind Cluster以外を対象にしません。

## migration

- `promotion.git-mediated-change`: Gitに記録する段階的変更とRollback点を確認する。
- `application.declarative-model`: Manifest契約の変更範囲を確認する。
- `migration.version-upgrade`: 移行元／先Version、Preflight、Backup、Verification、Rollbackを確認する。
- `migration.multi-version-rollback-matrix`: 複数Versionの実Rollback／Restore Matrixがmissingであることを返す。
- `compatibility.broad-version-generator-matrix`: Argo CD／Kubernetes／Generator／Extension互換Matrixがmissingであることを返す。

`v3.5.2`外の移行先を既知の互換対象とせず、該当VersionのAuthority LockとCompatibility Evidenceが必要だと明示します。

## review

次の接続を検査します。

```text
Coverage Target -> Claim -> Source Lock
                -> Lab/Runbook -> Evidence
                -> Source/Harness/Environment Digest

Mastery Outcome/Surface -> Coverage Target Set -> Coverage Target
```

- `covered`にClaimとEvidenceがあるか。
- ClaimのVersionとAuthorityが固定されているか。
- Labがsetup/execute/verify/cleanupを持ち、再実行可能か。
- 成功、拒否、障害、復旧のObservable Outcomeが区別されているか。
- Secret、権限、公開の境界を越えていないか。
- `status: complete`をGate通過前に宣言していないか。
- `skill.router-evaluation`が独立Agentの採点Evidenceへ接続されているか。
- `observability.distributed-trace-incident-capacity`がOTLP、Incident rehearsal、SLO、Retention、Cardinality、RedactionのArtifact Evidenceを持つか。

## Route不能

GitOps一般、別製品、未固定のArgo CD Version、Coverageに存在しない機能は既存Targetへ無理に割り当てません。利用者の質問へ一般的に答えられる場合でも、Atlasに根拠がないことを明示し、必要なCoverage Target、Claim、LabまたはEvidenceをGapとして提案します。

## 複合・曖昧な依頼

- 「遅い」「壊れた」「安全にして」のように対象が定まらない場合は、Application、Controller、Repository、Cluster、Identity、Version、時刻範囲を読取情報から絞ります。変更を先行しません。
- 複数領域を含む場合は、設計・診断・変更・証拠要求を分解し、それぞれのMode、権限、Target／Gapを示します。
- Evidence要求では、Screenshotや単一Logを結論にせず、ClaimのAcceptance CriteriaとDigestで束縛されたEvidenceを求めます。
- 大量Sync、削除、Credential更新、障害注入、Restore、Upgradeは、対象、影響、Rollback、明示許可が揃うまで実行しません。
