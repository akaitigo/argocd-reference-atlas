# Reference SystemとScenario Proof

`integrations/reference-system/manifest.yaml`は、normal、boundary、rejection、failure、recovery、migration、operations、security、performance、compatibilityの10 Scenarioを固定します。`scripts/generate_scenario_proofs.py`は既存の実Kind／Argo CD Evidence recordとraw Artifactをdigest再検証し、10 Scenarioを一回のoffline integration auditとして評価します。

生成ReporterはFE `7175de4305afb308722d5b83475e91c18da64957`の原子的Evidence保持契約を適用します。既存`evidence/`を同一filesystem上の`.evidence-next`へ複製し、今回生成するReference結果、index、1,000 Proofをすべてstaging内で完成させます。Artifact集合、各size／digest、generation digest、意味内容のfull-run検証がpassした場合だけ、現行treeを`.evidence-previous`へ退避してdirectory renameで公開します。公開側renameが失敗した場合は退避treeを元へrenameしてrollbackします。失敗run、部分生成、または新旧Artifact混在は現行成功Evidenceを変更しません。

この実行は過去のCluster Labを同じScenario契約へ統合する検証であり、同一Repository、同一Cluster topology、同一Attemptで10 Scenarioを再実行した証拠ではありません。`attempts: 1`はこのoffline監査の回数、`runtime_attempts: 0`は統合Runtime未実行を表します。したがって`evidence/reference-system/results.json`の`integrated_runtime_passed`は0で、`single_topology_execution`もfalseです。10行を評価した事実と、統合Reference GitOps Systemが未完成である事実を分離します。

## Behavior固有Proof

`evidence/scenarios/index.json`は、現行`definitive/surface-inventory.yaml`の100 itemと10 Scenarioの直積1,000行を分母として固定します。各`evidence/scenarios/behaviors/<behavior-id>/<scenario>.proof.json`は次を保持します。

- Argo CD component、Kubernetes behavior、Argo CD version、Kubernetes runtime identity。
- 固定Source digestと未昇格Authority locator。
- Behaviorへ直接接続されたEvidence recordとraw Artifact digest。
- resource state、controller log、metric、traceそれぞれのArtifact JSON pointer、または専用の明示gap。
- 同じScenarioの統合Audit結果。ただしBehavior固有Evidenceとしては算入しない。
- `definitive/scenario-variant-contract.yaml`のVariant分母と、専用Runtime Closure全条件。

現行itemはAuthority raw anchorから人手Decisionで昇格したAtomic behaviorではなく、exhaustiveなVariant分母も未承認です。全行は`scenario-gap-open`、`authority_atomic_binding: false`、`completion_eligible: false`です。既存Labとの接続は20件の`supporting-runtime-artifact`、156件の`supporting-artifact`、824件の`no-supporting-artifact`として保持しますが、いずれもScenario gap Closureへ算入しません。

Gapを閉じられるのは、`evidence/scenarios/runtime/index.yaml`へ登録した専用reportがSurfaceとScenarioに完全一致し、承認済みの全Variantを実Argo CD on Kubernetesで駆動し、次の全条件を満たす場合だけです。

- retry 0、全Variantがfirst-attempt pass。
- 反証可能なOracleとAssertion。
- 実ファイルから再計算できるSource／Harness digest。
- Argo CD／Kubernetes version、Cluster／Topology、対象Controllerを含むRuntime identity。
- Variantごとに所有pathが異なるresource state、controller log、metric、trace Artifact。

統合Reference結果、既存Lab bundle、別Surface／Scenario／VariantのArtifact metadata、mock／static結果は代用できません。現行registryは専用report 0件であるため、Closureは0/1,000です。

専用reportは`id`、`surface_id`、`scenario`、`execution.retries`、Argo CD／Kubernetes／Cluster／Topology／Controllerを識別する`runtime_identity`を持ちます。`variants`は承認済みVariant集合と完全一致し、各recordがAttempt、結果、Oracle、所有者付きSource／Harness binding、4 Artifact bindingを保持します。Artifact pathは`evidence/scenarios/runtime/artifacts/<report-id>/<variant-id>/<channel>`配下に限定し、ownerを`<report-id>:<variant-id>:<channel>`として固定します。Channelごとのkindは`kubernetes-resource-state`、`argocd-controller-log`、`argocd-prometheus-metric`、`scenario-execution-trace`です。同じpathを別recordまたは別Channelへ再利用すると生成器が拒否します。

## 再生成と検証

```sh
make scenario-proofs
make scenario-proofs-validate
```

Validatorは1,000ファイルの集合、10 Scenario、補助Artifact digest、専用Runtime registry、Variant分母、Closure全16条件、統合／別Artifact metadataの非流用、Authority／Completionの0固定をofflineで照合します。`evidence/scenarios/atomic-publish-manifest.json`は今回生成した1,002 Artifactの集合とdigestを固定します。negative contract testはClosure条件に加え、失敗runによる直前成功Evidence消去、部分上書き、新旧generation混在、swap失敗時のrollbackを失敗注入で拒否します。
