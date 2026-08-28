# Domain Decision Records

## 共通Decision Contract

各記録はAtlasが回答を組み立てる際の証拠境界を決めます。利用環境のArchitectureを一律に決めるものではありません。選択肢の採否は、対象環境の制約とDirect Evidenceを確認してから決定します。

### ArchitectureとApplication

- **Status:** accepted
- **Decision:** Applicationの宣言境界、Reconciliation、Security、Recoveryを別の責任として比較する。
- **Reason:** `application.declarative-model`だけではControl plane TopologyやMulti-tenancyを証明できない。
- **Consequence:** Application SpecのEvidenceをArchitecture全体の推奨根拠へ拡張しない。Topology比較にはFailure、Capacity、Security Evidenceを追加する。

### ApplicationSet

- **Status:** partial
- **Decision:** ApplicationSetをApplicationの単なる複数形としてRouteしない。
- **Reason:** Generator入力、生成集合、Refresh、Ownership、削除はApplication単体とは異なるFailure modelを持つ。
- **Consequence:** `applicationset.generator-templating`のClaim／Labだけでは完了せず、合格Evidenceが揃うまでGenerator方式を実証済みとしない。

### Repository／Cluster接続

- **Status:** partial
- **Decision:** Source接続とDestination接続を独立した信頼境界として扱う。
- **Reason:** 認証、到達性、Revision解決、Cluster認可、Discoveryの失敗は同じ症状に集約され得る。
- **Consequence:** `connection.repository-cluster-registration`がcoveredになるまでは、Application ConditionだけでCredential不良やCluster権限を断定せず、Secret値を観測資料にしない。

### Reconciliation

- **Status:** accepted with scope
- **Decision:** 検出、Refresh、Sync、収束を別イベントとして記録する。
- **Reason:** 現行Claimは既知Driftを検出し、明示したSync操作後に収束する範囲を証明する。
- **Consequence:** Auto-sync、Retry policy、Scale時の収束時間は追加Evidenceなしに一般化しない。

### Sync／Diff／Health

- **Status:** accepted
- **Decision:** Sync Status、Operation Result、Diff、Healthを独立した状態軸として扱う。
- **Reason:** 各軸の入力とOracleが異なり、一つの成功が他の成功を意味しない。
- **Consequence:** 運用画面、Runbook、Evidenceでは3軸を別列にする。

### Hook／Wave

- **Status:** accepted with scope
- **Decision:** Hook PhaseとWaveを固定Fixtureの順序制約として検証する。
- **Reason:** `sync.order-and-policy`は前段失敗時の停止を含む反証可能な順序Claimを持つ。
- **Consequence:** 外部副作用、再実行冪等性、削除PolicyはFixtureごとに追加検証する。

### Promotion

- **Status:** accepted
- **Decision:** PromotionをGit上の監査可能なDesired state変更として扱う。
- **Reason:** Argo CDは変更後RevisionをReconcileするが、現行Coverageは汎用の環境間Promotion APIを証明しない。
- **Consequence:** 承認、段階化、Rollbackは外部Workflowの責任として明示する。

### RBAC／SSO／Secret

- **Status:** partial
- **Decision:** Identity、Authentication、Authorization、Secret lifecycleを一つの「認証設定」にまとめない。
- **Reason:** 現行Direct EvidenceはRepository／EvidenceへのSecret平文不在だけであり、RBAC／SSOの許可・拒否を証明しない。
- **Consequence:** Role／Claim mapping／IdP統合はGap。否定系を含むIdentity Fixtureが揃うまで推奨方式を固定しない。

### HA

- **Status:** partial
- **Decision:** HAをReplica数やManifest形状ではなく、定義した故障下の継続性、RTO／RPO、容量で評価する。
- **Reason:** Failure／Recoveryの単一LabはHA Topologyの可用性保証ではない。
- **Consequence:** `availability.high-availability`がpartialの間は保証せず、Replica、Shard、Stateful dependency、Queue、Failoverを測るEvidenceが必要。

### Observability

- **Status:** partial
- **Decision:** Metric、Log、Trace、Kubernetes Eventを、同じCorrelation Contextへ束縛して解釈する。
- **Reason:** 単一LogやSnapshotは状態を示せても因果やSLOを証明しない。
- **Consequence:** `observability.metrics-logs`の合格Evidenceを要求し、Trace、Retention、Cardinality、SLI/SLOは追加Coverageとして扱う。

### Failure／Recovery

- **Status:** accepted with local-only scope
- **Decision:** Failure、Dependency restore、Controller reevaluation、Backup/Restore、Workload recoveryを別段階にする。
- **Reason:** 異常を成功扱いしないClaimと、管理CRを再構成するClaimは別のOracleを持つ。
- **Consequence:** ローカルKind外へ障害注入を拡張せず、Backup DigestとVersion不一致では停止する。

### Drift

- **Status:** accepted with scope
- **Decision:** DriftをDesired Revision、Live変更集合、Ignore集合、収束操作の組で表す。
- **Reason:** `ignoreDifferences`は指定Fieldだけに作用し、広い無視規則は未検出Riskを増やす。
- **Consequence:** 変更主体を推測せず、無視対象外／対象内の否定系Fixtureを維持する。

### Upgrade／Migration

- **Status:** partial
- **Decision:** v3.5.2の実行Evidenceを別VersionのCompatibility保証へ流用しない。
- **Reason:** CRD、API、CLI、Kubernetes、Extension、Deprecated SurfaceはVersionごとに変化し得る。
- **Consequence:** `migration.version-upgrade`がcoveredになるには、移行元／先を固定したAuthority Lock、Preflight、Backup、Migration、Rollback Evidenceが必要。

### Operations

- **Status:** partial
- **Decision:** 運用依頼を状態観測、診断、変更、検証、引継ぎへ分解し、個別TargetへRouteする。
- **Reason:** 9つのLabは個別Claimを証明するが、SLO、On-call、Capacity、大量操作を統合した運用保証ではない。
- **Consequence:** Command成功では閉じず、User outcome、停止条件、残留影響、Evidenceを記録する。

## Decision Review

Decisionを更新するときは、対象Version、Coverage Epoch、関連Target、反証Evidence、Security境界、Rollback可能性を同時に確認します。Gapを`accepted`へ変えるには、文書の追加ではなく、Coverage Target、Claim、Lab、Evidenceの接続が必要です。
