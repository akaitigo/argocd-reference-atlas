# Argo CD 技術実証アトラス

`argocd-reference-atlas`は、Argo CD **v3.5.2**の主要な挙動を、固定した一次資料、反証可能なClaim、ローカルクラスタで再実行できるLab、Digestで束縛したEvidenceとして扱うProduct Atlasです。

現在のDefinitive状態は`incomplete`です。公開済みv0.1.0のCompletion Certificateは、2026-08-28時点の限定FixtureとCore v1 Gateだけを証明するbounded historical recordとして保持します。Performance、広域互換、実IdP、Host／Network障害、Rollback Matrix、Trace／Incident、Notifications、統合Reference System、Evidence比較を必須Gapとして追跡します。詳細は[`docs/MASTERY_GAPS.md`](docs/MASTERY_GAPS.md)に示します。

## 対象

- Applicationの宣言モデル
- Reconciliationと収束
- Syncの順序とPolicy
- Desired／Live Diff
- Resource Health評価
- Git変更を介したPromotion
- Secret管理責任の境界
- 依存障害時の安全な劣化
- Control Plane状態のRecovery
- Control Plane ArchitectureとApplicationSet
- Repository／Cluster connection
- Hook／Wave lifecycle
- RBAC／OIDC／Secret access boundary
- HA component冗長性とRedis leader再選出
- Metric／LogによるObservability
- Drift trackingとAutomated self-heal
- v3.4.8からv3.5.2へのUpgrade／Migration
- bounded OperationsとRouter Skill Eval
- Notification Trigger／Template／Subscription／Delivery
- Performance／Capacity、Version互換、実Rollbackの未Closure Matrix
- 統合Reference GitOps Systemと同一条件のEvidence比較

対象Version、Coverage Epoch、未Closure Targetは[`atlas.yaml`](atlas.yaml)と[`coverage.yaml`](coverage.yaml)に、採用した公式一次資料とContent Digestは[`sources.lock.yaml`](sources.lock.yaml)に固定しています。GitOps一般と外部製品は境界を明示しつつ、Argo CD本体のDefinitiveに必要な面を除外で閉じません。

## 正本

```text
sources.lock.yaml
  -> mastery.yaml
  -> coverage.yaml
  -> definitive/surface-inventory.yaml
  -> authority/extraction.snapshot.json
  -> authority/body-inventory.snapshot.json
  -> authority/review-queue.snapshot.json
  -> authority/reviews/decisions.json
  -> definitive/gap-ledger.yaml
  -> definitive/argocd-depth-parity.json
  -> definitive/fe-parity-matrix.json
  -> integrations/reference-system/manifest.yaml
  -> evidence/reference-system/results.json
  -> evidence/scenarios/index.json
  -> evals/argocd-atlas-router.definitive-skill-eval.json
  -> evals/argocd-atlas-router.definitive-forward-eval.json
  -> atlas/capabilities/index.yaml
  -> atlas/claims/index.yaml
  -> atlas/proof-obligations/index.yaml
  -> labs/
  -> evidence/
```

- 共通Identityと完成条件: `atlas.yaml`
- Authority Lock: `sources.lock.yaml`
- Authority locator監査: `authority/extraction.snapshot.json`
- Authority raw anchor母集団と非後退baseline: `authority/body-inventory.snapshot.json`、`baselines/authority-body-inventory-v1.json`
- Authority人手Review QueueとDecision ledger: `authority/review-queue.snapshot.json`、`authority/reviews/decisions.json`
- 8 Outcome／14 Surface: `mastery.yaml`
- 有限のCoverage: `coverage.yaml`
- Agent Router Package: `skill.package.yaml`
- 8 Outcome × 14 Surface Router契約と独立Forward Eval: `evals/argocd-atlas-router.definitive-skill-eval.json`、`evals/argocd-atlas-router.definitive-forward-eval.json`
- Product固有Graph: `atlas/`
- Core v1移行対応: `migrations/core-v1.yaml`
- Definitive Surface／Scenario Gap: `definitive/`
- FE Depth Reference 18軸監査: `definitive/argocd-depth-parity.json`
- 10 Scenario統合Audit、1,000件のBehavior固有Proof、全Variant専用Runtime Closure契約: `integrations/reference-system/manifest.yaml`、`definitive/scenario-variant-contract.yaml`、`evidence/reference-system/results.json`、`evidence/scenarios/index.json`

利用者向け文書は日本語を正本とし、Schema Key、ID、Path、API名、Argo CDの正式名称は英語表記を維持します。

## 検証

共通5 Manifestは`reference-atlas-core` v1.0.0の固定commit `cf9e6e2`に含まれる`atlas validate`で検証し、Repository全体は`atlas audit`で横断監査します。

```sh
atlas validate atlas.yaml mastery.yaml sources.lock.yaml coverage.yaml skill.package.yaml
atlas audit .
```

Labはローカルの専用Kindクラスタだけを対象にします。各Labは`setup`、`execute`、`verify`、`cleanup`を持ち、EvidenceがSource、Harness、EnvironmentのDigestへ束縛されるまでCoverage Targetは`covered`になりません。

実行結果と非保証範囲は[`docs/EXECUTION_REPORT.md`](docs/EXECUTION_REPORT.md)を参照してください。

## 公開状態

RepositoryはGitHubで公開済みですが、`main`のv0.1.0 CertificateをDefinitive完成の根拠にはしません。このfeature branchでCore v2 Gateと実行Evidenceを閉じるまで、新しいCompletion CertificateやDefinitive Releaseを発行しません。
