# Mastery Closureと明示的除外

`mastery.yaml`はArgo CDという対象分野を増やすものではなく、既存Coverageを「理解、選択、構築、検証、運用、診断、進化、委任」のOutcomeと14 Surfaceから利用できるか判定する契約です。

## この実装で接続済み

- 8 Outcomeと14 Surfaceを8 Target Setへ接続
- Application、ApplicationSet、Connection、Reconciliation、Sync、Hook／Wave、Diff、Health、Promotion、Secret、RBAC／OIDC、HA、Observability、Drift、Self-heal、Failure、Recovery、Upgrade、Operationsの実行Labと合格Evidence
- Authority Lock、Capability／Claim／Proof Graph、1 Router Skill、19件の静的Eval Corpus、8件の独立forward Eval
- Apache-2.0、NOTICE、第三者Manifest、決定論的SPDX SBOM、DCO／Security方針

## 固定Epochで一般保証しない範囲

- Performance／Capacity／CostのBenchmarkと回帰基準
- 対応Kubernetes Version、Source generator、CLI／APIのCompatibility Evidence
- v3.3、v3.4系の追加patch、複数Kubernetes Versionを横断するUpgrade／Rollback実行Matrix
- 分散Trace、Incident rehearsal、Capacityを統合した運用Evidence
- 実Identity Providerとの対話Login、MFA、Group claim変化を含むSSO E2E
- Node／host／network partitionを含むHA試験とRTO／RPO Benchmark
- 公開GitHub上でのRelease、署名Tag、外部配布物、人手による権利・商標・Security Review

上記のうち技術的な非保証範囲は、理由と再評価日を持つ6件の`excluded` Coverage Targetとして固定しています。21件の実証Target、Core v1 Claim／Evidence Graph、Required Profile、Skill Eval、Provenance、ローカルCompletion Certificateの全Gateを通した固定Epochだけを`complete`とします。GitHub公開、Release作成、署名Tagはこの作業では行いません。
