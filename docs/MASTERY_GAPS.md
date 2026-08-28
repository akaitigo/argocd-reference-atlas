# Definitive Mastery Gap

`mastery.yaml`はArgo CDという対象分野を増やすものではなく、既存Coverageを「理解、選択、構築、検証、運用、診断、進化、委任」のOutcomeと14 Surfaceから利用できるか判定する契約です。

## この実装で接続済み

- 8 Outcomeと14 Surfaceを8 Target Setへ接続
- Application、ApplicationSet、Connection、Reconciliation、Sync、Hook／Wave、Diff、Health、Promotion、Secret、RBAC／OIDC、HA、Observability、Drift、Self-heal、Failure、Recovery、Upgrade、Operationsの実行Labと合格Evidence
- Authority Lock、Capability／Claim／Proof Graph、1 Router Skill、19件の静的Eval Corpus、8件の独立forward Eval
- Apache-2.0、NOTICE、第三者Manifest、決定論的SPDX SBOM、DCO／Security方針

## Definitive Completionを阻止する必須Gap

- Performance／Capacity／CostのBenchmarkと回帰基準
- 対応Kubernetes Version、Source generator、CLI／APIのCompatibility Evidence
- v3.3、v3.4系の追加patch、複数Kubernetes Versionを横断するUpgrade／Rollback実行Matrix
- 分散Trace、Incident rehearsal、Capacityを統合した運用Evidence
- 実Identity Providerとの対話Login、MFA、Group claim変化を含むSSO E2E
- Node／host／network partitionを含むHA試験とRTO／RPO Benchmark
- 公開GitHub上でのRelease、署名Tag、外部配布物、人手による権利・商標・Security Review

上記はDefinitiveに重要なため`excluded`で閉じず、6件を`missing`、既存の広域12件を`partial`として再開しました。公開済みv0.1.0 Certificateは、そのSource commitにおける限定FixtureとCore v1 Gateを再現するbounded historical recordです。Core v2、細粒度Inventory、正常・拒否・障害・回復・移行・容量Evidence、統合Reference GitOps System、更新後Skill Evalを閉じるまで`atlas.yaml`は`status: incomplete`を維持します。
