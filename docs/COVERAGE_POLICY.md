# Coverage方針

## 固定境界

このCoverageは次の組に対してのみ有効です。

- Atlas ID: `argocd-reference-atlas`
- Product Version: `v3.5.2`
- Coverage Epoch: `2026-08-28`
- Authority Lock: `sources.lock.yaml`のContent Digest
- Core Contract: `reference-atlas-core` v1.0.0 commit `cf9e6e2`
- Required Environment Profiles: `local`、`container`、`cluster`

上流Source、Harness、Environment、対象Versionのいずれかを変更した場合、既存Evidenceを自動継承しません。新しいEpochまたは明示した再検証を要求します。

## Authority採用規則

Argo Projectが管理するArgo CD公式Repositoryと公式文書だけを一次Authorityとして採用します。Blog、個人記事、Vendor比較記事、検索結果の要約はClaimの根拠にしません。採用Sourceはv3.5.2 tagのContentへ固定し、URL、取得日、SHA-256、再配布方針をLockへ記録します。

同じ事項について一次資料が不足する場合、推測でClaimを完成させず、Targetを`partial`または`missing`に維持します。

## Target状態

| State | 本Atlasでの意味 |
|---|---|
| `missing` | 必須Surfaceは判明しているがClaimも実装もない |
| `planned` | ClaimまたはLabの設計対象として登録済み |
| `partial` | ClaimとProof Obligationはあるが、必要な実行EvidenceまたはGateが不足 |
| `covered` | Claim、Lab、Oracle、合格Evidenceが接続され、固定環境で再実行可能 |
| `excluded` | Scope外で、理由と再評価日がある |
| `infeasible` | 現在の環境では実証不能で、理由と再評価日がある |
| `expired` | Source、Harness、EnvironmentまたはEpoch変更でEvidenceが失効 |

`covered`へ変更するには少なくとも一つのClaimと一つの合格Evidenceが必要です。Evidence fileが存在するだけでは足りず、ClaimのAcceptance CriteriaとProof ObligationのOracleを満たす必要があります。

## 必須Target

21件の実証Targetはすべて`required`かつ`covered`です。性能、広域互換、実IdP、Host／Network障害、全Version Rollback Matrix、外部Trace／Incident統合は、固定Epochの結果を過剰一般化しないため理由と再評価日を持つ`excluded` Targetとして保持します。PromotionはGitを介したDesired state変更という境界で扱い、Argo CD固有の直接Promotion機能としては扱いません。

## Evidence規則

- setup、execute、verify、cleanupを非対話的に再実行できる。
- Source、Harness、Environment manifestをSHA-256へ束縛する。
- 正常系だけでなく、各Targetに適用可能な拒否、障害、復旧を含める。
- Secret、Credential、内部URL、個人情報をArtifactへ含めない。
- Failure injectionを専用ローカルKindクラスタ外へ送らない。
- `inconclusive`または`fail`のEvidenceでTargetを`covered`にしない。

## Epoch更新

Argo CD Version、公式CRD、主要Controller動作、Security Advisory、またはCore Policyの変更時にCoverageを再評価します。旧Epochの合格EvidenceとCertificateは履歴として不変に保ち、新Epochへ暗黙にコピーしません。
