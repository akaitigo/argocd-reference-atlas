# Argo CD Domain Router Index

## 使い方

このIndexは、Argo CD v3.5.2に関する依頼を、Atlasが実証したTargetと未検証のMastery Gapへ振り分けます。実際の`state`、Claim ID、Evidence IDは毎回`coverage.yaml`で確認してください。

分類は次の意味です。

- **direct**: 領域を直接扱うCoverage Targetがある。`covered`なら接続されたClaimとEvidenceの範囲だけを実証済みとして使える。
- **adjacent**: 関連するTargetはあるが、領域全体を証明しない。設計や原因候補の入口にだけ使う。
- **gap**: 現行Coverageに直接Targetがない。一般知識で補完せず、必要なClaim、Lab、Evidenceを不足として返す。

## 領域Map

| Topic ID | 領域 | 主なMode | Direct Target | Adjacent Target | Mastery Surface | 現行境界 |
|---|---|---|---|---|---|---|
| `architecture` | ArchitectureとApplication | design, review | `application.declarative-model`, `architecture.control-plane-components` | `reconciliation.continuous-loop`, `security.secret-boundary`, `recovery.control-plane-restore` | `architecture-design`, `decision-comparison` | Applicationはcovered。Component境界はpartial |
| `application-set` | ApplicationSet | design, implementation, recovery | `applicationset.generator-templating` | `application.declarative-model`, `recovery.control-plane-restore` | `implementation-construction`, `compatibility-integration` | Generator／Template Targetはpartial。Restore時のCR以外のScaleは未証明 |
| `repository-cluster` | Repository／Cluster接続 | design, diagnosis | `connection.repository-cluster-registration` | `application.declarative-model`, `failure.degraded-dependency`, `security.secret-boundary` | `architecture-design`, `security-privacy-safety` | 接続登録Targetはpartial。全認証方式の互換性は未証明 |
| `reconciliation` | Reconciliation | design, diagnosis | `reconciliation.continuous-loop` | `diff.desired-live-comparison`, `health.resource-assessment` | `foundations-mechanics`, `operations-observability` | 既知Driftの検出と明示Sync後の収束が実証範囲 |
| `sync-diff-health` | Sync／Diff／Health | implementation, diagnosis | `sync.order-and-policy`, `diff.desired-live-comparison`, `health.resource-assessment` | `reconciliation.continuous-loop` | `foundations-mechanics`, `testing-verification` | 3状態を同義に扱わない |
| `hook-wave` | Hook／Wave | implementation, diagnosis | `sync.order-and-policy`, `sync.hook-wave-lifecycle` | `health.resource-assessment` | `implementation-construction`, `failure-recovery` | 固定Wave順序はcovered。Hook Lifecycle Targetはpartial |
| `promotion` | Promotion | design, implementation | `promotion.git-mediated-change` | `application.declarative-model`, `sync.order-and-policy` | `decision-comparison`, `operations-observability` | Git変更の追跡を対象とし、Argo CD内蔵Promotion APIとは扱わない |
| `rbac-sso-secret` | RBAC／SSO／Secret | design, review | `security.secret-boundary`, `security.rbac-sso-access-boundary` | `application.declarative-model` | `security-privacy-safety`, `compatibility-integration` | Secret平文不在はcovered。RBAC／SSO Targetはpartial |
| `high-availability` | HA | design, review | `availability.high-availability` | `failure.degraded-dependency`, `recovery.control-plane-restore` | `architecture-design`, `performance-capacity-cost` | Component冗長化Targetはpartial。Capacityと本番RTO/RPOは未証明 |
| `observability` | Metric／Log／Trace | diagnosis, review | `observability.metrics-logs` | `reconciliation.continuous-loop`, `health.resource-assessment`, `failure.degraded-dependency` | `operations-observability`, `performance-capacity-cost` | Metric／Log相関Targetはpartial。Trace、SLO、Retentionは未証明 |
| `failure-recovery` | Failure／Recovery | diagnosis, recovery | `failure.degraded-dependency`, `recovery.control-plane-restore`, `recovery.automated-resynchronization` | `health.resource-assessment`, `reconciliation.continuous-loop` | `failure-recovery`, `operations-observability` | Repository障害と自動再同期はpartial。固定CR Restoreだけcovered |
| `drift` | Drift | diagnosis, implementation | `diff.desired-live-comparison`, `reconciliation.continuous-loop`, `drift.tracking-and-refresh` | `sync.order-and-policy` | `foundations-mechanics`, `testing-verification` | 既知Diff／収束はcovered。Tracking／Refresh Targetはpartial |
| `upgrade-migration` | Upgrade／Migration | migration, recovery | `migration.version-upgrade` | `recovery.control-plane-restore`, `application.declarative-model`, `promotion.git-mediated-change` | `migration-evolution-deprecation`, `compatibility-integration` | v3.4.8→v3.5.2 Targetはpartial。他VersionはCoverage外 |
| `operations` | Operations | diagnosis, recovery, review | `operations.routine-control` | 全Targetを状況別に利用 | `operations-observability`, `failure-recovery`, `security-privacy-safety` | 境界付き運用Targetはpartial。SLO、On-call、Capacityは未証明 |
| `performance-capacity` | Performance／Capacity／Cost | design, review | `performance.capacity-cost-baseline` | `availability.high-availability`, `observability.metrics-logs` | `performance-capacity-cost` | required missing。近いHA Evidenceで代用しない |
| `compatibility-matrix` | Version／Kubernetes／Generator互換 | migration, review | `compatibility.broad-version-generator-matrix` | `applicationset.generator-templating`, `migration.version-upgrade` | `compatibility-integration` | required missing。単一Version/List generatorだけでは閉じない |
| `external-idp-sso` | 実IdP SSO | design, implementation, review | `security.external-idp-interactive-sso` | `security.rbac-sso-access-boundary` | `security-privacy-safety`, `compatibility-integration` | required missing。OIDC discovery Fixtureはbounded Evidence |
| `host-network-rto-rpo` | Host／Network障害とRTO/RPO | diagnosis, recovery, review | `availability.host-network-rto-rpo` | `availability.high-availability`, `recovery.control-plane-restore` | `failure-recovery`, `performance-capacity-cost` | required missing。Pod/Redis leader削除で代用しない |
| `rollback-matrix` | 複数Version Rollback | migration, recovery | `migration.multi-version-rollback-matrix` | `migration.version-upgrade`, `recovery.control-plane-restore` | `migration-evolution-deprecation`, `compatibility-integration` | required missing。正方向Upgradeと同一Version Restoreで代用しない |
| `trace-incident-capacity` | Trace／Incident／Telemetry容量 | diagnosis, review | `observability.distributed-trace-incident-capacity` | `observability.metrics-logs` | `operations-observability`, `performance-capacity-cost` | required missing。Metric/Log captureだけでは閉じない |

## 文書Route

1. 判断条件を比較するなら[Domain Decisions](adrs/DOMAIN_DECISIONS.md)。
2. 読取確認、変更前提、停止条件を選ぶなら[Domain Runbooks](runbooks/DOMAIN_RUNBOOKS.md)。
3. 症状から反証可能な仮説へ分けるなら[Failure-mode Catalog](failure-modes/DOMAIN_FAILURE_MODES.md)。
4. Evidenceから言えることと言えないことを評価するなら[Evidence Interpretation Guide](evidence/INTERPRETATION_GUIDE.md)。

文書に操作例があっても、それ自体は実行許可でも実証Evidenceでもありません。実行には対象と権限を確認し、実在するLabとOracleを使います。
