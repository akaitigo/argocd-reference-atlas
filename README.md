# Argo CD 技術実証アトラス

`argocd-reference-atlas`は、Argo CD **v3.5.2**の主要な挙動を、固定した一次資料、反証可能なClaim、ローカルクラスタで再実行できるLab、Digestで束縛したEvidenceとして扱うProduct Atlasです。

現在の状態は`incomplete`です。21 TargetのLab／Eval Evidenceは生成済みですが、Performance、広いCompatibility、Publication Gate、Completion Certificateが揃うまでは完成を主張しません。残差は[`docs/MASTERY_GAPS.md`](docs/MASTERY_GAPS.md)に明示します。

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

対象Version、Coverage Epoch、明示的除外は[`atlas.yaml`](atlas.yaml)に、採用した公式一次資料とContent Digestは[`sources.lock.yaml`](sources.lock.yaml)に固定しています。GitOps一般、外部Secret製品、CI製品、公開Cloud上の障害注入は対象外です。

## 正本

```text
sources.lock.yaml
  -> mastery.yaml
  -> coverage.yaml
  -> atlas/capabilities/index.yaml
  -> atlas/claims/index.yaml
  -> atlas/proof-obligations/index.yaml
  -> labs/
  -> evidence/
```

- 共通Identityと完成条件: `atlas.yaml`
- Authority Lock: `sources.lock.yaml`
- 8 Outcome／14 Surface: `mastery.yaml`
- 有限のCoverage: `coverage.yaml`
- Agent Router Package: `skill.package.yaml`
- Product固有Graph: `atlas/`
- Core v1移行対応: `migrations/core-v1.yaml`

利用者向け文書は日本語を正本とし、Schema Key、ID、Path、API名、Argo CDの正式名称は英語表記を維持します。

## 検証

共通5 Manifestは`reference-atlas-core`の固定commit `d5c0a6c`に含まれる`atlas validate`で検証し、Repository全体は`atlas audit`で横断監査します。

```sh
atlas validate atlas.yaml mastery.yaml sources.lock.yaml coverage.yaml skill.package.yaml
atlas audit .
```

Labはローカルの専用Kindクラスタだけを対象にします。各Labは`setup`、`execute`、`verify`、`cleanup`を持ち、EvidenceがSource、Harness、EnvironmentのDigestへ束縛されるまでCoverage Targetは`covered`になりません。

実行結果と非保証範囲は[`docs/EXECUTION_REPORT.md`](docs/EXECUTION_REPORT.md)を参照してください。

## 公開状態

Repository URLは共通Schema上の正式な公開予定地を表しますが、この作業ではGitHub Repositoryの作成、Push、Releaseを行いません。権利、秘密、第三者素材、SBOM、Skill Evalを含む全Gate通過後にのみ公開可能性を判断します。
