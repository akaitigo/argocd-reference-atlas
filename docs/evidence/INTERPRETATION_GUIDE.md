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

- **Strong for:** 固定List generatorからblue/green Applicationを生成し、element削除後の集合とtemplate一致を確認したbounded Evidence。Recovery EvidenceにはCRのBackup／Restore前後Spec比較もある。
- **Insufficient for:** Git／Cluster／SCM／PR／Matrix／Merge／Plugin generator、Scale、外部API失敗。
- **Corroboration needed:** Generator別Fixture、期待集合Oracle、否定系、Ownershipの合格Evidence。

### `repository-cluster`

- **Strong for:** ApplicationのSource／Destination宣言、単一local repositoryとnamespace限定cluster登録、到達不能endpoint拒否、固定依存障害中に成功を偽装しない観測。
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

- **Strong for:** 既知Canary Secret非混入、固定Identity/RBAC allow-deny、OIDC discoveryとprovider outageのbounded Evidence。
- **Insufficient for:** 暗号学的秘匿、および`security.rbac-sso-access-boundary`がpartialの間のRBAC完全性、SSO Claim mapping、IdP可用性、Token lifecycle。
- **Corroboration needed:** 無害なIdentity Fixtureによる許可／拒否Matrix。実CredentialをEvidenceにしない。

### `high-availability`

- **Strong for:** 3-node KindのHA replica、Application Controller/repo-server/Redis master Pod UID交代、Controller復旧後Drift再収束、repo-server復旧後Hard Refresh、Redis障害窓中10/10 read/metrics成功のbounded Evidence。
- **Insufficient for:** Replica数から可用性、RTO／RPO、Capacity、Shard公平性を推論すること。
- **Corroboration needed:** 定義した故障単位、継続率、Queue、Latency、再収束時間のBenchmark。

### `observability`

- **Strong for:** controller、API server、repo-serverの固定Metric/Log captureと既知Sync時刻のbounded相関。`observability.metrics-logs`自体はpartial。
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

- **Strong for:** Kind v1.34.0上のv3.4.8からv3.5.2への正方向Upgrade、主要CR spec digest、Sync/Health維持。`migration.version-upgrade`自体はpartial。
- **Insufficient for:** 別VersionとのCompatibility、CRD Migration、Deprecated Surface、Rollback成功。
- **Corroboration needed:** 移行元／先双方のAuthority Lock、Preflight、正／負／Rollback Evidence。

### `operations`

- **Strong for:** 固定Applicationのrefresh、wait、export/importという限定的な操作Outcome。`operations.routine-control`自体はpartial。
- **Insufficient for:** 統合SLO、On-call readiness、Capacity、大量操作、安全なConcurrency。
- **Corroboration needed:** Incident scope、User impact、停止閾値、操作前後、残留影響、引継ぎ記録。

## Evidence要求への返答形式

### `notifications`

- **Strong for:** Application annotation、実Notification controllerからlocal receiverへの正常配信、HTTP 503 retry、receiver回復後の配信、trigger／delivery metric、Secret値と外部送信を含まないArtifact。
- **Insufficient for:** global subscription、外部provider認証、rate limit、controller再起動時のdeduplication、全Service。
- **Corroboration needed:** 対象Scopeを拡張する場合は、同じVersionと隔離環境でcontroller log、delivery metric、receiver artifact、redaction結果を再取得する。

### `integrated-reference-system`

- **Strong for:** 10 Scenario契約、既存Cluster Evidenceのdigest再検証、100 Surface × 10 Scenarioの専用row、各rowのController／Kubernetes／Version identityとresource state／controller log／metric／trace Artifactまたは明示gap。
- **Insufficient for:** 同一Repository／Cluster topology／Attemptのcross-surface不変条件。offline統合結果をBehavior固有Proofへ流用できず、Authority atomic bindingとCompletion eligibleは0。
- **Corroboration needed:** 単一Repository／Cluster／Revision／Correlation contextで10 Scenarioを再実行した統合Artifactと、人手Authority Decisionへ束縛したAtomic behavior。

### `evidence-comparison`

- **Strong for:** 個々の方式について固定Fixtureが直接観測した結果。
- **Insufficient for:** 入力、環境、version、metric、failure oracleが異なる方式間の優劣。
- **Corroboration needed:** 同一条件の比較Matrix、raw artifact、選択条件、非保証条件。

Evidenceを求められたら、少なくとも次を分けます。

- **Supported:** Target、Claim、Acceptance Criteria、Evidence ID、Verdict、Digestが直接支える内容。
- **Not supported:** 隣接Evidenceからは導けない内容。
- **Conditions:** Version、Profile、Fixture、環境、時刻など適用条件。
- **Next proof:** 不足を閉じるTarget、Lab、Oracle、否定系、必要権限。

この形式は結論の文言を固定するものではなく、Evidenceの射程を誤って拡大しないための検査枠です。
