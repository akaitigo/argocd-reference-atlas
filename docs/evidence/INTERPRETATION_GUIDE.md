# Evidence Interpretation Guide

## Evidenceを読む順序

Evidence Fileが存在することと、技術的主張が成立することは同じではありません。次を順番に確認します。

1. `claim_ids`が質問のCoverage Targetに接続されている。
2. `verdict`が`pass`であり、ClaimのAcceptance CriteriaとProof ObligationのOracleを満たす。
3. Product Versionが`v3.5.2`で、Source Lock、Harness、Environment Manifest、ArtifactのDigestが一致する。
4. 実行Profile、Fixture、時刻、前提、否定系が質問の条件と一致する。
5. ArtifactにSecret、個人情報、内部URLがなく、同梱権利が確認されている。

`fail`は反証、`inconclusive`は判定不能です。古いDigest、異なるVersion、欠落Artifactは成功根拠にしません。Screenshot、Command exit code、単一Logは補助資料であり、それだけでClaimを閉じません。

## 領域別の解釈

### `architecture`

- **Strong for:** `application.declarative-model`の正規化済みSpecとStatusが入力Manifestへ一致すること。
- **Insufficient for:** Topology、Multi-tenancy、HA、Scale、Blast radiusの優劣。
- **Corroboration needed:** Security境界、Failure、Recovery、Capacityの独立Evidence。

### `application-set`

- **Strong for:** Recovery Evidenceに含まれる固定ApplicationSet CRのBackup／Restore前後Spec比較。
- **Insufficient for:** `applicationset.generator-templating`がpartialの間のGenerator入力から生成Application集合への保証、Refresh、削除、Scale、外部API失敗。
- **Corroboration needed:** Generator別Fixture、期待集合Oracle、否定系、Ownershipの合格Evidence。

### `repository-cluster`

- **Strong for:** ApplicationのSource／Destination宣言、固定依存障害中に成功を偽装しない観測。
- **Insufficient for:** `connection.repository-cluster-registration`がpartialの間の全認証方式、TLS、Proxy、Credential Rotation、Least privilege。
- **Corroboration needed:** Source側／Destination側を分けた接続Contractと拒否Evidence。

### `reconciliation`

- **Strong for:** 既知DriftのOutOfSync検出と明示Sync後のResource値収束。
- **Insufficient for:** Auto-sync全設定、無限Retry防止、Scale時Latency、すべてのMutation源。
- **Corroboration needed:** Drift前後とSync後の同一時系列、Observed Revision、Resource値。

### `sync-diff-health`

- **Strong for:** 固定Waveの順序、既知Diff／Ignore集合、Fixture Ready条件とHealth状態。
- **Insufficient for:** ある軸の成功から他軸の成功を導くこと。任意CRDのCustom Health一般化。
- **Corroboration needed:** Sync Status、Operation Result、Diff、Healthを独立したOracleで評価する。

### `hook-wave`

- **Strong for:** 固定FixtureのWave境界と前段失敗時に後段を成功扱いしないこと。
- **Insufficient for:** 外部副作用のExactly-once、Hook Jobの冪等性、任意削除Policy。
- **Corroboration needed:** Annotation、Event、Operation result、残留Resourceの時系列。

### `promotion`

- **Strong for:** Promotion前後のGit Revision、Desired state、Observed Revision、Resource値の接続。
- **Insufficient for:** 外部承認System、CI、Policy engineの正しさや内蔵Promotion APIの存在。
- **Corroboration needed:** Gitの監査記録とArgo CD観測結果を別Artifactとして照合する。

### `rbac-sso-secret`

- **Strong for:** 既知Canary SecretがRepositoryと公開Evidenceに平文で存在しないこと。
- **Insufficient for:** 暗号学的秘匿、および`security.rbac-sso-access-boundary`がpartialの間のRBAC完全性、SSO Claim mapping、IdP可用性、Token lifecycle。
- **Corroboration needed:** 無害なIdentity Fixtureによる許可／拒否Matrix。実CredentialをEvidenceにしない。

### `high-availability`

- **Strong for:** `availability.high-availability`はpartialで合格Direct Evidenceなし。Failure／Recovery Evidenceは隣接情報だけ。
- **Insufficient for:** Replica数から可用性、RTO／RPO、Capacity、Shard公平性を推論すること。
- **Corroboration needed:** 定義した故障単位、継続率、Queue、Latency、再収束時間のBenchmark。

### `observability`

- **Strong for:** covered Targetの個別Labにある時刻付き状態遷移。`observability.metrics-logs`自体はpartial。
- **Insufficient for:** Telemetry完全性、因果、SLI/SLO、Retention、Cardinality、安全なRedaction。
- **Corroboration needed:** 同一Correlation ContextのMetric／Log／Trace／EventとQuery条件。

### `failure-recovery`

- **Strong for:** ローカルKindでの依存障害中の異常観測、復旧後再評価、固定Backupからの主要CR Spec再構成。
- **Insufficient for:** 本番RTO／RPO、Workload Data Recovery、外部Dependency、別Version Restore。
- **Corroboration needed:** 注入→異常→復旧→再評価の順序、Backup／Restore Digest、前後Spec集合。

### `drift`

- **Strong for:** 既知Live変更の検出、明示したIgnore Fieldの除外、Sync後の既知値収束。
- **Insufficient for:** 未観測の変更主体、任意Mutation Webhook、広いIgnore規則の安全性。
- **Corroboration needed:** Desired Revision、変更Field、Ignore集合、変更前後Artifact。

### `upgrade-migration`

- **Strong for:** v3.5.2内のBackup入力形状やApplication／Promotion境界のBaseline。`migration.version-upgrade`自体はpartial。
- **Insufficient for:** 別VersionとのCompatibility、CRD Migration、Deprecated Surface、Rollback成功。
- **Corroboration needed:** 移行元／先双方のAuthority Lock、Preflight、正／負／Rollback Evidence。

### `operations`

- **Strong for:** covered Targetに接続された限定的な操作Outcome。`operations.routine-control`自体はpartial。
- **Insufficient for:** 統合SLO、On-call readiness、Capacity、大量操作、安全なConcurrency。
- **Corroboration needed:** Incident scope、User impact、停止閾値、操作前後、残留影響、引継ぎ記録。

## Evidence要求への返答形式

Evidenceを求められたら、少なくとも次を分けます。

- **Supported:** Target、Claim、Acceptance Criteria、Evidence ID、Verdict、Digestが直接支える内容。
- **Not supported:** 隣接Evidenceからは導けない内容。
- **Conditions:** Version、Profile、Fixture、環境、時刻など適用条件。
- **Next proof:** 不足を閉じるTarget、Lab、Oracle、否定系、必要権限。

この形式は結論の文言を固定するものではなく、Evidenceの射程を誤って拡大しないための検査枠です。
