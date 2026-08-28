# Reference SystemとScenario Proof

`integrations/reference-system/manifest.yaml`は、normal、boundary、rejection、failure、recovery、migration、operations、security、performance、compatibilityの10 Scenarioを固定します。`scripts/generate_scenario_proofs.py`は既存の実Kind／Argo CD Evidence recordとraw Artifactをdigest再検証し、10 Scenarioを一回のoffline integration auditとして評価します。

この実行は過去のCluster Labを同じScenario契約へ統合する検証であり、同一Repository、同一Cluster topology、同一Attemptで10 Scenarioを再実行した証拠ではありません。`attempts: 1`はこのoffline監査の回数、`runtime_attempts: 0`は統合Runtime未実行を表します。したがって`evidence/reference-system/results.json`の`integrated_runtime_passed`は0で、`single_topology_execution`もfalseです。10行を評価した事実と、統合Reference GitOps Systemが未完成である事実を分離します。

## Behavior固有Proof

`evidence/scenarios/index.json`は、現行`definitive/surface-inventory.yaml`の100 itemと10 Scenarioの直積1,000行を分母として固定します。各`evidence/scenarios/behaviors/<behavior-id>/<scenario>.proof.json`は次を保持します。

- Argo CD component、Kubernetes behavior、Argo CD version、Kubernetes runtime identity。
- 固定Source digestと未昇格Authority locator。
- Behaviorへ直接接続されたEvidence recordとraw Artifact digest。
- resource state、controller log、metric、traceそれぞれのArtifact JSON pointer、または専用の明示gap。
- 同じScenarioの統合Audit結果。ただしBehavior固有Evidenceとしては算入しない。

現行itemはAuthority raw anchorから人手Decisionで昇格したAtomic behaviorではありません。全行は`authority_atomic_binding: false`、`completion_eligible: false`です。ControllerとKubernetes version identityまでArtifact内で完結する行だけを`bounded-runtime-proof`、直接Evidenceはあるがidentity gapが残る行を`bounded-artifact-proof`、直接Evidenceがない行を`behavior-specific-gap`とします。いずれもTarget closureやDefinitive完成を意味しません。

## 再生成と検証

```sh
make scenario-proofs
make scenario-proofs-validate
```

Validatorは1,000ファイルの集合、Source／Harness／Artifact digest、10 Scenario、各rowのidentity、4観測ChannelのArtifactまたはgap、統合結果の非流用、Authority／Completionの0固定をofflineで照合します。
