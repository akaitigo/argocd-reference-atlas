# Argo CD 技術実証アトラス Architecture

## 目的と境界

本AtlasはArgo CD v3.5.2を単一のProduct Versionとして固定し、30件のrequired Targetと100件の細粒度Surfaceを仕様Graphにします。現状は8件`covered`、13件`partial`、9件`missing`です。100 Surfaceは暫定母集団であり、Authority本文からの抽出が閉じるまで有限性を主張しません。Definitiveに重要な面を除外で閉じず、`2026-08-28`のCoverage Epochと`sources.lock.yaml`のAuthority Corpusに限定して未Closureを追跡します。

共通Contractは`reference-atlas-core` v1.0.0 commit `cf9e6e2`です。共通Schemaを製品固有Fieldで拡張せず、Argo CD固有情報は`atlas/`、`labs/`、`evidence/`に保持します。`mastery.yaml`は分野を増やさず、既存Coverageを8 Outcomeと14 Surfaceから辿る上位契約です。

## Canonical Graph

```text
Argo Project公式Source（v3.5.2 tag）
  -> Mastery Outcome / Surface
  -> Coverage Target
  -> Definitive Surface / Gap Scenario
  -> Capability
  -> Claim
  -> Proof Obligation
  -> local Kind Lab / Oracle
  -> Evidence
  -> Router Skill Eval
  -> Completion Certificate
```

各Nodeは安定した英語IDで接続します。利用者向けTitle、説明、判断基準は日本語です。Source、Harness、EnvironmentのいずれかのDigestが変わったEvidenceは、新しい実行で更新するまで現行Claimの証明に利用しません。

## 層の責任

| 層 | 正本 | 責任 |
|---|---|---|
| Identity | `atlas.yaml` | ID、Version境界、言語、Status、完成Profile |
| Authority | `sources.lock.yaml` | 公式一次資料のURL、Version、取得日、Digest |
| Mastery | `mastery.yaml` | 8 Outcome、14 Surface、Audience、既存Target Setへの接続 |
| Coverage | `coverage.yaml` | 有限Target、必須度、状態、Claim／Evidence接続 |
| Definitive inventory | `definitive/` | 公式Surface、bounded Evidence binding、未実行Scenario |
| Domain Graph | `atlas/` | Capability、反証可能なClaim、Proof Obligation |
| Execution | `labs/` | setup、execute、verify、cleanup、隔離 |
| Proof | `evidence/` | 実行環境とArtifactのDigest、Verdict |
| Agent routing | `.agents/skills/`, `evals/` | 問いを正本・Labへ案内し、Coverage gapを返す |

## Product Overlay

### ApplicationとReconciliation

Application CRDのDesired stateとControllerの観測結果を分離します。宣言が存在することと、Resourceが収束したことを別Claimとして証明します。

### Sync、Diff、Health

Sync操作、Diff判定、Health評価は相関しますが同一ではありません。Labはそれぞれ独立したOracleを持ち、`Synced`を`Healthy`の代用にしません。Diff customizationは明示したFieldだけに限定し、隠れた差分を一般に無視できるとは主張しません。

### Promotion

本AtlasでのPromotionはGit上の環境宣言を変更するWorkflowです。Argo CDは変更されたRevisionをReconcileします。Argo CD v3.5.2に環境間Promotionを直接実行する汎用APIがあるとは主張しません。

### Secret boundary

Secretの生成・保管・復号責任をArgo CDの外に置きます。Repository、Command log、EvidenceへCanary Secretの平文が出現しないことを検査し、値そのものを証拠として保存しません。

### FailureとRecovery

障害注入は一時的なローカルKindクラスタ内に限定します。Failure Labは異常を成功扱いしないことと復旧後の再評価を、Recovery LabはBackup／Restore前後の正規化した管理Resourceを検証します。実在の第三者環境や公開Cloudは対象にしません。

## 完成状態

`status: complete`は、Authority、Coverage、Mastery、Claim、Execution、Operational、Skill、Publicationの8 Closureを通過し、生成済みCompletion CertificateがRelease入力をDigest固定した場合だけ維持します。いずれかのDigestまたは必須Gateが崩れた場合は`incomplete`へ戻します。
