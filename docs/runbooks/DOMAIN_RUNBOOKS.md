# Domain Runbooks

## 共通の開始条件

この文書は操作Commandの固定リストではなく、適切なLab／Evidenceへ到達するための運用順序です。全領域で次を先に行います。

1. 対象がArgo CD `v3.5.2`か確認する。
2. Context、Namespace、Application、Repository、Cluster、時刻範囲を読取情報から特定する。
3. `coverage.yaml`でTarget Stateを確認する。Direct Targetがない領域は調査計画までとし、実証済みRunbookと表現しない。
4. 変更依頼でなければ読取に留める。変更依頼でも、対象、影響、Rollback、明示許可を確認する。
5. Evidence要求ではClaimのAcceptance Criteria、Source／Harness／Environment Digest、Artifact Digest、Verdictを確認する。

外部、共有、本番Clusterへの障害注入、無差別Sync、削除、Restore、Credential変更、UpgradeはこのAtlasの実行範囲外です。

## ArchitectureとApplication

**Anchor:** `application.declarative-model`はcovered、`architecture.control-plane-components`はpartialです。

1. Applicationの`spec.source`、`spec.destination`、`spec.project`、`syncPolicy`を別の責任境界として列挙する。
2. Desired stateの宣言とControllerによる収束を分け、後者は`reconciliation.continuous-loop`へRouteする。
3. Repository、Destination Cluster、Project、Secret、Recoveryの信頼境界を図または表で示す。
4. 方式選択では[Architecture ADR](../adrs/DOMAIN_DECISIONS.md#architectureとapplication)を読み、単一／複数Control planeの優劣をEvidenceなしに断定しない。
5. 実証が必要ならApplication Labを選び、正規化済みSpecとStatusを入力Manifestと比較する。

**停止:** HA、Shard、Scale、Multi-tenancyの結論が必要だが対応Target／Evidenceがない場合。

## ApplicationSet

**Anchor:** `applicationset.generator-templating`はpartial。`application.declarative-model`と`recovery.control-plane-restore`は隣接です。

1. 問いをGenerator入力、生成Application、Refresh、Ownership、削除、Recoveryのどれかへ分解する。
2. 生成されたApplicationの宣言境界だけはApplication Targetへ接続し、Generator挙動をそのEvidenceで証明しない。
3. RestoreではBackup対象にApplicationSet CRが含まれるか、生成結果とController再評価を混同していないか確認する。
4. Matrix、SCM、Pull Request等のGenerator固有挙動には、固定入力、失敗Fixture、生成集合Oracleを持つ新Targetが必要と記録する。

**停止:** Generatorが外部API、実Credential、第三者Repositoryを必要とする場合。現行Atlasで実行しない。

## Repository／Cluster接続

**Anchor:** `connection.repository-cluster-registration`はpartial。`application.declarative-model`、`failure.degraded-dependency`、`security.secret-boundary`が隣接します。

1. Source到達性、認証、Revision解決と、Destination Cluster到達性、認可、Discoveryを別々に確認する。
2. Application StatusのConditionを観測し、接続失敗をSync／Healthの成功・失敗へ短絡しない。
3. Credential値は表示せず、Secret名、参照先、更新時刻、拒否結果だけを扱う。
4. 依存劣化の再現はローカルKindのFailure Labだけを使用する。
5. 接続追加、Credential Rotation、Cluster登録は変更操作として別承認を要求する。

**停止:** 接続先の所有者、許可範囲、Credential出所が不明な場合。

## Reconciliation

**Anchor:** `reconciliation.continuous-loop`。

1. Desired Revision、Live値、Observed Revision、Refresh／Sync操作の時系列を揃える。
2. Auto-syncの有無を確認し、現行Claimが「明示Sync後の収束」を扱うことと区別する。
3. Drift導入前、検出後、Sync後を同一HarnessでCaptureする。
4. 再試行やRefreshを手動で繰り返す前に、依存劣化、Diff、Healthのどこで停止しているか切り分ける。
5. 収束判定はResource値とApplication Sync Statusの両方を使う。

**停止:** 無制限の再試行、原因不明のHard refresh、共有Clusterへの変更が必要になった場合。

## Sync／Diff／Health

**Anchor:** `sync.order-and-policy`、`diff.desired-live-comparison`、`health.resource-assessment`。

1. 問いをOperation結果、Desired/Live差分、Resource状態評価に分ける。
2. `Synced`、`OutOfSync`と`Healthy`、`Degraded`、`Progressing`を別列で記録する。
3. Diffでは既知変更集合と`ignoreDifferences`対象集合を明示する。
4. SyncではPolicy、Option、Phase／Wave、Operation結果を記録する。
5. HealthではFixtureのReady条件とApplication集約状態を比較する。

**停止:** `Synced`だけで健全性を、`Healthy`だけでDesired一致を結論付けようとする場合。

## Hook／Wave

**Anchor:** `sync.order-and-policy`。

1. Hook Phase、Wave annotation、Resource kind/nameを表にして期待順序を固定する。
2. 正常系と前段失敗系を別実行にし、後段が成功扱いされないことを確認する。
3. Hookの削除Policyや再実行副作用は現行Claimの範囲かを確認し、範囲外ならGapとする。
4. Operation result、Event、annotationを時系列で照合する。
5. Cleanupで残留Hook Resourceを確認する。

**停止:** JobやHookが外部Systemへ副作用を持つ、または冪等性が確認できない場合。

## Promotion

**Anchor:** `promotion.git-mediated-change`。

1. Promotion前Revision、変更内容、承認者、Promotion後RevisionをGit側の記録として固定する。
2. Argo CDのObserved RevisionとResource値をPromotion後Revisionへ照合する。
3. Promotion操作とSync操作を別イベントとして記録する。
4. Rollbackは前Revisionへの新しい監査可能な変更として設計し、Live state直接編集で代用しない。
5. 内蔵Promotion APIの存在を前提にしない。

**停止:** Source Revisionが未固定、変更主体が不明、承認境界やRollback点がない場合。

## RBAC／SSO／Secret

**Anchor:** Secretの`security.secret-boundary`はcovered、`security.rbac-sso-access-boundary`はpartialです。

1. Identity Provider、SSO Claim、Argo CD Account、RBAC Role、Project、Cluster権限を別層に分ける。
2. 読取確認ではPolicy名、Subject、Scope、拒否結果を扱い、TokenやClient Secretを取得しない。
3. Secretは生成、保管、復号、注入、Log／Evidence除去の責任者を記録する。
4. RBAC／SSOの許可・拒否Matrixは固定Identity Fixtureと否定系Evidenceが揃うまで実証済みとしない。
5. Security Labは既知Canary値の不在を検査し、値自体を保存しない。

**停止:** 実Identityでの権限試行、権限昇格、Credential表示、第三者IdP変更が必要な場合。

## HA

**Anchor:** `availability.high-availability`はpartial。Failure／Recoveryは隣接です。

1. 可用性目標、故障単位、Replica、Stateful dependency、Shard、Pod disruption、Capacityを明示する。
2. 単一Component停止のLab結果をHA構成全体のFailover保証へ拡張しない。
3. RTO／RPO、Queue backlog、再選出、再収束を測るTargetとBenchmarkがあるか確認する。
4. HA Manifestの存在ではなく、故障注入中の継続性と回復時間をEvidenceに要求する。

**停止:** 本番相当保証を求められたがCapacity／Failover Evidenceがない場合。Mastery Gapとして返す。

## Observability

**Anchor:** `observability.metrics-logs`はpartial。Reconciliation、Health、FailureのCaptureが隣接します。

1. 依頼をUser outcome、Application state、Controller queue、Repository dependency、Kubernetes eventのどこに属するか分ける。
2. 時刻、Version、Component、Application、Revision、Correlation keyを揃える。
3. Metric、Log、Traceのいずれが事実、傾向、因果のどこまで支えるか区別する。
4. SLI／SLO、Retention、Cardinality、Redactionは現行Coverage外として扱う。
5. 変更前後を比較できる同一Query／Capture条件をEvidenceに残す。

**停止:** Logに秘密や個人情報が含まれる、時刻同期がなく相関不能、単一Snapshotしかない場合。

## Failure／Recovery

**Anchor:** `failure.degraded-dependency`、`recovery.control-plane-restore`。

1. 障害注入、異常観測、依存復旧、再評価、正常操作の順序を固定する。
2. Backup Artifact、Version、対象CR集合、DigestをRestore前に確認する。
3. Workload復旧とArgo CD管理状態のRestoreを別のOutcomeとして扱う。
4. Restore後は正規化済みSpec集合、Application Status、Resource状態を確認する。
5. Cleanupと残留影響を記録する。

**停止:** BackupのDigest／Version不一致、外部Cluster、不可逆な削除、Rollback不能な操作。

## Drift

**Anchor:** `diff.desired-live-comparison`、`reconciliation.continuous-loop`。

1. Desired Revisionを固定し、Live変更Fieldと変更主体を記録する。
2. 無視対象外のDriftと`ignoreDifferences`対象Fieldを分ける。
3. OutOfSync検出を確認してから、許可された場合だけSyncによる収束を行う。
4. ControllerやMutating admissionによる差分は、既知Fixtureなしに原因断定しない。
5. Driftを隠すための広い無視規則を追加せず、最小Fieldで反証する。

**停止:** 変更主体不明、Desired Revision未固定、無視規則がSecurity／Policy Fieldを覆う場合。

## Upgrade／Migration

**Anchor:** `migration.version-upgrade`はpartial。Recovery、Application、Promotionが隣接します。

1. 現在Version、移行元／先Version、Kubernetes Version、CRD、CLI/API、Extensionを固定する。
2. Release noteとCompatibility資料を新しいAuthority Lockへ追加する計画を作る。
3. Backup、Preflight、段階的変更、Verification、Rollback条件を定義する。
4. 既存v3.5.2 Evidenceを移行先互換性の証明に再利用しない。
5. 新Version環境の正／負／Recovery Evidenceが揃うまで保証要求を拒否する。

**停止:** 移行先未固定、Deprecated Surface未棚卸し、Backup未検証、Rollback期限なしの場合。

## Operations

**Anchor:** `operations.routine-control`はpartial。症状に応じて他Targetへ分解します。

1. Incidentか定常作業か、読取か変更か、対象と時間制約を確認する。
2. `sync-diff-health`、`observability`、`failure-recovery`、`security`へ分解する。
3. 仮説、確認Query、観測、判断、実行、検証、引継ぎを時系列で記録する。
4. 大量操作は対象集合、Concurrency、停止閾値、Rollbackを確認する。
5. 完了条件をUser outcomeとEvidenceで定義し、Command成功だけで閉じない。

**停止:** 対象集合が曖昧、権限不明、SLO／Impact未評価、監査記録を残せない場合。
