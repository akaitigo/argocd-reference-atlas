# Evidence Dependency Graph

`evidence/dependency-graph.json`は、Argo CD Atlasで実在する入力、実行、Evidence、Scenario Proofの推移依存を固定します。共通契約の正本は`akaitigo/reference-atlas-core`正式main／CI成功commit `072d7ca77981f51754e824d70c6d4ecd55ea67e5`です。Frontendの件数、ID、閾値は使用しません。

## Argo CD固有入力

入力nodeはApplication、AppProject／RBAC policy、Reference System manifest、Cluster Lab harness、Scenario／Skill harness、Argo CD controller、Argo CD／Kubernetes version lock、local／container／cluster profileへ分離します。各nodeの`current_digest`はRepository内のmember pathと現在のfile digestから再計算します。

Application、ApplicationSet、Project、Repository／Cluster接続、sync、drift、rollback、health、multi-cluster、RBAC／SSO、failure、recovery、compatibilityを含む24 Evidence recordと23固有raw ArtifactをGraphへ接続します。加えてReference System結果、1,000 Scenario Proof、Scenario index、原子的公開manifest、Closure Plan、Definitive Skill Eval、provenance、bounded historical Certificateを機械列挙します。

## 変更と再実行

`baseline_digest`と`current_digest`が異なる入力から到達するoutputはstale対象です。Closureには次の全条件が必要です。

- 変更観測時刻以後に開始した実run。
- `attempts: 1`かつ`result: passed`。
- 全祖先入力の現在digest binding。
- runが生成した全output IDの機械列挙。
- Runtime／Platform runのArgo CD、Kubernetes、cluster、profileを含むruntime identity。

入力、output、Graphのdigestだけを更新してもClosureしません。失敗run、stale output、再実行対象漏れ、Graph外への退避をGateで拒否します。

## ProofとClosure Plan

`evidence/scenarios/closure-plan.json`はArgo CDの100 Surface × 10 Scenarioをrisk順、同一Scenario内の安定Surface順で全件保持し、1 trancheを最大4 Surfaceに制限します。Authority人手Review済みVariant分母は現在0であるため、`approved_variant_ids`は空、`variant_denominator.status`は`pending-authority-human-review`です。件数のための仮Variantを作らず、全1,000 rowを未完のまま保持します。

Dependency GraphはScenario Proof indexのID、Surface、Target、Target Set、Scenario、Path、Source binding構造と、Closure Planのpolicy、baseline、tranche membership、全row順を構造digestへ固定します。Proof削除、Target差替え、row削除、risk順退避、tranche上限超過は再固定だけでは通りません。

## 実行

```sh
python3 scripts/evidence_dependency_graph.py generate
python3 scripts/evidence_dependency_graph.py validate
python3 scripts/test_evidence_dependency_graph.py
atlas audit . --gate evidence-dependency
```

Graph Gateは専用OracleやRuntime Evidenceの意味的正しさを代替しません。Scenario Closure、Definitive、Non-regression、Certificate Gateと併用し、全Completion条件が閉じるまで`status: incomplete`を維持します。
