---
name: argocd-atlas-router
description: Argo CD v3.5.2のArchitecture、ApplicationSet、接続、同期、Security、HA、Observability、障害復旧、移行、運用に関する設計・実装・診断・レビューを、AtlasのCoverage、Claim、Runbook、ADR、Failure mode、Evidenceへ案内する。Coverage外の機能説明には使わない。
---

# Argo CD Atlas Router

Argo CD v3.5.2について判断するとき、このSkillをAtlasの入口として使います。Atlasの内容を記憶や一般論で補完せず、Repository内の機械可読な記録へ戻って回答します。

## 先に守る境界

- 対象Releaseは`v3.5.2`です。別Versionの挙動はこのAtlasで実証済みと扱いません。
- `coverage.yaml`のTargetが`covered`である場合だけ、そこに列挙された`claim_ids`と`evidence_ids`を実証済み根拠として使います。`partial`、`planned`、`missing`、`expired`は不足を明示します。
- `excluded`または`infeasible`は、`exclusion`の理由と見直し日を伝えます。Coverage外の機能、互換性、安全性を捏造しません。
- 技術的主張のAuthorityは`atlas/claims/`、一次資料は`sources.lock.yaml`、観測結果は`evidence/`です。外部記事を優先しません。
- Lab実行と環境変更は、利用者が変更を依頼し対象を許可した場合だけ行います。診断やレビューの依頼から実装、公開、外部Cluster操作へ拡張しません。
- Security／Failure／Recovery LabはRepositoryが管理するローカル専用Kind Clusterだけを対象にします。Credential、内部URL、個人情報を出力やEvidenceへ保存しません。
- `atlas.yaml`が`status: incomplete`である間は、Atlas全体を完成済みと表現しません。
- `mastery.yaml`の8 Outcomeと14 Surfaceから依頼の目的を確認し、必要なSurfaceに成果物がなければMastery Gapとして返します。

## Route

依頼を次のModeへ分類し、[routes.md](references/routes.md)から該当ModeとCapabilityだけを読みます。

- **design**: 境界、責任分担、Reconciliation、Promotion、Secret設計を比較する。
- **implementation**: 再現可能な構築・同期手順を選び、Labの`setup`、`execute`、`verify`、`cleanup`を使う。
- **diagnosis**: Desired/Live差分、Health、同期失敗を観測し、原因候補をEvidenceで狭める。
- **recovery**: 障害状態、復旧条件、復旧後の不変条件をRunbookとRecovery Evidenceで確認する。
- **migration**: Versionや構成変更の前提、互換性、Promotion手順、Rollback条件を確認する。
- **review**: Coverage、Claim、Manifest、Lab、EvidenceのTraceabilityと権限境界を検査する。

複数Modeにまたがる場合も、一度に必要なReferenceだけを開き、回答内でModeを区別します。

Modeを選んだ後、依頼の領域を[Router Index](../../../docs/ROUTER_INDEX.md)で特定します。設計判断ならADR、手順ならRunbook、異常の切り分けならFailure-mode Catalog、証拠の評価ならEvidence Interpretationだけを追加で読みます。直接Targetがない領域は、隣接Targetを根拠の代用にせず、Router IndexのGap分類を維持します。

## 根拠を辿る手順

1. `mastery.yaml`で依頼のOutcomeとSurfaceを特定し、接続先Target Setを確認します。
2. `coverage.yaml`で対象Targetを特定し、`state`と`requirement`を確認します。
3. そのTargetに接続されたClaimだけを`atlas/claims/`から読み、対応するSource IDを`sources.lock.yaml`で確認します。
4. 実行や障害対応が必要なら、Router Indexから`docs/runbooks/`または`docs/failure-modes/`を選び、その文書が指すTarget、Lab、停止条件を確認します。実行Labが存在しなければ手順を創作せず、Gapとして返します。
5. Claimが参照するEvidenceを`evidence/`で確認し、`source_digest`、`harness_digest`、Environment Manifest Digest、`verdict`を保持したまま使います。
6. 推奨を述べるときは、Outcome、Surface、Target ID、Coverage State、Claim ID、Evidence ID、適用Version、未検証点を示します。

`rg`が使える環境では、まず次のようにIDを正確に検索します。

```sh
rg -n 'application\.declarative-model|<target-or-claim-id>' coverage.yaml atlas/claims labs docs/runbooks evidence
```

## 停止条件

- 対象Targetがない、またはCoverageとClaim／Evidenceの参照が一致しない場合は、確認できた事実と不足Artifactを分けて返します。
- `verdict: fail`または`inconclusive`のEvidenceを成功根拠にしません。
- 実行対象、権限、破壊的影響が不明な変更は実行せず、必要な許可を求めます。
- GitHubへの公開、Push、Releaseは明示的な別承認なしに行いません。

## 回答の最低要素

簡潔な回答でも、選択したMode、Target IDとCoverage State、根拠となるClaim／Evidence、次の安全な操作または不足点を含めます。一般的知識を補足する場合は「Atlas外の参考情報」と明示し、実証済みClaimと混同しません。
