# Domain Failure-mode Catalog

## Triage Contract

症状は原因ではありません。診断では次の順序を維持します。

1. Version、Context、対象、Revision、時刻範囲を固定する。
2. 読取観測と変更操作を分離する。
3. 複数の反証可能な仮説を置き、最小の観測で減らす。
4. Coverage TargetとClaimのAcceptance Criteriaへ接続する。
5. Evidenceがない領域は「未確認」とし、もっともらしい根本原因を創作しない。

## Catalog

### `architecture`

- **Symptoms:** Applicationが意図しないProject／Clusterへ向く、責任者が不明、障害影響が広い。
- **Competing hypotheses:** Spec誤り、Project境界、接続構成、Control plane配置、運用手順の混同。
- **Disambiguation:** Application Spec、Project参照、Destination、所有境界を読取確認する。
- **Unsafe shortcut:** Application Lab成功だけでTopology全体を安全と判断する。
- **Evidence limit:** `application.declarative-model`はSpecとStatusを支えるが、HAやMulti-tenancyを支えない。

### `application-set`

- **Symptoms:** Application生成漏れ、重複、予期しない削除、古いGenerator結果。
- **Competing hypotheses:** Generator入力、Filter、Refresh、外部API、Template、Ownershipの問題。
- **Disambiguation:** ApplicationSet Spec、生成Application集合、Owner reference、入力Snapshotを比較する。
- **Unsafe shortcut:** 生成後Applicationが正常だからGeneratorも正常と断定する。
- **Evidence limit:** `applicationset.generator-templating`はpartialであり、合格Direct Evidenceはまだない。

### `repository-cluster`

- **Symptoms:** Revision取得失敗、Comparison error、Destination到達不能、Permission denied。
- **Competing hypotheses:** DNS／TLS、Repository Credential、Revision、Cluster Credential、RBAC、API discovery。
- **Disambiguation:** Source側とDestination側のCondition、時刻、拒否種別を別に確認する。
- **Unsafe shortcut:** Credentialを表示して確認する、接続を削除・再登録する。
- **Evidence limit:** `connection.repository-cluster-registration`はpartialであり、接続方式全体の互換性は未検証。

### `reconciliation`

- **Symptoms:** OutOfSyncが残る、Observed Revisionが進まない、同じ操作が反復する。
- **Competing hypotheses:** Refresh未完了、Source不達、Diff、Sync拒否、Health待機、Controller停止。
- **Disambiguation:** Desired／Observed Revision、Condition、Operation、Live値を時系列化する。
- **Unsafe shortcut:** 原因不明のHard refreshやSync連打。
- **Evidence limit:** 現行Claimは既知Driftと明示Sync後収束であり、Auto-sync全般は証明しない。

### `sync-diff-health`

- **Symptoms:** SyncedだがDegraded、OutOfSyncだがHealthy、Operation成功後も差分が残る。
- **Competing hypotheses:** 状態軸の混同、Ignore規則、Health条件、Mutation、Hook／Wave失敗。
- **Disambiguation:** Sync Status、Operation Result、Diff、Healthを別列で比較する。
- **Unsafe shortcut:** 一つのBadgeを全体成功のOracleにする。
- **Evidence limit:** 各Direct TargetのAcceptance Criteriaを跨いで一般化しない。

### `hook-wave`

- **Symptoms:** Resource順序が逆、後段が開始しない、Hookが残る、再実行で副作用。
- **Competing hypotheses:** Phase、Wave annotation、前段失敗、Hook delete policy、Job冪等性。
- **Disambiguation:** Resource annotation、Event、Operation result、残留Resourceを時系列照合する。
- **Unsafe shortcut:** 失敗Hookを削除して成功だけ再取得する。
- **Evidence limit:** 固定Fixtureの順序は支えるが、任意の外部副作用や再実行安全性は支えない。

### `promotion`

- **Symptoms:** Environment間でRevision不一致、監査不能なLive変更、Rollback点不明。
- **Competing hypotheses:** Git変更漏れ、承認経路、Observed Revision遅延、直接編集、Sync未実行。
- **Disambiguation:** Promotion前後Commit、差分、Observed Revision、Resource値を一記録で照合する。
- **Unsafe shortcut:** Live stateを直接変え、後でGitを合わせる。
- **Evidence limit:** Git-mediated変更を支えるが、外部CI／承認製品の正しさは支えない。

### `rbac-sso-secret`

- **Symptoms:** Login失敗、想定外許可／拒否、Repository認証失敗、Evidenceへの秘密混入。
- **Competing hypotheses:** IdP、Claim mapping、Account、RBAC policy、Project scope、Secret lifecycle。
- **Disambiguation:** 無害なIdentity Fixtureによる許可／拒否MatrixとRedaction結果を確認する。
- **Unsafe shortcut:** Admin権限付与、Token表示、実利用者で試行する。
- **Evidence limit:** 合格Direct EvidenceはSecret Canary不在だけ。`security.rbac-sso-access-boundary`はpartial。

### `high-availability`

- **Symptoms:** Replicaがあるのに停止、Queue backlog、Leader／Shard偏り、復旧時間超過。
- **Competing hypotheses:** Stateful dependency、Scheduling、Capacity、Shard、再選出、外部依存。
- **Disambiguation:** 故障単位、継続率、Queue、Latency、RTO／RPOを同一試験で測る。
- **Unsafe shortcut:** Pod数、Ready数、単一Pod停止だけでHAを保証する。
- **Evidence limit:** `availability.high-availability`はpartialで、HA／Capacityの合格Evidenceはない。

### `observability`

- **Symptoms:** Logはあるが原因不明、Metricと状態が一致しない、時系列が相関しない。
- **Competing hypotheses:** Clock、Label／Cardinality、Sampling、Retention、Redaction、Query境界。
- **Disambiguation:** Version、Component、Application、Revision、Correlation key、Query条件を固定する。
- **Unsafe shortcut:** 単一Log行、Screenshot、現在値だけで因果を断定する。
- **Evidence limit:** `observability.metrics-logs`はpartial。個別Lab CaptureだけではSLO、Trace完全性を証明しない。

### `failure-recovery`

- **Symptoms:** 依存障害を成功扱い、復旧後も再評価しない、Restore後に管理CRが欠落。
- **Competing hypotheses:** 障害対象、Controller状態、Backup範囲、Version／Digest不一致、再評価待機。
- **Disambiguation:** 注入→異常→依存復旧→再評価→正常操作の順序とBackup前後Spec集合を確認する。
- **Unsafe shortcut:** Backup未確認のRestore、共有Clusterへの障害注入、Workload復旧との混同。
- **Evidence limit:** ローカルKindの固定Failureと管理CR Restoreに限定。

### `drift`

- **Symptoms:** OutOfSync反復、差分が見えない、Sync後に値が戻る、無視規則が広すぎる。
- **Competing hypotheses:** 手動変更、Controller／Admission Mutation、Defaulting、Ignore規則、Desired Revision違い。
- **Disambiguation:** Desired Revision、Live変更Field、変更主体、Ignore集合、Sync後値を比較する。
- **Unsafe shortcut:** `ignoreDifferences`を広げて症状を消す。
- **Evidence limit:** 既知Fixture以外のMutation原因は追加観測が必要。

### `upgrade-migration`

- **Symptoms:** CRD／API不整合、CLI失敗、Application挙動変化、Rollback不能。
- **Competing hypotheses:** Version skew、Deprecated Surface、Kubernetes互換性、Extension、Data migration。
- **Disambiguation:** 移行元／先、CRD、API、CLI、Kubernetes、Extension、Backupを固定して差分試験する。
- **Unsafe shortcut:** Latestへ直接更新、Release noteだけで互換性判断、Backup未検証。
- **Evidence limit:** `migration.version-upgrade`はpartial。既存v3.5.2のEvidenceだけではVersion間Migrationを証明しない。

### `operations`

- **Symptoms:** 大量Alert、対象不明、操作が競合、Incidentが閉じない、再発条件不明。
- **Competing hypotheses:** User impact、Control plane、Source、Destination、Security、Capacity、変更競合。
- **Disambiguation:** Incident scopeを固定し、個別Topicへ分解して共通時系列へ戻す。
- **Unsafe shortcut:** 一括Sync／削除／再起動、複数Operatorの無調整変更、Command成功で終了。
- **Evidence limit:** `operations.routine-control`はpartial。個別Claim Evidenceを統合SLOやOn-call成熟度の証明にしない。

## Escalation

秘密、個人情報、未公開脆弱性、権限昇格、第三者環境、不可逆操作が関係する場合は通常のTriageを停止し、`SECURITY.md`と所有者の承認経路へ移します。AtlasのGapが原因で断定できない場合は、必要なTarget、Fixture、Oracle、Evidenceを明示して引き継ぎます。
