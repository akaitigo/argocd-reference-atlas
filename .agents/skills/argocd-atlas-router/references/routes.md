# RouteとCapability Index

このReferenceは、依頼のMode、Mastery Outcome／Surface、Coverage Targetを選ぶときだけ読みます。Outcome／Surfaceは`mastery.yaml`、Targetの実際の状態、Claim ID、Evidence IDは`coverage.yaml`を正本として再確認します。

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
- `reconciliation.continuous-loop`: 継続的Reconciliationの責任境界と収束条件を設計する。
- `promotion.git-mediated-change`: Gitを介した環境間Promotionと承認境界を設計する。
- `security.secret-boundary`: Repository、Argo CD、Cluster間のSecret境界を設計する。

出力では、候補、選択理由、前提、禁止境界、検証に使うLabを分けます。

## implementation

- `application.declarative-model`: Application ManifestとSource/Destinationの不変条件を実装する。
- `sync.order-and-policy`: Sync Policy、Wave/Hook、順序、失敗時の停止条件を実装する。
- `promotion.git-mediated-change`: Environment差分をGit上の変更として実装する。
- `security.secret-boundary`: 実Credentialを記録せずSecret参照境界を実装する。

利用可能なLabの`setup`から`cleanup`までを一つのHarnessとして扱い、途中のコマンドだけを成功証拠にしません。

## diagnosis

- `diff.desired-live-comparison`: DesiredとLiveの差、差分正規化、無視規則を確認する。
- `health.resource-assessment`: Resource HealthとApplication集約状態を確認する。
- `failure.degraded-dependency`: Repository、API、Controller等の依存劣化を再現し観測する。
- `reconciliation.continuous-loop`: 再試行、収束、停止状態を確認する。

最初に観測、次に反証可能な原因候補、最後に最小の確認操作を示します。単一のLog断片だけで根本原因を断定しません。

## recovery

- `failure.degraded-dependency`: 障害注入条件と期待する劣化状態を確認する。
- `recovery.control-plane-restore`: Control Plane復旧、再同期、復旧後不変条件を確認する。
- `health.resource-assessment`: 復旧後のHealthと収束を確認する。

Runbookの前提、停止条件、Rollback、復旧判定、残留影響を示します。ローカル専用Kind Cluster以外を対象にしません。

## migration

- `promotion.git-mediated-change`: Gitに記録する段階的変更とRollback点を確認する。
- `application.declarative-model`: Manifest契約の変更範囲を確認する。
- Coverageに互換性／Version固有Targetが追加されている場合だけ、そのTargetを利用する。

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

## Route不能

GitOps一般、別製品、未固定のArgo CD Version、Coverageに存在しない機能は既存Targetへ無理に割り当てません。利用者の質問へ一般的に答えられる場合でも、Atlasに根拠がないことを明示し、必要なCoverage Target、Claim、LabまたはEvidenceをGapとして提案します。
